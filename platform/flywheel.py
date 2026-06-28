"""飞轮回流（loom.flywheel）—— M5：合成/上传产物回流入池 + 健康度闭环 + 信任层。

docs 步骤8：generate 产物过 Gate-1 后打包成 registry item 入 pending/，过同一 ingest 管线，
provenance=synthesized 低初始健康度入池；被复用→健康度升→转优先 pick。用户上传 provenance=user 更高信任。

信任层（evolution-design P1）：
  trust_score：0.0~1.0，初始 0.5，每次 record_reuse +0.1（上限 1.0）
  last_used：ISO 时间戳，每次复用更新
  时间衰减：超 30 天没用 → 每天 -0.01（下限 0.1）
  检索加权：retrieve.py 的排序公式纳入 trust_score（W_TRUST）

闭环两端（本模块）：
  harvest()       ：generate 产物（已过 gate）→ ingest 入池
  record_reuse()  ：候选被 pick → 健康度/信任分升 + 更新 last_used
  apply_decay()   ：定期调用，对久未用的候选降低 trust_score
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
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

# 信任层参数
TRUST_INITIAL = 0.5          # 新候选初始信任分
TRUST_REUSE_BOOST = 0.1      # 每次复用 +0.1
TRUST_MAX = 1.0
TRUST_MIN = 0.1
TRUST_DECAY_AFTER_DAYS = 30  # 超过多少天没用开始衰减
TRUST_DECAY_PER_DAY = 0.01   # 每天衰减多少


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
    """某候选被 pick → 健康度升、trust_score 升、reuse_count+1、last_used 更新。"""
    meta_path = CANDIDATES / seam_id / ref / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"候选不存在: {seam_id}/{ref}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ml = meta["registry_item"]["meta_loom"]

    # 健康度
    old_health = float(meta["l0"].get("health", 0.0))
    new_health = min(1.0, old_health + REUSE_INCREMENT)
    count = int(meta["l0"].get("reuse_count", 0)) + 1
    meta["l0"]["health"] = new_health
    meta["l0"]["reuse_count"] = count
    ml["health"] = new_health

    # 信任分
    old_trust = float(ml.get("trust_score", TRUST_INITIAL))
    new_trust = min(TRUST_MAX, old_trust + TRUST_REUSE_BOOST)
    ml["trust_score"] = round(new_trust, 3)

    # last_used
    now = datetime.now(timezone.utc).isoformat()
    ml["last_used"] = now

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ref": ref,
        "health_before": round(old_health, 3),
        "health_after": round(new_health, 3),
        "trust_before": round(old_trust, 3),
        "trust_after": round(new_trust, 3),
        "reuse_count": count,
        "last_used": now,
        "promoted": old_health < PROMOTE_THRESHOLD <= new_health,
        "is_pick_grade": new_health >= PROMOTE_THRESHOLD,
    }


def apply_decay() -> list[dict]:
    """对久未使用的候选降低 trust_score（时间衰减）。返回被衰减的候选列表。

    建议定期调用（如每次 propose 前,或 cron）。只影响 trust_score,不影响 health。
    """
    now = datetime.now(timezone.utc)
    decayed: list[dict] = []
    for meta_path in CANDIDATES.rglob("meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ml = meta.get("registry_item", {}).get("meta_loom", {})
        last_used_str = ml.get("last_used")
        trust = float(ml.get("trust_score", TRUST_INITIAL))

        if trust <= TRUST_MIN:
            continue  # 已到下限,不再衰减

        if not last_used_str:
            continue  # 从未被 record_reuse 过,不衰减（保持初始分）

        try:
            last_used = datetime.fromisoformat(last_used_str)
        except (ValueError, TypeError):
            continue

        days_idle = (now - last_used).days
        if days_idle <= TRUST_DECAY_AFTER_DAYS:
            continue  # 还在 grace period 内

        decay_days = days_idle - TRUST_DECAY_AFTER_DAYS
        new_trust = max(TRUST_MIN, trust - decay_days * TRUST_DECAY_PER_DAY)
        if new_trust < trust:
            ml["trust_score"] = round(new_trust, 3)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            decayed.append({
                "ref": meta.get("l0", {}).get("ref", "?"),
                "seam_id": meta.get("l0", {}).get("seam_id", "?"),
                "trust_before": round(trust, 3),
                "trust_after": round(new_trust, 3),
                "days_idle": days_idle,
            })
    return decayed
