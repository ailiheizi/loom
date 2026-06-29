"""统一路径解析：兼容"仓库内运行"和"uvx/pip 安装后运行"两种场景。

- 开发(仓库内)：core.json 在 ../core/loom.core.json
- 发布(uvx 装)：打进包的 loom_seed/loom.core.json
优先用包内副本(发布场景),回退仓库路径(开发场景)。
"""
from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent          # platform/
_REPO_ROOT = _HERE.parent                         # 仓库根(开发时)
_SEED_DIR = _HERE / "loom_seed"                   # 包内数据


def core_json_path() -> Path:
    """loom.core.json 路径：包内优先,回退仓库。"""
    packaged = _SEED_DIR / "loom.core.json"
    if packaged.exists():
        return packaged
    return _REPO_ROOT / "core" / "loom.core.json"


def seed_data_path() -> Path:
    """seed_data.json 路径(只在包内)。"""
    return _SEED_DIR / "seed_data.json"


def base_dir() -> Path:
    """t3-base 源目录：包内优先(loom_seed/t3-base),回退仓库(core/t3-base)。"""
    packaged = _SEED_DIR / "t3-base"
    if packaged.exists():
        return packaged
    return _REPO_ROOT / "core" / "t3-base"
