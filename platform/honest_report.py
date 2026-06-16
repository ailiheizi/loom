"""汇总诚实 benchmark：两臂真实结局（收敛率 > 省 token%）。

诚实口径：
- 主指标 = 从零臂收敛率（修到真能跑的比例）。组装臂几乎都收敛。
- 省 token% 只在【两臂都收敛】的样本上算（否则拿没修完的从零比不公平）。
- 两臂都收敛的样本可能很少——那本身就是诚实结果（从零修到能跑确实难）。
"""
import json, glob, os, statistics
from pathlib import Path

ARCH = Path(__file__).resolve().parent.parent / ".work" / "honest-bench"

def load(arm, idea):
    p = ARCH / f"{arm}-{idea}.json"
    if not p.exists(): return None
    return json.loads(p.read_text(encoding="utf-8"))

ideas = sorted({os.path.basename(f).split("-",1)[1].rsplit(".json",1)[0]
                for f in glob.glob(str(ARCH/"assembly-*.json"))})

print("=== 诚实 benchmark（两臂 maxRounds=8，修到收敛或 thrash 止损）===\n")
print(f"{'想法':<34} {'组装结局':>10} {'从零结局':>14} {'组装out':>8} {'从零out':>8}")
print("-"*80)

asm_conv = fz_conv = 0
both_saved = []
for idea in ideas:
    a, z = load("assembly", idea), load("from_zero", idea)
    if not a or not z: continue
    ac, zc = a["converged"], z["converged"]
    asm_conv += ac; fz_conv += zc
    aout, zout = a["total_output_tok"], z["total_output_tok"]
    a_end = "✓收敛" if ac else f"✗{a['final_error_count']}错"
    z_end = "✓收敛" if zc else f"✗{z['final_error_count']}错thrash"
    print(f"{idea:<34} {a_end:>10} {z_end:>14} {aout:>8} {zout:>8}")
    if ac and zc:
        both_saved.append((aout, zout))

n = len(ideas)
print("-"*80)
print(f"\n组装臂收敛: {asm_conv}/{n}   从零臂收敛: {fz_conv}/{n}")
print(f"\n【核心结论】")
if fz_conv == 0:
    print(f"  从零生成 {n} 个想法 0 个修到能跑（都 thrash 止损）——deepseek 从零做不出能编译的项目。")
    print(f"  组装臂 {asm_conv}/{n} 收敛。这不是'省 X% token'，是'从零根本做不出，组装能'。")
elif both_saved:
    asm_med = statistics.median([s[0] for s in both_saved])
    fz_med = statistics.median([s[1] for s in both_saved])
    print(f"  仅 {len(both_saved)} 个想法两臂都收敛。这些样本上：")
    print(f"  组装 out 中位 {asm_med:.0f} vs 从零 {fz_med:.0f} → 省 {(1-asm_med/fz_med)*100:.0f}%（公平口径）")
print(f"\n注：从零臂未收敛时不算省 token%（避免拿半成品比成品的虚高）。单模型 deepseek。")
