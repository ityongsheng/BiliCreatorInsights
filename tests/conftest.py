import os
import tempfile
from pathlib import Path

_dir = Path(tempfile.mkdtemp(prefix="bili-test-"))
os.environ["BILI_DB_PATH"] = str(_dir / "test.db")

import pytest


@pytest.fixture(autouse=True)
def fresh_db():
    from app.db import init_db, reset_engine

    reset_engine()
    base = Path(os.environ["BILI_DB_PATH"])
    for path in (base, Path(str(base) + "-wal"), Path(str(base) + "-shm")):
        if path.exists():
            path.unlink()
    init_db()
    yield
    reset_engine()
