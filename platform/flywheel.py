"""飞轮回流（loom.flywheel）—— M5：合成/上传产物回流入池 + 健康度闭环。

docs 步骤8：generate 产物过 Gate-1 后打包成 registry item 入 pending/，过同一 ingest 管线，
provenance=synthesized 低初始健康度入池；被复用→健康度升→转优先 pick。用户上传 provenance=user 更高信任。

闭环两端（本模块）：
  harvest()     ：generate 产物（已过 gate）→ ingest 入池，provenance=synthesized，健康度 0.3（低）
  record_reuse()：某候选被 pick → 健康度 += 增量，跨阈值（0.6）标记 promoted（转优先 pick）

健康度→排序的另半闭环已在 retrieve.py（W_HEALTH=0.3）就位：健康度升 → 检索得分升 → 更易被选。
最小真实版：本地文件池 + JSON meta 原地改健康度。推迟 M5+：Qdrant 同步、OCI 分发、四道闸门治理。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ingest import ingest_file

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "candidates"

SYNTH_INITIAL_HEALTH = 0.3   # 合成产物初始健康度（低，未经实战）
USER_INITIAL_HEALTH = 0.6    # 用户上传初始信任更高
REUSE_INCREMENT = 0.15       # 每次被复用的健康度增量
PROMOTE_THRESHOLD = 0.6      # 跨此阈值视为"转优先 pick"


def harvest(
    src_path: Path,
    seam_id: str,
    ref: str,
    summary: str,
    target: str,
    provenance: str = "synthesized",
) -> Path:
    """把一个（已过 gate 的）generate/上传产物回流入池。

    复用 ingest.py 的解析+打包，再把 provenance/健康度 改成回流语义。
    """
    meta_path = ingest_file(src_path, seam_id, ref, summary, target, CANDIDATES)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    init_health = USER_INITIAL_HEALTH if provenance == "user" else SYNTH_INITIAL_HEALTH
    meta["registry_item"]["meta_loom"]["provenance"] = provenance
    meta["registry_item"]["meta_loom"]["health"] = init_health
    meta["l0"]["provenance"] = provenance
    meta["l0"]["health"] = init_health
    meta["l0"]["reuse_count"] = 0
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def record_reuse(seam_id: str, ref: str) -> dict:
    """某候选被 pick → 健康度升、reuse_count+1，跨阈值标记 promoted。返回闭环状态。"""
    meta_path = CANDIDATES / seam_id / ref / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"候选不存在: {seam_id}/{ref}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    old = float(meta["l0"].get("health", 0.0))
    new = min(1.0, old + REUSE_INCREMENT)
    count = int(meta["l0"].get("reuse_count", 0)) + 1
    meta["l0"]["health"] = new
    meta["l0"]["reuse_count"] = count
    meta["registry_item"]["meta_loom"]["health"] = new
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ref": ref,
        "health_before": round(old, 3),
        "health_after": round(new, 3),
        "reuse_count": count,
        "promoted": old < PROMOTE_THRESHOLD <= new,  # 本次跨过阈值
        "is_pick_grade": new >= PROMOTE_THRESHOLD,
    }
