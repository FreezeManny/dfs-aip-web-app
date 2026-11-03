import asyncio
import zipfile
import io

import db

PROFILE = {"name": "vfr", "flight_rule": "vfr", "filters": ["AD"], "enabled": True}


def make_profile(client, **over):
    assert client.post("/api/profiles", json={**PROFILE, **over}).status_code == 200


def run(app_main, **kw):
    asyncio.run(app_main.run_update(**kw))


def out(app_main, name=""):
    return app_main.OUTPUT_DIR / name


def files(app_main):
    return sorted(p.name for p in app_main.OUTPUT_DIR.iterdir())


# ---------- profiles ----------

def test_profile_api_shapes(client):
    make_profile(client)
    assert client.post("/api/profiles", json=PROFILE).status_code == 400
    assert client.get("/api/profiles").json() == {"profiles": [PROFILE]}
    assert client.put("/api/profiles/vfr", json={**PROFILE, "enabled": False}).status_code == 200
    assert client.put("/api/profiles/nope", json=PROFILE).status_code == 404
    assert client.post("/api/profiles", json={**PROFILE, "name": "bad name"}).status_code == 422
    assert client.delete("/api/profiles/vfr").status_code == 200
    assert client.delete("/api/profiles/vfr").status_code == 404


# ---------- update pipeline ----------

def test_update_creates_ocr_and_deletes_raw(client, app_main):
    make_profile(client)
    run(app_main)
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf"]

    runs = client.get("/api/runs").json()["runs"]
    assert len(runs) == 1 and runs[0]["status"] == "success" and runs[0]["pdf_created"] is True
    detail = client.get(f"/api/runs/{runs[0]['id']}").json()
    assert detail["logs"]["vfr"][-1]["stage"] == "complete"
    assert app_main._current_run_id is None and app_main._update_lock_file is None


def test_second_run_is_noop_when_ocr_exists(client, app_main, monkeypatch, tmp_path):
    make_profile(client)
    run(app_main)
    log = tmp_path / "aip.log"
    monkeypatch.setenv("FAKE_AIP_LOG", str(log))
    run(app_main)
    assert "pdf" not in log.read_text()  # no regeneration
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf"]


def test_failed_ocr_keeps_raw_and_old_cycle(client, app_main, monkeypatch):
    make_profile(client)
    run(app_main)  # cycle 2026-11-12 complete
    monkeypatch.setenv("FAKE_AIRAC", "2026-12-10")
    monkeypatch.setenv("FAKE_OCR_FAIL", "1")
    run(app_main)
    # new raw is kept for a retry, no partial left behind, old complete doc untouched
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf", "vfr_2026-12-10.pdf"]
    assert client.get("/api/runs").json()["runs"][0]["status"] == "error"

    monkeypatch.delenv("FAKE_OCR_FAIL")
    run(app_main)  # resumes OCR from the kept raw file
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf", "vfr_2026-12-10_ocr.pdf"]


def test_failed_pdf_leaves_no_partial(client, app_main, monkeypatch):
    make_profile(client)
    monkeypatch.setenv("FAKE_AIP_PDF_FAIL", "1")
    run(app_main)
    assert files(app_main) == []


def test_rollover_keeps_newest_cycles(client, app_main, monkeypatch):
    make_profile(client)
    for airac in ("2026-10-15", "2026-11-12", "2026-12-10", "2027-01-07"):
        monkeypatch.setenv("FAKE_AIRAC", airac)
        run(app_main)
    assert files(app_main) == ["vfr_2026-12-10_ocr.pdf", "vfr_2027-01-07_ocr.pdf"]


def test_upgrade_drops_legacy_raw_next_to_ocr(client, app_main):
    make_profile(client)
    d = app_main.OUTPUT_DIR
    (d / "vfr_2026-11-12.pdf").write_bytes(b"raw")
    (d / "vfr_2026-11-12_ocr.pdf").write_bytes(b"ocr")
    run(app_main)
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf"]


def test_force_refreshes_and_replaces_atomically(client, app_main, monkeypatch, tmp_path):
    make_profile(client)
    run(app_main)
    before = out(app_main, "vfr_2026-11-12_ocr.pdf").read_bytes()
    log = tmp_path / "aip.log"
    monkeypatch.setenv("FAKE_AIP_LOG", str(log))
    monkeypatch.setenv("FAKE_AIRAC", "2026-11-12")  # content marker differs from the first build
    run(app_main, force=True)
    calls = log.read_text().splitlines()
    assert any(c.startswith("toc fetch") and "--refresh" in c for c in calls)
    assert any(c.startswith("pdf") and "--refresh" in c for c in calls)
    assert out(app_main, "vfr_2026-11-12_ocr.pdf").read_bytes() != before
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf"]


def test_failed_force_keeps_existing_document(client, app_main, monkeypatch):
    make_profile(client)
    run(app_main)
    before = out(app_main, "vfr_2026-11-12_ocr.pdf").read_bytes()
    monkeypatch.setenv("FAKE_AIP_PDF_FAIL", "1")
    run(app_main, force=True)
    assert out(app_main, "vfr_2026-11-12_ocr.pdf").read_bytes() == before
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf"]


def test_plain_update_does_not_pass_refresh(client, app_main, monkeypatch, tmp_path):
    make_profile(client)
    log = tmp_path / "aip.log"
    monkeypatch.setenv("FAKE_AIP_LOG", str(log))
    run(app_main)
    assert "--refresh" not in log.read_text()


# ---------- trigger / status ----------

def test_trigger_and_status_endpoints(client, app_main):
    make_profile(client)
    assert client.get("/api/update/status").json() == {"running": False, "run_id": None}
    assert client.post("/api/update/run?profile=nope").status_code == 404

    app_main._acquire_update_lock()
    try:
        assert client.get("/api/update/status").json()["running"] is True
        r = client.post("/api/update/run")
        assert r.status_code == 409 and r.json() == {"status": "already_running"}
    finally:
        app_main._release_update_lock()

    r = client.post("/api/update/run?force=true")  # TestClient runs background tasks before returning
    assert r.status_code == 200 and r.json() == {"status": "started"}
    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf"]


# ---------- documents / zip ----------

def test_document_list_download_and_zip(client, app_main):
    make_profile(client)
    run(app_main)
    docs = client.get("/api/documents").json()["documents"]
    assert len(docs) == 1
    d = docs[0]
    assert set(d) == {"id", "name", "profile", "airac_date", "size", "modified", "is_ocr"}
    assert d["is_ocr"] is True and d["airac_date"] == "2026-11-12"

    direct = client.post("/api/documents/download", json={"id": d["id"], "zip": False})
    assert direct.status_code == 200
    assert direct.headers["content-disposition"].startswith("attachment")

    z = client.post("/api/documents/download", json={"id": d["id"], "zip": True})
    assert z.status_code == 200
    assert z.headers["content-type"] == "application/zip"
    assert z.headers["content-disposition"].startswith("attachment")
    assert "vfr_2026-11-12_ocr.zip" in z.headers["content-disposition"]
    assert z.headers["content-length"] == str(len(z.content))  # not gzipped / chunked
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        assert zf.namelist() == ["vfr_2026-11-12_ocr.pdf"]
        assert zf.read("vfr_2026-11-12_ocr.pdf") == direct.content
    assert list(app_main.TMP_DIR.iterdir()) == []  # temp zip removed after the response

    assert client.delete(f"/api/documents/{d['id']}").status_code == 200
    assert client.get("/api/documents").json()["documents"] == []


def test_zip_rejects_traversal_and_missing(client, app_main):
    (app_main.OUTPUT_DIR / "vfr").mkdir()
    assert client.post("/api/documents/download", json={"id": 999999, "zip": True}).status_code == 404
    assert client.get("/api/documents/999999/zip").status_code == 404
    assert client.get("/api/documents/..%2Fdata/app.db/zip").status_code in (400, 404, 422)
    assert client.get("/api/documents/vfr/..%2F..%2Fdata%2Fapp.db/zip").status_code in (400, 404, 422)
    assert list(app_main.TMP_DIR.iterdir()) == []


# ---------- static frontend ----------

def test_spa_serving(client):
    index = client.get("/some/deep/link")
    assert index.status_code == 200 and "spa" in index.text
    assert index.headers["cache-control"] == "no-cache"
    asset = client.get("/assets/app-abc123.js")
    assert "immutable" in asset.headers["cache-control"]
    miss = client.get("/api/nope")
    assert miss.status_code == 404 and miss.headers["content-type"].startswith("application/json")
    assert "spa" not in miss.text


def test_gzip_for_json_but_not_documents(client, app_main):
    make_profile(client, filters=["A" * 150] * 20)
    big = client.get("/api/profiles", headers={"accept-encoding": "gzip"})
    assert big.headers.get("content-encoding") == "gzip"


# ---------- lifespan housekeeping ----------

def test_startup_housekeeping(app_main):
    from fastapi.testclient import TestClient

    d = app_main.OUTPUT_DIR / "vfr"
    d.mkdir()
    (d / "vfr_2026-11-12.pdf.partial").write_bytes(b"half")
    (d / "vfr_2026-11-12_ocr.pdf").write_bytes(b"legacy-sub")
    (app_main.TMP_DIR / "leftover.zip").write_bytes(b"x")
    db.start_run("crashed")
    (app_main.DATA_DIR / "profiles.json").write_text('[{"name": "legacy"}]')

    with TestClient(app_main.app):
        pass

    assert files(app_main) == ["vfr_2026-11-12_ocr.pdf"]
    assert list(app_main.TMP_DIR.iterdir()) == []
    assert db.get_run("crashed")["status"] == "error"
    assert [p["name"] for p in db.list_profiles()] == ["legacy"]
