"""全流程端到端测试：模拟真实用户旅程(装 MCP → propose → plan → get_files → ingest → 越用越强)。

验证 Loom 进化版作为一个产品,从头到尾能不能跑通。不是单元测试——是用户旅程。

跑：cd platform && PYTHONIOENCODING=utf-8 LOOM_EMBED_PROVIDER=stub uv run python test_e2e_journey.py
"""
from __future__ import annotations
import os, sys, json, tempfile, shutil

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("LOOM_EMBED_PROVIDER", "stub")

# 隔离环境
STORE = tempfile.mkdtemp(prefix="loom_e2e_")
os.environ["LOOM_STORE_DIR"] = STORE
os.environ["LOOM_BACKEND"] = "memory"

import mcp_server as m
import memory_backend as mb

fails = []
def check(name, cond, extra=""):
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f"  ({extra})" if extra else ""))
    if not cond: fails.append(name)

def main():
    print("=" * 60)
    print("全流程端到端：真实用户旅程")
    print("=" * 60)

    # ── 第 0 步：首次启动,自动 bootstrap(模拟 uvx 首次跑)
    print("\n▶ 0. 首次启动(自动 bootstrap seed)")
    backend = mb.get_backend()
    check("bootstrap 成功", backend.count >= 39, f"count={backend.count}")

    # ── 第 1 步：用户说想法 → propose 返回候选梯度
    print("\n▶ 1. loom_propose(想法 → 候选梯度)")
    idea = json.dumps({
        "idea_id": "e2e-test",
        "title": "带 Google 登录、Project 增删改查、数据表格的 SaaS 后台",
        "description": "一个标准 SaaS 后台：Google OAuth + CRUD + 表格展示",
        "core_ref": "create-t3-app@7.39.x",
        "capability_intents": [
            {"intent": "Google OAuth 登录", "seam_id": "auth.oauth_provider"},
            {"intent": "Project 增删改查", "seam_id": "data.crud_resource"},
            {"intent": "数据表格展示列表", "seam_id": "ui.data_table"},
        ],
    })
    propose_result = json.loads(m.loom_propose(idea))
    seams = propose_result.get("seams", propose_result) if isinstance(propose_result, dict) else propose_result
    check("propose 返回多个 seam", len(seams) >= 3, f"seams={len(seams)}")
    # 每个 seam 应有 candidates 列表
    first_seam = seams[0]
    check("每个 seam 有候选列表", "candidates" in first_seam and len(first_seam["candidates"]) >= 1)

    # ── 第 2 步：AI 帮用户选 → plan
    print("\n▶ 2. loom_plan_from_choices(选择 → 装配计划)")
    choices = []
    for seam in seams:
        if seam.get("candidates"):
            choices.append({
                "seam_id": seam["seam_id"],
                "action": "pick",
                "ref": seam["candidates"][0]["ref"],
            })
    plan_result = json.loads(m.loom_plan_from_choices(idea, json.dumps(choices)))
    check("plan 有 seams", "seams" in plan_result and len(plan_result["seams"]) >= 1)
    check("plan 有 idea_id", "idea_id" in plan_result)

    # ── 第 3 步：get_files 物化(轻量路径)
    print("\n▶ 3. loom_get_files(物化 → 文件清单)")
    files_result = json.loads(m.loom_get_files(json.dumps(plan_result)))
    check("get_files 返回文件", "files" in files_result and len(files_result["files"]) >= 5,
          f"files={len(files_result.get('files', []))}")
    # 检查 _next_step 提醒(信号闭环的信息提示)
    has_hint = "_next_step" in files_result
    check("返回包含 _next_step(信号闭环提醒)", has_hint)

    # ── 第 4 步：手动 record_outcome(模拟 agent 验证后回报)
    print("\n▶ 4. loom_record_outcome(模拟验证通过 → 飞轮真实驱动)")
    picked_refs = [s["ref"] for s in plan_result["seams"] if s.get("ref")]
    if picked_refs:
        w_before = backend.get_worth(picked_refs[0])
        outcome = json.loads(m.loom_record_outcome(picked_refs, True, "tsc 通过"))
        w_after = backend.get_worth(picked_refs[0])
        check("record_outcome 驱动 worth 上升", w_after > w_before,
              f"{picked_refs[0]}: {w_before:.3f}→{w_after:.3f}")
    else:
        check("有 picked refs 可回报", False)

    # ── 第 5 步：用户写了新代码 → ingest 进库
    print("\n▶ 5. loom_ingest(用户新代码收录进库)")
    # 创建一个假文件模拟用户写的组件
    comp_dir = os.path.join(STORE, "my_components")
    os.makedirs(comp_dir, exist_ok=True)
    comp_file = os.path.join(comp_dir, "MyDashboard.tsx")
    with open(comp_file, "w", encoding="utf-8") as f:
        f.write('export function MyDashboard() { return <div>我的仪表盘</div>; }')
    ingest_result = json.loads(m.loom_ingest([comp_file], "ui.layout", "自定义仪表盘布局"))
    check("ingest 成功", ingest_result.get("status") == "ingested" or "ingested" in str(ingest_result),
          f"result={list(ingest_result.keys())}")

    # ── 第 6 步：越用越强验证——下次类似需求能检索到自己写的
    print("\n▶ 6. 越用越强验证：下次检索到用户自己写的组件")
    hits = backend.retrieve("ui.layout", "dashboard layout", top_k=5)
    refs = [h["ref"] for h in hits]
    # ingest 的 ref 从文件名推断
    found = any("dashboard" in r.lower() or "mydashboard" in r.lower() for r in refs)
    check("检索到用户自己 ingest 的组件", found, f"top5={refs}")

    # ── 第 7 步：飞轮验证——真正的"越用越强"：排名随使用提升
    print("\n▶ 7. 越用越强核心验证：被复用候选在竞争中排名真的提升")
    # 用 ui.data_table(有 8 个种子候选,语义都相关)做竞争对照
    hits_before = backend.retrieve("ui.data_table", "data table", top_k=10)
    if len(hits_before) >= 3:
        # 取排名最后的候选作为目标
        target_ref = hits_before[-1]["ref"]
        rank_before = len(hits_before)
        w_before = backend.get_worth(target_ref)

        # 只对目标做 8 次成功强化(模拟"这个候选被反复用且验证通过")
        for _ in range(8):
            backend.reinforce(target_ref, success=True)
        w_after = backend.get_worth(target_ref)

        # 关键断言：再次检索时,该候选排名真的提升了
        hits_after = backend.retrieve("ui.data_table", "data table", top_k=10)
        refs_after = [h["ref"] for h in hits_after]
        rank_after = refs_after.index(target_ref) + 1 if target_ref in refs_after else -1

        check("worth 升", w_after > w_before, f"{w_before:.3f}→{w_after:.3f}")
        check("排名真的提升(越用越强核心)", rank_after < rank_before,
              f"#{rank_before}→#{rank_after}")
        # 对照：没被强化的候选排名没变或下降
        other_ref = hits_before[0]["ref"]  # 之前排第一的
        rank_other_after = refs_after.index(other_ref) + 1 if other_ref in refs_after else -1
        check("未强化候选排名不升", rank_other_after >= 1)  # 至少没比之前更前
    else:
        check("ui.data_table 有足够候选做竞争", False)

    # ── 第 8 步：失败信号验证——坏候选真的沉底
    print("\n▶ 8. 坏候选沉底验证：失败信号让排名下降")
    if len(hits_before) >= 3:
        top_ref = hits_before[0]["ref"]
        rank_top_before = 1
        for _ in range(10):
            backend.reinforce(top_ref, success=False)
        hits_punished = backend.retrieve("ui.data_table", "data table", top_k=10)
        refs_p = [h["ref"] for h in hits_punished]
        rank_top_after = refs_p.index(top_ref) + 1 if top_ref in refs_p else -1
        check("10次失败后排名下降(坏候选沉底)", rank_top_after > rank_top_before,
              f"#{rank_top_before}→#{rank_top_after}")

    # ── 清理
    shutil.rmtree(STORE, ignore_errors=True)
    os.environ.pop("LOOM_STORE_DIR", None)

    print("\n" + "=" * 60)
    if fails:
        print(f"FAIL: {len(fails)} 项失败 — {', '.join(fails)}")
    else:
        print("全流程 PASS ✅ — 从装 MCP 到越用越强,端到端通")
    print("=" * 60)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
