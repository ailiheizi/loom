"""仓库分析入口（loom.analyze_repo）—— 飞轮自举的"前人种树"入口。

输入一个真实 repo 目录 → 扫 TS/TSX 源 → tree-sitter 抽 export 签名 →
AI（deepseek）判断每个文件对齐到哪个 loom 接缝（或 skip）→ 对齐的走 ingest 入池
（provenance=user，高初始信任）。入池前每个候选过 verify_candidates 质量门（防垃圾）。

"前人种树后人乘凉"：一个人贡献一个 repo，AI 自动拆成接缝级候选，
后来的想法就能 pick 到这些现成组件 → 池靠社区贡献自增长。

最小真实版（一轮可做完可测）：
  - 单语言 TS/TSX，对齐到现有 6 个 core 接缝
  - AI 单轮 JSON 输出对齐决策（复用 run_select 的 deepseek 路径）
诚实推迟：多语言、跨文件依赖分析、新接缝自动发现、大规模 repo。

用法：
  LOOM_LLM_PROVIDER=deepseek LOOM_LLM_API_KEY=sk-... \
    uv run python analyze_repo.py <repo_dir> [--dry-run]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ingest import extract_exports, ingest_file

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "candidates"

# 扫描时跳过的目录
SKIP_DIRS = {"node_modules", ".next", "generated", ".git", "dist", "build", ".work"}


def scan_ts_files(repo_dir: Path, max_files: int = 40) -> list[Path]:
    """扫 repo 下的 TS/TSX 源文件（跳过依赖/产物目录）。"""
    out: list[Path] = []
    for p in sorted(repo_dir.rglob("*.ts")) + sorted(repo_dir.rglob("*.tsx")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name.endswith(".d.ts") or p.name.endswith(".test.ts"):
            continue
        out.append(p)
        if len(out) >= max_files:
            break
    return out


def _seam_catalog() -> list[dict]:
    core = json.loads((ROOT / "core" / "loom.core.json").read_text(encoding="utf-8"))
    return [{"seam_id": s["seam_id"], "signature": s.get("signature", "")} for s in core["seams"]]


def align_files_to_seams(files: list[Path], repo_dir: Path) -> list[dict]:
    """AI 判断每个文件对齐到哪个接缝（或 skip）。单轮 JSON 输出。"""
    from openai import OpenAI

    base = os.environ.get("LOOM_LLM_BASE_URL", "https://api.deepseek.com")
    key = os.environ["LOOM_LLM_API_KEY"]
    model = os.environ.get("LOOM_LLM_MODEL", "deepseek-chat")
    client = OpenAI(api_key=key, base_url=base)

    seams = _seam_catalog()
    # 给 AI 每个文件的 export 签名摘要（不喂全文，省 input）
    file_digests = []
    for i, f in enumerate(files):
        try:
            exports = extract_exports(f.read_text(encoding="utf-8"))
        except Exception:
            exports = []
        sig = "; ".join(f"{e.kind} {e.name}: {e.signature}" for e in exports[:3]) or "(无 export)"
        file_digests.append(f"  [{i}] {f.relative_to(repo_dir)} → {sig[:150]}")

    sys_prompt = (
        "你是 Loom 的仓库分析器。给定一个 repo 的文件 export 签名清单和 Loom 的接缝(seam)目录，"
        "判断每个文件**对齐到哪个接缝**（该文件实现了那个接缝的能力），或 skip（不对齐任何接缝）。\n"
        "只在签名明确匹配接缝能力时对齐；拿不准就 skip。\n"
        "【接缝目录】\n" + "\n".join(f"  {s['seam_id']}: {s['signature']}" for s in seams) + "\n\n"
        '【输出】JSON：{"alignments":[{"file_index":0,"seam_id":"...或null(skip)",'
        '"ref":"建议候选名(kebab-case)","summary":"一句话能力摘要","confidence":0.0-1.0}]}'
    )
    user_msg = "仓库文件清单（index 文件 → export 签名）:\n" + "\n".join(file_digests)

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"},
        max_tokens=4096,
    )
    print(f"[analyze] AI 对齐 input={resp.usage.prompt_tokens} output={resp.usage.completion_tokens} tok")
    return json.loads(resp.choices[0].message.content).get("alignments", [])


# 接缝 → 物化目标目录（与 loom.core.json 的 target 对齐）
SEAM_TARGET_DIR = {
    "auth.oauth_provider": "src/server/auth/providers/",
    "data.crud_resource": "src/server/api/routers/",
    "ui.data_table": "src/app/_components/",
    "report.custom_export": "src/server/export/",
    "content.markdown_render": "src/app/_components/",
    "data.bulk_import": "src/server/import/",
}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if not args:
        print("用法: analyze_repo.py <repo_dir> [--dry-run]")
        return
    repo_dir = Path(args[0]).resolve()
    if not repo_dir.is_dir():
        print(f"✗ 不是目录: {repo_dir}")
        return

    files = scan_ts_files(repo_dir)
    print(f"=== analyze_repo: {repo_dir.name} ({len(files)} 个 TS 文件) ===")
    if not files:
        print("无可分析的 TS 文件")
        return

    alignments = align_files_to_seams(files, repo_dir)
    aligned = [a for a in alignments if a.get("seam_id")]
    print(f"\nAI 对齐结果：{len(aligned)}/{len(files)} 文件对齐到接缝\n")

    ingested = []
    for a in aligned:
        idx = a["file_index"]
        if idx >= len(files):
            continue
        f = files[idx]
        seam = a["seam_id"]
        ref = a.get("ref") or f.stem
        target_dir = SEAM_TARGET_DIR.get(seam)
        if not target_dir:
            print(f"  [skip] {f.name}: 未知接缝 {seam}")
            continue
        target = target_dir + f.name
        print(f"  [{a.get('confidence',0):.2f}] {f.relative_to(repo_dir)} → {seam} (ref={ref})")
        if dry_run:
            continue
        # 入池：provenance=user（贡献者，高初始信任），过 verify 门见下方提示
        meta_path = ingest_file(
            f, seam, ref, a.get("summary", f"来自 {repo_dir.name} 的贡献"),
            target, CANDIDATES,
        )
        # ingest 默认 provenance=platform，这里改成 user（贡献者）
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["registry_item"]["meta_loom"]["provenance"] = "user"
        meta["l0"]["provenance"] = "user"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        ingested.append(f"{seam}/{ref}")

    if dry_run:
        print(f"\n[dry-run] 不入池。去掉 --dry-run 实际 ingest。")
        return

    print(f"\n入池 {len(ingested)} 个候选（provenance=user），跑质量门自检…")
    # 飞轮防污染闭环：入池后立即过 verify 门，不过 t3 gate 的自动撤回（前人种坏树自动被拔）
    import subprocess

    proc = subprocess.run(
        ["uv", "run", "python", str(Path(__file__).parent / "verify_candidates.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent),
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # 解析 verify 输出，找新入池候选里没过门的（[✗] seam/ref）
    failed = []
    for line in out.splitlines():
        if "[✗]" in line:
            tag = line.split("[✗]")[1].strip().split()[0]  # seam/ref
            if tag in ingested:
                failed.append(tag)
    kept = [c for c in ingested if c not in failed]
    for tag in failed:
        seam, ref = tag.split("/", 1)
        d = CANDIDATES / seam / ref
        if d.exists():
            import shutil
            shutil.rmtree(d)
    print(f"\n✓ 质量门把关完成：")
    print(f"  留池（过 t3 gate）：{kept}")
    if failed:
        print(f"  自动撤回（未过门，AI 误判/不合格）：{failed}")
    print(f"  → 飞轮防污染：贡献被 AI 拆解入池，质量门自动拦截毒树。")


if __name__ == "__main__":
    main()
