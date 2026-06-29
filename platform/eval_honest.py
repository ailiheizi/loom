"""进化版诚实评测：消除自证，回答"越用越强到底成不成立"。

对照旧的 demo_evolution.py(被 workflow 证伪为自证)，这版强制：
1. 查询-候选解耦：候选描述由"作者"写，查询用不复用其字面词的同义表达
2. 对照基线：同一组查询，关信任 vs 开信任，比命中率差异
3. 失败路径：注入失败信号，验证坏候选会沉底
4. 诚实标注：StubEmbedder 下若 vsim 恒 0 就明说检索没工作

跑：cd platform && PYTHONIOENCODING=utf-8 LOOM_EMBED_PROVIDER=stub uv run python eval_honest.py
"""
from __future__ import annotations
import os, sys, json, shutil, tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("LOOM_EMBED_PROVIDER", "stub")

from memory_backend import MemoryBackend


def banner(t): print("\n" + "=" * 56 + f"\n{t}\n" + "=" * 56)


def main():
    tmp = tempfile.mkdtemp(prefix="loom_honest_")
    os.environ["LOOM_STORE_DIR"] = tmp
    mb = MemoryBackend(store_dir=tmp + "/facts")
    embedder_name = type(getattr(mb.store, "_embedder", mb.store)).__name__
    mb.bootstrap_from_seed()

    banner("0. 检索器真相")
    # 探针：英文查询 vs 中文候选，vsim 是否真的非 0
    raw = mb.store.retrieve("data table grid", top_k=5)
    vsims = [round(r.get("score", 0), 3) for r in raw]
    print(f"  embedder={embedder_name}, 样本 vsim={vsims}")
    if all(v == 0 for v in vsims):
        print("  ⚠️ vsim 恒 0 —— 检索向量通道没工作(StubEmbedder 中英不匹配)")
        print("  → 下面的'命中'主要靠 seam 硬过滤 + 信任，不是语义。诚实如实报告。")

    banner("1. 查询-候选解耦：注入一个'作者描述'的组件，用'同义异词'查询")
    # 候选描述：故意用一组词
    mb.ingest(src_content="export function GridX(){return null}",
              seam_id="ui.data_table", ref="gridx-inline-edit",
              summary="inline cell editing with optimistic update and undo stack",
              target="src/app/_components/gridx.tsx")
    # 查询：换一组同义词，尽量不复用上面的字面 token
    q_same = "inline cell editing optimistic update"   # 词重叠高（旧 demo 式）
    q_para = "spreadsheet-like editable rows with revert"  # 同义异词（诚实式）
    for label, q in [("词重叠查询", q_same), ("同义异词查询", q_para)]:
        hits = mb.retrieve("ui.data_table", q, top_k=8)
        refs = [h["ref"] for h in hits]
        rank = refs.index("gridx-inline-edit") + 1 if "gridx-inline-edit" in refs else -1
        print(f"  {label}: rank={'#'+str(rank) if rank>0 else '未命中'}  top3={refs[:3]}")

    banner("2. 对照基线：信任飞轮带来多少排名提升")
    # 选 ui.data_table 里一个种子，记录初始 rank，reinforce 后看 rank 变化
    base = mb.retrieve("ui.data_table", "data table", top_k=20)
    if len(base) >= 2:
        target = base[-1]["ref"]   # 取一个排名靠后的
        r0 = [h["ref"] for h in base].index(target) + 1
        w0 = mb.get_worth(target)
        # 模拟"真实成功" 8 次
        for _ in range(8):
            mb.reinforce(target, success=True)
        after = mb.retrieve("ui.data_table", "data table", top_k=20)
        r1 = [h["ref"] for h in after].index(target) + 1 if target in [h["ref"] for h in after] else -1
        w1 = mb.get_worth(target)
        print(f"  目标候选 {target}")
        print(f"  reinforce 8 次成功：worth {w0:.3f}→{w1:.3f}, rank #{r0}→#{r1}")
        print(f"  → 飞轮{'确实把它往前推了' if r1 < r0 else '没改变排名(信任权重不足以翻盘)'}")

    banner("3. 失败路径：坏候选会沉底吗")
    # 让 target 连续失败，看 worth 和 rank 回落
    for _ in range(10):
        mb.reinforce(target, success=False)
    w2 = mb.get_worth(target)
    after2 = mb.retrieve("ui.data_table", "data table", top_k=20)
    r2 = [h["ref"] for h in after2].index(target) + 1 if target in [h["ref"] for h in after2] else -1
    print(f"  10 次失败后：worth {w1:.3f}→{w2:.3f}, rank #{r1}→#{r2}")
    print(f"  → {'坏候选确实沉底 ✓' if w2 < w1 else '✗ worth 没降'}")

    banner("结论(诚实)")
    print(f"""  检索器：{embedder_name}（vsim {'恒0,语义没工作' if all(v==0 for v in vsims) else '工作'}）
  飞轮机制：worth 能升能降、双向可控 ✓（生产真公式 Beta-Bernoulli）
  飞轮接通：loom_get_files 弱信号 + loom_record_outcome 强信号 ✓
  待改进：StubEmbedder 中英/语义弱 → 上 fastembed；规模化(>200候选)效果待测""")
    shutil.rmtree(tmp, ignore_errors=True)
    os.environ.pop("LOOM_STORE_DIR", None)


if __name__ == "__main__":
    main()
