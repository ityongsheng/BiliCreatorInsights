"""Runtime configuration."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def db_path() -> Path:
    raw = os.environ.get("BILI_DB_PATH", str(ROOT / "data" / "insights.db"))
    return Path(raw)
