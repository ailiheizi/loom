"""真实信号闭环端到端测试：client gate 产信号 → platform 消费 → 飞轮驱动。

验证第三轮 workflow 揪出的 fatal(飞轮成功信号是虚拟计数)已真正修复——
现在信号来自 client 的全项目 tsc gate，platform 自动消费，不靠 agent 主动调。

跑：cd platform && PYTHONIOENCODING=utf-8 LOOM_EMBED_PROVIDER=stub uv run python test_outcomes_loop.py
"""
from __future__ import annotations
import os, sys, json, tempfile, shutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("LOOM_EMBED_PROVIDER", "stub")

fails = []


def check(name, cond, extra=""):
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def main():
    print("== 真实信号闭环：client gate → outcomes.jsonl → platform reinforce ==")
    store = tempfile.mkdtemp(prefix="loom_loop_")
    os.environ["LOOM_STORE_DIR"] = store
    import memory_backend as mb

    # 1. 起 backend 建库
    mb._BACKEND = None
    b = mb.get_backend()
    ref_ok, ref_bad = "google-oauth", "sortable-data-table"
    w_ok0, w_bad0 = b.get_worth(ref_ok), b.get_worth(ref_bad)

    # 2. 模拟 client gate 产出的真实信号(success + failure 混合)
    op = Path(store) / "outcomes.jsonl"
    op.write_text(
        json.dumps({"ref": ref_ok, "seam_id": "auth.oauth_provider", "success": True,
                    "error_count": 0, "source": "client-gate"}) + "\n" +
        json.dumps({"ref": ref_ok, "success": True}) + "\n" +
        json.dumps({"ref": ref_bad, "success": False, "error_count": 3, "source": "client-gate"}) + "\n",
        encoding="utf-8",
    )

    # 3. 重启 backend 触发消费
    mb._BACKEND = None
    b2 = mb.get_backend()
    w_ok1, w_bad1 = b2.get_worth(ref_ok), b2.get_worth(ref_bad)

    check("success 信号抬升 worth", w_ok1 > w_ok0, f"{w_ok0:.3f}→{w_ok1:.3f}")
    check("failure 信号压低 worth", w_bad1 < w_bad0, f"{w_bad0:.3f}→{w_bad1:.3f}")
    check("outcomes 文件消费后删除(幂等)", not op.exists())

    # 4. 幂等性：再次重启不应重复计数
    mb._BACKEND = None
    b3 = mb.get_backend()
    w_ok2 = b3.get_worth(ref_ok)
    check("重启不重复计数(worth 不再变)", abs(w_ok2 - w_ok1) < 1e-9, f"{w_ok1:.3f}=={w_ok2:.3f}")

    # 5. 坏行容错
    op.write_text('{"ref":"google-oauth","success":true}\n{坏行}\n\n', encoding="utf-8")
    mb._BACKEND = None
    n_before_fail = len(fails)
    try:
        b4 = mb.get_backend()
        check("坏行不崩溃(跳过脏数据)", True)
    except Exception as e:
        check("坏行不崩溃(跳过脏数据)", False, str(e))

    # 6. ref 不在库 → 保留重试(不因文件删而丢信号)
    op.write_text(
        json.dumps({"ref": "google-oauth", "success": True}) + "\n" +
        json.dumps({"ref": "does-not-exist-ref", "success": True}) + "\n",
        encoding="utf-8",
    )
    b5 = b4  # 复用已消费过的 backend(库里有 google-oauth，无 does-not-exist-ref)
    consumed = b5.consume_outcomes(str(op))
    check("在库的 ref 被消费", consumed == 1, f"consumed={consumed}")
    check("不在库的 ref 保留文件重试", op.exists())
    if op.exists():
        remain = [l for l in op.read_text(encoding="utf-8").splitlines() if l.strip()]
        check("保留的正是不在库那条", len(remain) == 1 and "does-not-exist-ref" in remain[0],
              f"remain={remain}")

    shutil.rmtree(store, ignore_errors=True)
    os.environ.pop("LOOM_STORE_DIR", None)
    print(f"\n=== {'PASS' if not fails else 'FAIL: ' + ', '.join(fails)} ===")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
