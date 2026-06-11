"""选择引擎（select.py）—— M1 的 AI 核心。

retrieval-as-generation：喂 idea + 所有候选的 L0 清单 + L1 签名，
AI 用 expand_l2 工具按需展开候选全文（披露式展开），
最终用 submit_plan 工具输出 AssemblyPlan（output 极小：每 seam 一条决策）。

经济埋点：分桶记录 input/output token；schema 重试单独计量不计入主成本。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic

import loom_contracts as c
from load_candidates import Candidate, load_candidates, find_candidate

MODEL = os.environ.get("LOOM_MODEL", "claude-sonnet-4-6")
MAX_TURNS = 12  # 披露式展开 + 提交的总轮次硬上限

ROOT = Path(__file__).resolve().parent.parent


def _l0_digest(by_seam: dict[str, list[Candidate]]) -> str:
    """L0 候选清单（粗筛层）。"""
    lines = []
    for seam_id, cands in by_seam.items():
        lines.append(f"## seam: {seam_id}")
        for cand in cands:
            l0 = cand.l0
            lines.append(
                f"  - ref={l0.ref} | {l0.summary} | deps={l0.deps} | loc={l0.loc} | health={l0.health}"
            )
    return "\n".join(lines)


def _l1_digest(cand: Candidate) -> str:
    """L1 接口签名（决赛层）。"""
    exports = "; ".join(f"{e.name}: {e.signature}" for e in cand.l1.exports)
    return f"ref={cand.ref} exports=[{exports}] imports={cand.l1.imports} types={cand.l1.types}"


SUBMIT_TOOL = {
    "name": "submit_plan",
    "description": "提交最终装配清单。对每个 seam 给出一条决策。",
    "input_schema": {
        "type": "object",
        "properties": {
            "seams": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "seam_id": {"type": "string"},
                        "action": {"type": "string", "enum": ["pick", "adapt", "generate", "skip"]},
                        "ref": {"type": ["string", "null"], "description": "pick/adapt 时选中的候选 ref"},
                        "adapter": {"type": ["string", "null"], "description": "adapt 时需要的胶水说明"},
                        "generated_file": {
                            "type": ["string", "null"],
                            "description": "generate 时要写的目标文件路径",
                        },
                        "confidence": {"type": "number"},
                        "why": {"type": "string", "description": "一句话理由"},
                    },
                    "required": ["seam_id", "action", "confidence", "why"],
                },
            }
        },
        "required": ["seams"],
    },
}

EXPAND_TOOL = {
    "name": "expand_l2",
    "description": "展开某候选的 L2 全文源码。只在 L0/L1 不足以决策时调用，避免浪费 input。",
    "input_schema": {
        "type": "object",
        "properties": {
            "seam_id": {"type": "string"},
            "ref": {"type": "string"},
        },
        "required": ["seam_id", "ref"],
    },
}

SYSTEM = """你是 Loom 的装配选择引擎。给定一个开发想法和一个受控候选库，你的工作不是写代码，而是【选择】：
对想法分解出的每个 seam（接缝），从候选库里选一个最合适的（action=pick），或选一个需小幅适配的（action=adapt），
或在确实没有合适候选时才自己写（action=generate），或保留 core 自带（action=skip）。

原则：
- 优先 pick：候选是实战检验过的真实代码，复用胜过生成。
- 只有当某 seam 的所有候选都明显不匹配能力需求时，才用 generate。
- 披露式展开：先看 L0 摘要和 L1 签名。只有签名不足以判断时，才用 expand_l2 取全文。节省 input。
- 想清楚后用 submit_plan 一次性提交所有 seam 的决策。"""


def _select_via_openai(user_msg: str, idea: dict, metrics: c.AssemblyMetrics) -> tuple[c.AssemblyPlan, c.AssemblyMetrics]:
    """deepseek（OpenAI 兼容）单轮 JSON 输出选择路径。

    不用 anthropic 多轮 tool-use（deepseek tool 格式不同），改为让模型直接按 schema 返回
    seams 决策 JSON。deepseek JSON 输出可靠，且省去 expand_l2 多轮（M1 候选 L0/L1 已够判断）。
    """
    from openai import OpenAI

    base = os.environ.get("LOOM_LLM_BASE_URL", "https://api.deepseek.com")
    key = os.environ["LOOM_LLM_API_KEY"]
    model = os.environ.get("LOOM_LLM_MODEL", "deepseek-chat")
    client = OpenAI(api_key=key, base_url=base)

    sys_prompt = SYSTEM + (
        "\n\n【输出格式】直接返回 JSON 对象，不要 tool_call、不要解释。形如："
        '{"seams":[{"seam_id":"...","action":"pick|adapt|generate|skip",'
        '"ref":"候选ref或null","generated_file":"generate时给路径否则null",'
        '"confidence":0.0-1.0,"why":"理由"}]}。每个 seam 一条决策。'
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        max_tokens=4096,
    )
    metrics.total_input_tok += resp.usage.prompt_tokens
    metrics.total_output_tok += resp.usage.completion_tokens

    data = json.loads(resp.choices[0].message.content)
    seams = [
        c.SelectionDecision(
            seam_id=s["seam_id"],
            action=c.SeamAction(s["action"]),
            ref=s.get("ref"),
            generated_file=s.get("generated_file"),
            confidence=s.get("confidence", 0.0),
            why=s.get("why", ""),
        )
        for s in data["seams"]
    ]
    plan = c.AssemblyPlan(
        idea_id=idea["idea_id"],
        core_ref=idea["core_ref"],
        seams=seams,
        synthesized=[s.generated_file for s in seams if s.action == c.SeamAction.GENERATE and s.generated_file],
    )
    gen = sum(1 for s in seams if s.action == c.SeamAction.GENERATE)
    metrics.write_own_ratio = gen / len(seams) if seams else 0.0
    plan.budget = c.TokenBudget(input_tok=metrics.total_input_tok, output_tok=metrics.total_output_tok)
    return plan, metrics


def run_selection(idea_path: Path, use_retrieve: bool = False, top_k: int = 3) -> tuple[c.AssemblyPlan, c.AssemblyMetrics]:
    idea = json.loads(idea_path.read_text(encoding="utf-8"))
    by_seam = load_candidates(ROOT / "candidates")

    if use_retrieve:
        # M3 真检索：对每个 capability 的 seam 召回 top-k，只喂召回子集（替换 L0 全量喂）。
        from retrieve import Retriever

        core = json.loads((ROOT / "core" / "loom.core.json").read_text(encoding="utf-8"))
        seam_sig = {s["seam_id"]: s.get("signature", "") for s in core["seams"]}
        retriever = Retriever(by_seam)
        retrieved: dict[str, list] = {}
        for ci in idea["capability_intents"]:
            sid = ci["seam_id"]
            q = f"{seam_sig.get(sid, '')} | {ci['intent']}"
            hits = retriever.retrieve(sid, q, top_k=top_k)
            retrieved[sid] = [find_candidate(by_seam, sid, h.ref) for h in hits]
        # 仅保留召回到的候选，喂给 AI
        l0_lines, l1_all = [], []
        for sid, cands in retrieved.items():
            cands = [c for c in cands if c]
            if not cands:
                continue
            l0_lines.append(f"## seam: {sid}")
            for cand in cands:
                l0_lines.append(
                    f"  - ref={cand.l0.ref} | {cand.l0.summary} | deps={cand.l0.deps} | loc={cand.l0.loc} | health={cand.l0.health}"
                )
                l1_all.append(_l1_digest(cand))
        l0_digest = "\n".join(l0_lines)
    else:
        # 初始 prompt：idea + 全部 L0 + 全部 L1（一次性给足检索层，省去多轮往返）
        l1_all = []
        for cands in by_seam.values():
            for cand in cands:
                l1_all.append(_l1_digest(cand))
        l0_digest = _l0_digest(by_seam)

    intents = "\n".join(
        f"  - intent: {ci['intent']} → seam={ci['seam_id']}" for ci in idea["capability_intents"]
    )
    user_msg = f"""# 开发想法
{idea['title']}
{idea['description']}

# 需要装配的 seam（来自想法分解）
{intents}

# 候选库 L0 清单
{l0_digest}

# 候选 L1 接口签名
{chr(10).join('  ' + s for s in l1_all)}

请对每个 seam 做出决策。注意：某些 seam 可能没有候选，那就 action=generate。"""

    metrics = c.AssemblyMetrics(arm="assembly", idea_id=idea["idea_id"])
    plan: c.AssemblyPlan | None = None

    # provider 分支：deepseek（OpenAI 兼容，JSON 输出）vs anthropic（原生 tool-use）
    if os.environ.get("LOOM_LLM_PROVIDER", "").lower() == "deepseek":
        return _select_via_openai(user_msg, idea, metrics)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages: list[dict] = [{"role": "user", "content": user_msg}]

    for _turn in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM,
            tools=[EXPAND_TOOL, SUBMIT_TOOL],
            messages=messages,
        )
        metrics.total_input_tok += resp.usage.input_tokens
        metrics.total_output_tok += resp.usage.output_tokens

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            # 没有工具调用，提示模型必须用工具
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": "请用 submit_plan 提交决策，或用 expand_l2 取更多信息。"})
            continue

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        submitted = False

        for tu in tool_uses:
            if tu.name == "submit_plan":
                seams = [
                    c.SelectionDecision(
                        seam_id=s["seam_id"],
                        action=c.SeamAction(s["action"]),
                        ref=s.get("ref"),
                        adapter=s.get("adapter"),
                        generated_file=s.get("generated_file"),
                        confidence=s.get("confidence", 0.0),
                        why=s.get("why", ""),
                    )
                    for s in tu.input["seams"]
                ]
                plan = c.AssemblyPlan(
                    idea_id=idea["idea_id"],
                    core_ref=idea["core_ref"],
                    seams=seams,
                    synthesized=[s.generated_file for s in seams if s.action == c.SeamAction.GENERATE and s.generated_file],
                )
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "已收到 plan"})
                submitted = True
            elif tu.name == "expand_l2":
                cand = next(
                    (x for x in by_seam.get(tu.input["seam_id"], []) if x.ref == tu.input["ref"]),
                    None,
                )
                if cand:
                    files = cand.l2_files()
                    body = "\n\n".join(f"// {f.path}\n{f.content}" for f in files)
                else:
                    body = f"(未找到候选 {tu.input['seam_id']}/{tu.input['ref']})"
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": body})

        messages.append({"role": "user", "content": tool_results})
        if submitted:
            break

    if plan is None:
        raise RuntimeError(f"选择引擎在 {MAX_TURNS} 轮内未提交 plan")

    # 计算 WRITE_OWN 退化率
    gen = sum(1 for s in plan.seams if s.action == c.SeamAction.GENERATE)
    metrics.write_own_ratio = gen / len(plan.seams) if plan.seams else 0.0
    plan.budget = c.TokenBudget(input_tok=metrics.total_input_tok, output_tok=metrics.total_output_tok)

    return plan, metrics


if __name__ == "__main__":
    import sys

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_retrieve = "--retrieve" in sys.argv  # M3 真检索（默认 False=L0 全量喂，向后兼容）

    idea_file = ROOT / "ideas" / "saas-admin-with-google-auth.json"
    if args:
        idea_file = Path(args[0])

    plan, metrics = run_selection(idea_file, use_retrieve=use_retrieve)
    # 输出带 idea_id，避免多想法铺宽时互相覆盖（M2）
    out = ROOT / ".work" / f"assembly-plan-{plan.idea_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    print(f"[select] use_retrieve={use_retrieve} → {out.name} ({len(plan.seams)} decisions)")

    print(f"=== AssemblyPlan ({len(plan.seams)} decisions) ===")
    for s in plan.seams:
        print(f"  {s.seam_id}: {s.action.value}" + (f" -> {s.ref}" if s.ref else "") + f"  ({s.confidence:.2f}) {s.why}")
    print(f"=== 指标 ===")
    print(f"  input_tok={metrics.total_input_tok} output_tok={metrics.total_output_tok} equiv_cost={metrics.equiv_cost:.0f}")
    print(f"  WRITE_OWN 退化率={metrics.write_own_ratio:.2f}")
    print(f"  plan 写入 {out}")
