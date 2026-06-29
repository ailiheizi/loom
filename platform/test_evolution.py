"""进化版回归测试：loom_ingest / 信任飞轮 / seam 推断 / memory_backend / bootstrap。

一键复跑（零网络，用 StubEmbedder）：
  cd platform && PYTHONIOENCODING=utf-8 LOOM_EMBED_PROVIDER=stub uv run python test_evolution.py

覆盖 docs/evolution-design.md 的 P0/P1/P2 + memory-engine 集成 + 自包含 bootstrap。
"""
from __future__ import annotations

import os
import sys
import json
import shutil
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("LOOM_EMBED_PROVIDER", "stub")

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = ""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✓ {name}")
    else:
        _failed += 1
        print(f"  ✗ {name}  {detail}")


def test_infer_seam():
    print("== P2: seam 自动推断 ==")
    from infer_seam import infer_seam
    cases = [
        ("Google OAuth 登录", "auth.oauth_provider"),
        ("对 Project 增删改查 CRUD", "data.crud_resource"),
        ("数据表格展示列表", "ui.data_table"),
        ("表单创建编辑", "ui.form"),
        ("导出 CSV", "report.custom_export"),
        ("批量导入 CSV", "data.bulk_import"),
        ("侧边栏布局", "ui.layout"),
    ]
    ok = sum(1 for t, exp in cases if infer_seam(t)[0] == exp)
    check(f"seam 推断 {ok}/{len(cases)}", ok == len(cases))


def test_beta_trust():
    print("== P1: Beta-Bernoulli 信任(MemoryWorth 上游公式) ==")
    # 测生产实际用的公式：worth=(s+1)/(s+f+2)(Laplace 平滑)
    try:
        from loom_vendor.memory_worth import MemoryWorth
    except ImportError:
        from memory_engine.memory_worth import MemoryWorth

    class _FakeStore:
        def __init__(self):
            self.facts = [{"id": 1, "success": 0, "failure": 0}]
        def _save(self):
            pass

    st = _FakeStore()
    w = MemoryWorth(st)
    check("初始 worth=0.5", abs(w.get_worth(1) - 0.5) < 1e-6)
    for _ in range(5):
        w.record_success(1)
    check("5 次 success → 6/7≈0.857", abs(w.get_worth(1) - 6 / 7) < 0.01,
          f"got {w.get_worth(1):.4f}")
    w.record_failure(1)
    check("failure 拉低信任", w.get_worth(1) < 6 / 7)
    # 置信度随观察次数升
    check("观察越多置信越高", w.get_confidence(1) > 0)


def test_backend_flywheel():
    print("== memory_backend + 飞轮闭环 ==")
    tmp = tempfile.mkdtemp()
    os.environ["LOOM_STORE_DIR"] = tmp
    try:
        from memory_backend import MemoryBackend
        mb = MemoryBackend(store_dir=tmp + "/facts")
        # bootstrap
        n = mb.bootstrap_from_seed()
        check(f"bootstrap 导入 {n} 候选", n >= 39, f"got {n}")
        # 去重：再 bootstrap 不重复
        n2 = mb.bootstrap_from_seed()
        check("重复 bootstrap 跳过", n2 == 0)
        # 检索
        hits = mb.retrieve("ui.data_table", "data table", top_k=3)
        check(f"检索返回 {len(hits)} 候选", len(hits) >= 1)
        check("候选带文件内容", bool(hits and hits[0].get("file_content")))
        # ingest 自写组件 → 飞轮闭环
        before = mb.count
        mb.ingest(src_content="export function Foo(){return null}",
                  seam_id="ui.data_table", ref="my-foo-table", summary="my custom foo table",
                  target="src/app/_components/foo.tsx")
        check("ingest 后 count+1", mb.count == before + 1)
        hits2 = mb.retrieve("ui.data_table", "custom foo table", top_k=5)
        check("ingest 的组件被召回", any(h["ref"] == "my-foo-table" for h in hits2))
        # reinforce 信任升（Beta worth）
        w_before = mb.get_worth("my-foo-table")
        ok = mb.reinforce("my-foo-table", success=True)
        check("reinforce(success) 成功", ok)
        w_after = mb.get_worth("my-foo-table")
        check("success → worth 升", w_after > w_before, f"{w_before:.3f}->{w_after:.3f}")
        # 失败路径：worth 必须能降（之前从没测过）
        mb.reinforce("my-foo-table", success=False)
        mb.reinforce("my-foo-table", success=False)
        w_fail = mb.get_worth("my-foo-table")
        check("failure → worth 降", w_fail < w_after, f"{w_after:.3f}->{w_fail:.3f}")
    finally:
        os.environ.pop("LOOM_STORE_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)


def test_full_chain():
    print("== 全链路 propose→plan→get_files (backend) ==")
    tmp = tempfile.mkdtemp()
    os.environ["LOOM_STORE_DIR"] = tmp
    os.environ["LOOM_BACKEND"] = "memory"
    try:
        import importlib
        import memory_backend, mcp_server
        importlib.reload(memory_backend)  # 重置单例用新 store_dir
        importlib.reload(mcp_server)
        m = mcp_server
        idea = json.dumps({"idea_id": "rt", "core_ref": "create-t3-app@7.39.x",
            "capability_intents": [
                {"intent": "google login", "seam_id": "auth.oauth_provider"},
                {"intent": "crud", "seam_id": "data.crud_resource"},
                {"intent": "data table", "seam_id": "ui.data_table"},
            ]})
        prop = json.loads(m.loom_propose(idea))
        check(f"propose {len(prop['seams'])} seams", len(prop["seams"]) == 3)
        choices = json.dumps([{"seam_id": s["seam_id"], "ref": s["candidates"][0]["ref"]}
                              for s in prop["seams"] if s["candidates"]])
        plan = m.loom_plan_from_choices(idea, choices)
        gf = json.loads(m.loom_get_files(plan))
        check(f"get_files {len(gf['files'])} 文件(完整项目)", len(gf["files"]) > 20)
        check("含 dashboard 页", any("dashboard" in f["path"] for f in gf["files"]))
        check("含 schema.prisma", any("schema.prisma" in f["path"] for f in gf["files"]))
    finally:
        os.environ.pop("LOOM_STORE_DIR", None)
        os.environ.pop("LOOM_BACKEND", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_infer_seam()
    test_beta_trust()
    test_backend_flywheel()
    test_full_chain()
    print(f"\n=== {_passed} passed, {_failed} failed ===")
    sys.exit(1 if _failed else 0)
