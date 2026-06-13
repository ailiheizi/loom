"""读 .work/bench-archive 的多样本双臂 metrics，汇总成诚实的实测报告。"""
from __future__ import annotations
import json, statistics, sys
from pathlib import Path
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARCHIVE = Path(__file__).resolve().parent.parent / ".work" / "bench-archive"

# data[idea][arm] = list of (output_tok, converged)
data: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for f in sorted(ARCHIVE.glob("*.json")):
    # 文件名：<arm>-<idea>-run<N>.json，arm 可能含下划线(from_zero)
    name = f.stem
    arm = "from_zero" if name.startswith("from_zero") else "assembly"
    rest = name[len(arm) + 1:]  # 去掉 arm- 前缀
    idea = rest.rsplit("-run", 1)[0]
    d = json.loads(f.read_text(encoding="utf-8"))
    data[idea][arm].append((d["total_output_tok"], d["converged"]))

print("=== Loom 双臂对照实测（多样本）===\n")
print(f"{'想法':<34} {'臂':<10} {'样本':>4} {'out中位':>8} {'out范围':>14} {'收敛率':>8}")
print("-" * 84)

all_asm_out, all_fz_out = [], []
for idea in sorted(data):
    for arm in ("assembly", "from_zero"):
        runs = data[idea].get(arm, [])
        if not runs:
            continue
        outs = [r[0] for r in runs]
        convs = [r[1] for r in runs]
        med = int(statistics.median(outs))
        conv_rate = f"{sum(convs)}/{len(convs)}"
        print(f"{idea:<34} {arm:<10} {len(runs):>4} {med:>8} {f'{min(outs)}-{max(outs)}':>14} {conv_rate:>8}")
        (all_asm_out if arm == "assembly" else all_fz_out).extend(outs)

print("-" * 84)
if all_asm_out and all_fz_out:
    am, fm = statistics.median(all_asm_out), statistics.median(all_fz_out)
    print(f"\n全样本 output 中位数：assembly={am}  from_zero={fm}")
    print(f"量级比：from_zero / assembly ≈ {fm/am:.1f}×（组装省 AI 输出 ≈ {(1-am/fm)*100:.0f}%）")
    print(f"样本量：assembly {len(all_asm_out)} 次，from_zero {len(all_fz_out)} 次")
