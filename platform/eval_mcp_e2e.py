"""MCP server 三工具端到端冒烟测试：propose → plan_from_choices → materialize。

直接调工具函数（不走 stdio 协议），验证 agent-native 闭环：
想法 → 候选梯度 → 架构师选择 → plan → 0-error starter。

用法：cd platform && uv run python eval_mcp_e2e.py
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mcp_server as m

ROOT = Path(__file__).resolve().parent.parent
idea = (ROOT / "ideas" / "saas-admin-with-google-auth.json").read_text(encoding="utf-8")

# 1. propose：候选梯度
prop = json.loads(m.loom_propose(idea))
print(f"[1] propose: {len(prop['seams'])} seams")
for s in prop["seams"]:
    rec = next((c["ref"] for c in s["candidates"] if c.get("recommended")), "无")
    print(f"    {s['seam_id']}: {len(s['candidates'])} 候选, 推荐={rec}")
assert all(len(s["candidates"]) >= 1 for s in prop["seams"]), "有 seam 无候选"

# 2. 模拟架构师选择：ui.data_table 故意选非推荐的 sortable，证明能挑梯度
choices = []
for s in prop["seams"]:
    if s["seam_id"] == "ui.data_table":
        choices.append({"seam_id": s["seam_id"], "ref": "sortable-data-table"})
    else:
        rec = next((c["ref"] for c in s["candidates"] if c.get("recommended")), None)
        choices.append({"seam_id": s["seam_id"], "ref": rec})
print(f"[2] choices: {[(c['seam_id'].split('.')[-1], c['ref']) for c in choices]}")

# 3. plan_from_choices
plan = json.loads(m.loom_plan_from_choices(idea, json.dumps(choices)))
ui_ref = next(d["ref"] for d in plan["seams"] if d["seam_id"] == "ui.data_table")
print(f"[3] plan: {len(plan['seams'])} decisions, ui.data_table -> {ui_ref}")
assert ui_ref == "sortable-data-table", "选择未正确反映到 plan"

# 4. materialize
res = json.loads(m.loom_materialize(json.dumps(plan)))
print(f"[4] materialize: converged={res['converged']} final_error={res['final_error_count']} ok={res['ok']}")
print(f"    out_dir={res['out_dir']}")
assert res["converged"], "物化未收敛！"
assert res["final_error_count"] == 0, "有类型错！"

print("\n✓ MCP 三工具端到端闭环通过：想法 → 候选梯度 → 架构师选择 → plan → 0-error starter")
