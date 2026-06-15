"""Loom MCP Server —— agent-native 入口（第三步）。

把 Loom 的能力暴露为 MCP 工具，装进 Claude Code/codex 等宿主 agent。
设计原则（用户已拍板）：
  - LLM 在 client 侧（宿主 agent）：对话/澄清/判断/选择由 agent 做，server 不调 LLM。
  - server 无状态：三个工具都是「输入 → 确定性输出」，不持有会话状态。

工具：
  1. loom_propose(idea_json)            → 候选梯度（每 seam 2-3 真实候选 + 架构取舍）
  2. loom_plan_from_choices(idea_json, choices) → 把 agent/用户的选择组装成 AssemblyPlan
  3. loom_materialize(plan_json)        → 确定性物化成能跑的 t3 starter，返回路径 + 收敛状态

闭环：agent 听想法 → propose → 摊候选给架构师挑 → plan_from_choices → materialize。

运行：uv run python mcp_server.py   （stdio transport，由宿主 agent 拉起）
依赖：mcp（见 pyproject）。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import loom_contracts as c
from propose import propose as _propose
from plan_from_choices import plan_from_choices as _plan_from_choices

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work"

mcp = FastMCP("loom")


def _write_idea_tmp(idea_json: str) -> Path:
    """把 idea JSON 文本落到临时文件（propose/plan 接收路径）。"""
    idea = json.loads(idea_json)
    WORK.mkdir(parents=True, exist_ok=True)
    p = WORK / f"idea-{idea['idea_id']}.json"
    p.write_text(json.dumps(idea, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@mcp.tool()
def loom_propose(idea_json: str) -> str:
    """对一个开发想法，返回每个能力 seam 的候选梯度（2-3 个真实候选 + 架构取舍）。

    宿主 agent 用这个结果摊给架构师挑：每个候选带 ref/summary/deps/health/score/tradeoffs，
    recommended=true 的是检索默认推荐项。needs_generate=true 表示该 seam 无候选只能从零写。

    入参 idea_json：想法 JSON 文本，格式同 ideas/*.json
      （idea_id / title / description / core_ref / capability_intents[{intent, seam_id}]）。
    返回：GradientProposal JSON 文本。
    """
    idea_path = _write_idea_tmp(idea_json)
    proposal = _propose(idea_path)
    return proposal.model_dump_json(indent=2)


@mcp.tool()
def loom_plan_from_choices(idea_json: str, choices_json: str) -> str:
    """把 agent/架构师对每个 seam 的选择，组装成确定性 AssemblyPlan（零 LLM）。

    入参：
      idea_json：同 loom_propose。
      choices_json：选择数组 JSON，每个 seam 一条：
        [{"seam_id": "ui.data_table", "action": "pick", "ref": "sortable-data-table"}, ...]
        action 省略时：有 ref 默认 pick，无 ref 默认 skip。generate 用 generated_file 指定目标路径。
    返回：AssemblyPlan JSON 文本（喂给 loom_materialize）。
    校验失败（选了不存在的候选 / 漏了某 seam）会抛错并列出可选项。
    """
    idea_path = _write_idea_tmp(idea_json)
    choices = json.loads(choices_json)
    if isinstance(choices, dict) and "choices" in choices:
        choices = choices["choices"]
    plan = _plan_from_choices(idea_path, choices)
    out = WORK / f"assembly-plan-{plan.idea_id}.json"
    out.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return plan.model_dump_json(indent=2)


@mcp.tool()
def loom_materialize(plan_json: str) -> str:
    """把 AssemblyPlan 确定性物化成能跑的 create-t3-app starter。

    client 侧确定性物化（零 LLM）：拷 base → 落候选文件 → 注入 prisma model/env →
    类型检查 gate。agent-native 设计：repairMode=none，gate 残留错不调 server 侧 LLM 修，
    而是经 unresolved 回传，交给宿主 agent（你）修——LLM 全在 client 侧。

    入参 plan_json：loom_plan_from_choices 的输出。
    返回：JSON 文本 {out_dir, converged, final_error_count, layers, unresolved, next}。
      converged=true 表示 0 类型错。unresolved 非空时是待宿主 agent 修的诊断。
    """
    plan = c.AssemblyPlan.model_validate_json(plan_json)
    WORK.mkdir(parents=True, exist_ok=True)
    plan_path = WORK / f"assembly-plan-{plan.idea_id}.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    out_dir = WORK / f"loom-out-{plan.idea_id}"

    # client 物化入口：cd client && LOOM_OUT=.. LOOM_PLAN=.. LOOM_REPAIR_MODE=none node tsx ...
    client = ROOT / "client"
    proc = subprocess.run(
        ["node", "node_modules/tsx/dist/cli.mjs", "scripts/loom_materialize.ts"],
        cwd=str(client),
        env={
            **_env(),
            "LOOM_OUT": str(out_dir),
            "LOOM_PLAN": str(plan_path),
            "LOOM_REPAIR_MODE": "none",  # server 零 LLM，残留错交宿主 agent
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    stdout = proc.stdout or ""
    # 解析 converged / final_error（materialize 打印 "converged=... final_error=..."）
    converged = "converged=true" in stdout
    final_err = 0
    unresolved = None
    for line in stdout.splitlines():
        if "final_error=" in line:
            try:
                final_err = int(line.split("final_error=")[1].split()[0])
            except (ValueError, IndexError):
                pass
        if line.startswith("[materialize] UNRESOLVED "):
            try:
                unresolved = json.loads(line.split("UNRESOLVED ", 1)[1])
            except (ValueError, IndexError):
                pass

    result = {
        "out_dir": str(out_dir),
        "converged": converged,
        "final_error_count": final_err,
        "ok": proc.returncode == 0 and converged,
        "next": f"cd {out_dir} && pnpm install && node node_modules/next/dist/bin/next dev",
        "log_tail": "\n".join(stdout.splitlines()[-15:]),
    }
    if unresolved:
        result["unresolved"] = unresolved
        result["hint"] = "gate 未收敛。这些诊断需你（宿主 agent）在 out_dir 里直接改文件修复，然后重跑 tsc 确认。"
    if proc.returncode != 0 and not stdout:
        result["error"] = (proc.stderr or "")[-500:]
    return json.dumps(result, ensure_ascii=False, indent=2)


def _env() -> dict:
    import os

    return dict(os.environ)


@mcp.tool()
def loom_get_files(plan_json: str) -> str:
    """把 AssemblyPlan 物化成文件清单（纯数据，server 不跑 Node、不装依赖）。

    agent-native 轻量物化：server 只返回"该写哪些文件 + 什么内容 + 装哪些依赖"，
    由宿主 agent（你）在用户本地写盘 → pnpm install → 填 .env → tsc 自验。
    server 零 Node、零存储、零 gate。

    入参 plan_json：loom_plan_from_choices 的输出。
    返回：JSON 文本 {idea_id, core_ref, files:[{path,content}], deps:[{name,version}],
      env_vars:[...], prisma_models:[...], notes:[...]}。
      - files：写盘即得完整 create-t3-app 项目（含 base + 选中组件 + barrel/env/prisma 注入）
      - deps：用户 pnpm add 这些（候选声明的外部依赖；多数候选零依赖）
      - notes：generate 接缝等需宿主 agent 补写的提示
    用户侧步骤：写所有 files → pnpm install（+ pnpm add deps）→ 填 .env 真值 → next dev。
    """
    from get_files import get_files

    plan = c.AssemblyPlan.model_validate_json(plan_json)
    result = get_files(plan)
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    import os

    # 启动预热：把 embedding 模型加载移到 server 启动期，避免首次工具调用超时。
    try:
        from propose import warmup
        warmup()
    except Exception:
        pass  # 预热失败不阻塞启动，首次调用会懒加载

    # transport：LOOM_TRANSPORT=http 时走 streamable-http（远程托管，配 cloudflared），
    # 否则默认 stdio（本地由宿主 agent 拉起）。
    transport = os.environ.get("LOOM_TRANSPORT", "stdio").lower()
    if transport == "http":
        host = os.environ.get("LOOM_HOST", "127.0.0.1")
        port = int(os.environ.get("LOOM_PORT", "8000"))
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
