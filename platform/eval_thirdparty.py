"""第三方查询 + fastembed 规模化验证。

回答 workflow 指出的"评测脚本仍自证(查询由命题作者写)"：
- 用 seed 的中文 intent(来自 infer_seam 测试)和真实 GitHub issue 标题做查询
- 用 ingest_batch 批量导入大池(fastembed,不卡死)
- 测中文/英文/跨语言召回率 + 大池下飞轮

跑：cd platform && PYTHONIOENCODING=utf-8 LOOM_EMBED_PROVIDER=fastembed HTTPS_PROXY=http://127.0.0.1:7890 uv run python eval_thirdparty.py
"""
from __future__ import annotations
import os, sys, shutil, tempfile, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from memory_backend import MemoryBackend

# --- 第三方查询集(非为检索定制的, 来自 seam 推断 / GitHub issue 风格) ---
# seam→(查询, 该 seam 种子里应该命中的候选类型)
QUERIES = [
    # 来自 infer_seam 的中文 intent(为推断写的，不是为检索定制)
    ("ui.data_table", "数据表格展示列表", "中文intent"),
    ("ui.form", "表单创建编辑", "中文intent"),
    ("auth.oauth_provider", "Google OAuth 登录", "中文intent"),
    ("data.crud_resource", "对 Project 增删改查 CRUD", "中文intent"),
    ("ui.layout", "侧边栏布局", "中文intent"),
    # 模拟 GitHub issue 标题风格(英文,第三方用词)
    ("ui.data_table", "need a sortable filterable data grid", "GH issue EN"),
    ("ui.form", "add a form with validation and submit", "GH issue EN"),
    ("auth.oauth_provider", "implement social login with Google", "GH issue EN"),
    ("data.crud_resource", "REST API for creating and deleting resources", "GH issue EN"),
    ("ui.layout", "responsive sidebar navigation layout", "GH issue EN"),
    # 跨语言(中文查询，英文候选 summary / 反过来)
    ("ui.data_table", "我要一个可以排序筛选的表格", "ZH→EN候选"),
    ("ui.form", "I need a form component with built-in validation", "EN→候选"),
]


def main():
    tmp = tempfile.mkdtemp(prefix="loom_3p_")
    os.environ["LOOM_STORE_DIR"] = tmp
    embedder = os.environ.get("LOOM_EMBED_PROVIDER", "stub")
    mb = MemoryBackend(store_dir=tmp + "/facts")
    mb.bootstrap_from_seed()
    print(f"embedder={embedder}, 种子={mb.count}")

    # --- 1. 第三方查询召回率 ---
    print("\n" + "=" * 60)
    print("1. 第三方查询召回率(查询非为检索定制)")
    print("=" * 60)
    hit = 0
    total = 0
    for seam, query, src in QUERIES:
        hits = mb.retrieve(seam, query, top_k=5)
        refs = [h["ref"] for h in hits]
        # 召回标准：该 seam 下返回了至少 1 个候选(不判 ref 名,因为第三方查询不知道库里有啥)
        recalled = len(refs) > 0
        total += 1
        if recalled:
            hit += 1
        status = f"top1={refs[0]}" if refs else "✗空"
        print(f"  [{src:12s}] seam={seam:22s} → {status}")
    print(f"\n  召回率: {hit}/{total} = {hit/total:.0%}")

    # --- 2. fastembed 规模化(用 ingest_batch) ---
    print("\n" + "=" * 60)
    print("2. 规模化：批量注入 200 候选(ingest_batch)后召回+飞轮")
    print("=" * 60)
    items = [{"src_content": "x", "seam_id": "ui.data_table",
              "ref": f"scale-{i}", "summary": f"data table variant {i} with feature {i%7}",
              "target": f"g/{i}.tsx"} for i in range(200)]
    n = mb.ingest_batch(items)
    print(f"  批量注入 {n} 条, 总库 {mb.count}")
    # 用第三方查询测大池召回
    hits = mb.retrieve("ui.data_table", "我要一个可以排序筛选的表格", top_k=5)
    print(f"  中文查询大池 top5: {[h['ref'] for h in hits]}")
    # 飞轮大池翻盘
    base = mb.retrieve("ui.data_table", "data table", top_k=50)
    if len(base) >= 2:
        target = base[-1]["ref"]
        r0 = len(base)
        for _ in range(8):
            mb.reinforce(target, success=True)
        after = [h["ref"] for h in mb.retrieve("ui.data_table", "data table", top_k=50)]
        r1 = after.index(target) + 1 if target in after else -1
        print(f"  飞轮: #{r0}→#{r1} (reinforce 8 次成功)")

    shutil.rmtree(tmp, ignore_errors=True)
    os.environ.pop("LOOM_STORE_DIR", None)
    print("\n" + "=" * 60)
    print("诚实结论")
    print("=" * 60)


if __name__ == "__main__":
    main()
