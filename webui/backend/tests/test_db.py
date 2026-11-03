import json
from datetime import datetime, timedelta, timezone

import db


def test_profile_crud():
    p = {"name": "vfr", "flight_rule": "vfr", "filters": ["AD", "GEN-*"], "enabled": True}
    assert db.insert_profile(p) is True
    assert db.insert_profile(p) is False  # duplicate name
    assert db.list_profiles() == [p]
    assert db.update_profile("vfr", {**p, "enabled": False}) is True
    assert db.list_profiles()[0]["enabled"] is False
    assert db.update_profile("nope", p) is False
    assert db.delete_profile("vfr") is True
    assert db.delete_profile("vfr") is False


def test_run_lifecycle_and_status():
    db.start_run("r1")
    db.add_log("r1", "", "system", "start", "info")
    db.add_log("r1", "a", "toc_fetch", "failed", "error")
    db.add_log("r1", "b", "complete", "done", "success")
    assert db.list_runs()[0]["status"] == "running"
    assert db.finish_run("r1") == "error"

    run = db.get_run("r1")
    assert set(run["logs"]) == {"a", "b"}  # system logs are not exposed per profile
    assert run["status"] == "error"
    assert db.list_runs()[0]["profiles"] == ["a", "b"]
    assert db.get_run("missing") is None


def test_status_success_when_error_was_recovered_within_profile():
    db.start_run("r2")
    db.add_log("r2", "a", "x", "oops", "error")
    db.add_log("r2", "a", "complete", "ok", "success")
    assert db.finish_run("r2") == "success"


def test_system_error_marks_run_failed():
    db.start_run("r3")
    db.add_log("r3", "", "system", "Insufficient disk space", "error")
    assert db.finish_run("r3") == "error"


def test_fail_stale_runs():
    db.start_run("r4")
    assert db.fail_stale_runs() == 1
    assert db.get_run("r4")["status"] == "error"


def test_prune_runs_cascades_logs():
    db.start_run("old")
    db.add_log("old", "a", "x", "m", "info")
    db.finish_run("old")
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE runs SET started_at = ? WHERE id = 'old'", (old,))
    db.start_run("new")
    db.finish_run("new")
    assert db.prune_runs(180) == 1
    assert [r["id"] for r in db.list_runs()] == ["new"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM run_logs").fetchone()[0] == 0


def test_reconcile_hides_raw_when_ocr_exists_and_drops_stale_rows(tmp_path):
    (tmp_path / "vfr_2026-10-15.pdf").write_bytes(b"raw")
    (tmp_path / "vfr_2026-10-15_ocr.pdf").write_bytes(b"ocr!")
    (tmp_path / "vfr_2026-11-12.pdf").write_bytes(b"raw-only")
    (tmp_path / "junk.txt").write_text("x")

    docs = db.reconcile_documents(tmp_path)
    assert sorted(d["name"] for d in docs) == ["vfr_2026-10-15_ocr.pdf", "vfr_2026-11-12.pdf"]
    d = next(d for d in docs if d["is_ocr"])
    assert d["profile"] == "vfr" and d["airac_date"] == "2026-10-15" and isinstance(d["id"], int)
    assert d["size"] == 4
    assert db.get_document(d["id"]) == d
    assert db.get_document(999999) is None

    (tmp_path / "vfr_2026-11-12.pdf").unlink()
    assert [d["name"] for d in db.reconcile_documents(tmp_path)] == ["vfr_2026-10-15_ocr.pdf"]


def test_airac_date_with_underscore_in_profile_name(tmp_path):
    prof = tmp_path / "my_profile"
    prof.mkdir()
    (prof / "my_profile_2026-11-12_ocr.pdf").write_bytes(b"x")
    assert db.reconcile_documents(tmp_path)[0]["airac_date"] == "2026-11-12"


def test_migrate_json_is_idempotent(tmp_path):
    profiles_file = tmp_path / "profiles.json"
    profiles_file.write_text(json.dumps([{"name": "old", "flight_rule": "ifr", "filters": ["ENR"], "enabled": False}]))
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "20260101_020000.json").write_text(
        json.dumps(
            {
                "id": "20260101_020000",
                "timestamp": "2026-01-01T01:00:00+00:00",
                "logs": {"old": [{"timestamp": "t", "profile": "old", "stage": "s", "message": "m", "status": "error"}]},
                "metadata": {"pdf_created": True},
            }
        )
    )
    (runs_dir / "broken.json").write_text("{not json")

    db.migrate_json(profiles_file, runs_dir)
    db.migrate_json(profiles_file, runs_dir)  # second call must not duplicate or fail

    assert db.list_profiles() == [{"name": "old", "flight_rule": "ifr", "filters": ["ENR"], "enabled": False}]
    runs = db.list_runs()
    assert len(runs) == 1 and runs[0]["status"] == "error" and runs[0]["pdf_created"] is True
    assert len(db.get_run("20260101_020000")["logs"]["old"]) == 1
    assert (tmp_path / "profiles.json.migrated").exists() and not profiles_file.exists()
    assert (runs_dir / "20260101_020000.json.migrated").exists()
    assert (runs_dir / "broken.json").exists()  # unreadable files are left alone


def test_update_log_in_place():
    db.start_run("r_progress")
    log_id = db.add_log("r_progress", "vfr", "ocr", "Processing 0 / 10 pages (0%)", "info")
    db.update_log(log_id, "Processing 5 / 10 pages (50%)", "info")
    db.update_log(log_id, "Processed 10 / 10 pages (100%)", "info")
    entries = db.get_run("r_progress")["logs"]["vfr"]
    assert len(entries) == 1
    assert entries[0]["message"] == "Processed 10 / 10 pages (100%)"
