"""
SQLite persistence for profiles, run history and the document index.

The PDFs themselves stay on the filesystem; the files on disk are the source of
truth for documents and the ``documents`` table is only an index that is
reconciled against them (see :func:`reconcile_documents`).

The app runs a single uvicorn worker, so there is a single writer. Connections
are short-lived (one per operation) and use WAL + a busy timeout.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from rollover import flatten_output_dir, parse_document_name

logger = logging.getLogger(__name__)

_db_path: Optional[Path] = None

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    name         TEXT PRIMARY KEY,
    flight_rule  TEXT NOT NULL DEFAULT 'vfr',
    filters_json TEXT NOT NULL DEFAULT '[]',
    enabled      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    pdf_created INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    profile TEXT NOT NULL DEFAULT '',
    ts      TEXT NOT NULL,
    stage   TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    status  TEXT NOT NULL DEFAULT 'info'
);
CREATE INDEX IF NOT EXISTS idx_run_logs_run ON run_logs(run_id, id);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);

CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    profile    TEXT NOT NULL,
    airac_date TEXT NOT NULL,
    filename   TEXT NOT NULL,
    size       INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    is_ocr     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(profile, filename)
);
"""


def init(path: Path) -> None:
    """Point the module at ``path`` and create/upgrade the schema."""
    global _db_path
    _db_path = Path(path)
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(_SCHEMA)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a connection that commits on success, rolls back on error, always closes."""
    if _db_path is None:
        raise RuntimeError("db.init() has not been called")
    conn = sqlite3.connect(_db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============== Profiles ==============

def _profile_row(row: sqlite3.Row) -> dict:
    return {
        "name": row["name"],
        "flight_rule": row["flight_rule"],
        "filters": json.loads(row["filters_json"]),
        "enabled": bool(row["enabled"]),
    }


def list_profiles() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
    return [_profile_row(r) for r in rows]


def profile_exists(name: str) -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM profiles WHERE name = ?", (name,)).fetchone() is not None


def insert_profile(p: dict) -> bool:
    """Insert a profile. Returns False if the name is already taken."""
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO profiles (name, flight_rule, filters_json, enabled) VALUES (?, ?, ?, ?)",
                (p["name"], p["flight_rule"], json.dumps(p["filters"]), int(p["enabled"])),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def update_profile(name: str, p: dict) -> bool:
    """Replace profile ``name`` with ``p``. Returns False if it does not exist."""
    try:
        with connect() as conn:
            cur = conn.execute(
                "UPDATE profiles SET name = ?, flight_rule = ?, filters_json = ?, enabled = ? WHERE name = ?",
                (p["name"], p["flight_rule"], json.dumps(p["filters"]), int(p["enabled"]), name),
            )
            return cur.rowcount > 0
    except sqlite3.IntegrityError:
        # Renaming onto an existing profile name.
        return False


def delete_profile(name: str) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM profiles WHERE name = ?", (name,)).rowcount > 0


# ============== Runs ==============

def start_run(base_id: str) -> str:
    """Create a run row and return its id (``base_id``, suffixed if that id is already taken)."""
    with connect() as conn:
        run_id, n = base_id, 1
        while conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone():
            n += 1
            run_id = f"{base_id}_{n}"
        conn.execute(
            "INSERT INTO runs (id, started_at, status) VALUES (?, ?, 'running')",
            (run_id, _now()),
        )
    return run_id


def add_log(run_id: str, profile: str, stage: str, message: str, status: str) -> str:
    ts = _now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_logs (run_id, profile, ts, stage, message, status) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, profile, ts, stage, message, status),
        )
    return ts


def mark_pdf_created(run_id: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE runs SET pdf_created = 1 WHERE id = ?", (run_id,))


def _compute_status(conn: sqlite3.Connection, run_id: str) -> str:
    """'error' if a system-level error was logged or any profile's last log is an error."""
    if conn.execute(
        "SELECT 1 FROM run_logs WHERE run_id = ? AND profile = '' AND status = 'error' LIMIT 1",
        (run_id,),
    ).fetchone():
        return "error"
    rows = conn.execute(
        """
        SELECT l.status FROM run_logs l
        JOIN (SELECT profile, MAX(id) AS last_id FROM run_logs
              WHERE run_id = ? AND profile != '' GROUP BY profile) m
          ON l.id = m.last_id
        """,
        (run_id,),
    ).fetchall()
    return "error" if any(r["status"] == "error" for r in rows) else "success"


def finish_run(run_id: str) -> str:
    with connect() as conn:
        status = _compute_status(conn, run_id)
        conn.execute(
            "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
            (status, _now(), run_id),
        )
    return status


def fail_stale_runs() -> int:
    """Mark runs left 'running' by a crashed process as failed."""
    with connect() as conn:
        return conn.execute(
            "UPDATE runs SET status = 'error', finished_at = ? WHERE status = 'running'",
            (_now(),),
        ).rowcount


def list_runs() -> list[dict]:
    with connect() as conn:
        runs = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
        profiles: dict[str, list[str]] = {}
        for r in conn.execute(
            "SELECT run_id, profile FROM run_logs WHERE profile != '' GROUP BY run_id, profile ORDER BY MIN(id)"
        ).fetchall():
            profiles.setdefault(r["run_id"], []).append(r["profile"])
    return [
        {
            "id": r["id"],
            "timestamp": r["started_at"],
            "profiles": profiles.get(r["id"], []),
            "status": r["status"],
            "pdf_created": bool(r["pdf_created"]),
        }
        for r in runs
    ]


def get_run(run_id: str) -> Optional[dict]:
    with connect() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        logs: dict[str, list[dict]] = {}
        for l in conn.execute(
            "SELECT * FROM run_logs WHERE run_id = ? AND profile != '' ORDER BY id", (run_id,)
        ).fetchall():
            logs.setdefault(l["profile"], []).append(
                {
                    "timestamp": l["ts"],
                    "profile": l["profile"],
                    "stage": l["stage"],
                    "message": l["message"],
                    "status": l["status"],
                }
            )
    return {
        "id": run["id"],
        "timestamp": run["started_at"],
        "status": run["status"],
        "logs": logs,
        "metadata": {"pdf_created": bool(run["pdf_created"])},
    }


def last_log(run_id: str) -> Optional[dict]:
    with connect() as conn:
        l = conn.execute(
            "SELECT * FROM run_logs WHERE run_id = ? ORDER BY id DESC LIMIT 1", (run_id,)
        ).fetchone()
    if l is None:
        return None
    return {"profile": l["profile"], "stage": l["stage"], "message": l["message"], "status": l["status"]}


def prune_runs(retention_days: int) -> int:
    """Delete finished runs older than ``retention_days`` (their logs cascade)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    with connect() as conn:
        return conn.execute(
            "DELETE FROM runs WHERE started_at < ? AND status != 'running'", (cutoff,)
        ).rowcount


# ============== Documents (index over the output dir) ==============

def reconcile_documents(output_dir: Path) -> list[dict]:
    """Rebuild the document index from the files on disk and return it.

    A raw (non-OCR) PDF is hidden when its OCR counterpart exists: the raw file is only
    an intermediate and is removed on the next update.
    """
    flatten_output_dir(output_dir)
    parsed = {}
    for f in sorted(output_dir.glob("*.pdf")):
        info = parse_document_name(f.name)
        if info is not None:
            parsed[f.name] = (f, info)
    ocr_keys = {(info.stem, info.airac_date) for _, info in parsed.values() if info.is_ocr}

    found: dict[tuple[str, str], dict] = {}
    for name, (f, info) in parsed.items():
        if not info.is_ocr and (info.stem, info.airac_date) in ocr_keys:
            continue
        try:
            stat = f.stat()
        except FileNotFoundError:
            continue
        found[(info.stem, name)] = {
            "profile": info.stem,
            "airac_date": info.airac_date,
            "filename": name,
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "is_ocr": int(info.is_ocr),
        }

    with connect() as conn:
        existing = {
            (r["profile"], r["filename"]) for r in conn.execute("SELECT profile, filename FROM documents")
        }
        for key in existing - found.keys():
            conn.execute("DELETE FROM documents WHERE profile = ? AND filename = ?", key)
        for key, d in found.items():
            conn.execute(
                """
                INSERT INTO documents (profile, airac_date, filename, size, created_at, is_ocr)
                VALUES (:profile, :airac_date, :filename, :size, :created_at, :is_ocr)
                ON CONFLICT(profile, filename) DO UPDATE SET
                    airac_date = excluded.airac_date, size = excluded.size,
                    created_at = excluded.created_at, is_ocr = excluded.is_ocr
                """,
                d,
            )
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["filename"],
            "profile": r["profile"],
            "airac_date": r["airac_date"],
            "size": r["size"],
            "modified": r["created_at"],
            "is_ocr": bool(r["is_ocr"]),
        }
        for r in rows
    ]


def get_document(doc_id: int) -> Optional[dict]:
    with connect() as conn:
        r = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if r is None:
        return None
    return {
        "id": r["id"],
        "name": r["filename"],
        "profile": r["profile"],
        "airac_date": r["airac_date"],
        "size": r["size"],
        "modified": r["created_at"],
        "is_ocr": bool(r["is_ocr"]),
    }


# ============== One-time import of the legacy JSON files ==============

def _rename_migrated(path: Path) -> None:
    try:
        path.rename(path.with_name(path.name + ".migrated"))
    except OSError as e:
        logger.error(f"Could not rename {path}: {e}")


def migrate_json(profiles_file: Path, runs_dir: Path) -> None:
    """Import legacy ``profiles.json`` and ``runs/*.json`` and rename them ``*.migrated``.

    Idempotent: already-imported rows are skipped and migrated files are never read again.
    """
    if profiles_file.exists():
        try:
            for p in json.loads(profiles_file.read_text()):
                insert_profile(
                    {
                        "name": p["name"],
                        "flight_rule": p.get("flight_rule", "vfr"),
                        "filters": p.get("filters", []),
                        "enabled": p.get("enabled", True),
                    }
                )
            _rename_migrated(profiles_file)
            logger.info("Migrated profiles.json to SQLite")
        except Exception as e:
            logger.error(f"Failed to migrate {profiles_file}: {e}")

    if not runs_dir.is_dir():
        return
    migrated = 0
    for run_file in sorted(runs_dir.glob("*.json")):
        try:
            data = json.loads(run_file.read_text())
            run_id = data.get("id") or run_file.stem
            logs = data.get("logs", {})
            with connect() as conn:
                if conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone() is None:
                    conn.execute(
                        "INSERT INTO runs (id, started_at, status, pdf_created) VALUES (?, ?, 'running', ?)",
                        (
                            run_id,
                            data.get("timestamp") or _now(),
                            int(bool(data.get("metadata", {}).get("pdf_created", False))),
                        ),
                    )
                    for profile, entries in logs.items():
                        for m in entries:
                            conn.execute(
                                "INSERT INTO run_logs (run_id, profile, ts, stage, message, status) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    run_id,
                                    profile,
                                    m.get("timestamp", ""),
                                    m.get("stage", ""),
                                    m.get("message", ""),
                                    m.get("status", "info"),
                                ),
                            )
                    status = _compute_status(conn, run_id)
                    conn.execute(
                        "UPDATE runs SET status = ?, finished_at = started_at WHERE id = ?",
                        (status, run_id),
                    )
            _rename_migrated(run_file)
            migrated += 1
        except Exception as e:
            logger.error(f"Failed to migrate run {run_file}: {e}")
    if migrated:
        logger.info(f"Migrated {migrated} run(s) to SQLite")
