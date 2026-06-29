"""W_TRUST 扫描：信任权重多大才能让飞轮真翻盘？回答 eval_honest 暴露的"#9→#9 没动"。

对每个 W_TRUST 值：取一个排名靠后的候选，reinforce 8 次成功，看 rank 提升多少。
找到"飞轮能翻盘但不过度压制语义"的合理区间。

跑：cd platform && PYTHONIOENCODING=utf-8 LOOM_EMBED_PROVIDER=stub uv run python eval_wtrust.py
"""
from __future__ import annotations
import os, sys, shutil, tempfile, importlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("LOOM_EMBED_PROVIDER", "stub")


def run_one(w_trust: float):
    os.environ["LOOM_W_TRUST"] = str(w_trust)
    tmp = tempfile.mkdtemp(prefix=f"loom_wt_{w_trust}_")
    os.environ["LOOM_STORE_DIR"] = tmp
    import memory_backend
    importlib.reload(memory_backend)  # 重载让 _W_TRUST 生效
    mb = memory_backend.MemoryBackend(store_dir=tmp + "/facts")
    mb.bootstrap_from_seed()

    base = mb.retrieve("ui.data_table", "data table", top_k=20)
    refs0 = [h["ref"] for h in base]
    target = refs0[-1]  # 最靠后的
    r0 = len(refs0)
    # 看靠后候选与 top1 的语义分差(诊断)
    gap = base[0]["score"] - base[-1]["score"]
    for _ in range(8):
        mb.reinforce(target, success=True)
    after = mb.retrieve("ui.data_table", "data table", top_k=20)
    refs1 = [h["ref"] for h in after]
    r1 = refs1.index(target) + 1 if target in refs1 else -1
    shutil.rmtree(tmp, ignore_errors=True)
    return r0, r1, gap


def main():
    print("W_TRUST 扫描：靠后候选 reinforce 8 次成功后的 rank 变化")
    print(f"{'W_TRUST':>8} | {'rank 变化':>12} | {'语义分差(top1-last)':>18} | 翻盘?")
    print("-" * 60)
    for wt in [0.0, 0.2, 0.5, 1.0, 2.0, 3.0]:
        r0, r1, gap = run_one(wt)
        moved = r0 - r1
        flag = f"前进 {moved} 名" if moved > 0 else "没动"
        print(f"{wt:>8.1f} | {('#'+str(r0)+'→#'+str(r1)):>12} | {gap:>18.3f} | {flag}")
    os.environ.pop("LOOM_W_TRUST", None)
    os.environ.pop("LOOM_STORE_DIR", None)
    print("\n解读：W_TRUST 太小→飞轮无力(语义分差压过信任)；太大→信任压过语义(老候选霸榜)。")
    print("目标：让 8 次成功能前进几名，但不至于一次成功就霸榜。")


if __name__ == "__main__":
    main()
