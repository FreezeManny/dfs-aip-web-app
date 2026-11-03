import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

# Must be set before `main` is imported: it reads its settings and creates its dirs at import.
ROOT = Path(tempfile.mkdtemp(prefix="aip-backend-test-"))
os.environ.update(
    OUTPUT_DIR=str(ROOT / "output"),
    CACHE_DIR=str(ROOT / "cache"),
    DATA_DIR=str(ROOT / "data"),
    STATIC_DIR=str(ROOT / "static"),
    MIN_FREE_SPACE_GB="0.1",
    RETAIN_CYCLES="2",
)
(ROOT / "static" / "assets").mkdir(parents=True)
(ROOT / "static" / "index.html").write_text("<html>spa</html>")
(ROOT / "static" / "assets" / "app-abc123.js").write_text("console.log(1)")

sys.path.insert(0, str(BACKEND))

import db  # noqa: E402
import main  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    """Empty DB tables and output dir before each test."""
    with db.connect() as conn:
        for table in ("run_logs", "runs", "profiles", "documents"):
            conn.execute(f"DELETE FROM {table}")
    for d in (main.OUTPUT_DIR, main.TMP_DIR):
        for item in d.iterdir():
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    yield


@pytest.fixture
def app_main():
    return main


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(main.app)
