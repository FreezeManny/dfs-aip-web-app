import io
import zipfile

import db

PROFILE = {"name": "vfr", "flight_rule": "vfr", "filters": ["AD"], "enabled": True}


def make_profile(client, **over):
    assert client.post("/api/profiles", json={**PROFILE, **over}).status_code == 200


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


# ---------- documents / zip ----------

def test_document_list_download_and_zip(client, app_main):
    pdf_bytes = b"%PDF-1.4 sample content"
    (app_main.OUTPUT_DIR / "vfr_2026-11-12_ocr.pdf").write_bytes(pdf_bytes)

    docs = client.get("/api/documents").json()["documents"]
    assert len(docs) == 1
    d = docs[0]
    assert set(d) == {"id", "name", "profile", "airac_date", "size", "modified", "is_ocr"}
    assert d["is_ocr"] is True and d["airac_date"] == "2026-11-12"

    direct = client.post("/api/documents/download", json={"id": d["id"], "zip": False})
    assert direct.status_code == 200
    assert direct.headers["content-disposition"].startswith("attachment")
    assert direct.content == pdf_bytes

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
    assert client.get("/..%2Fdata/app.db").status_code == 404
    assert client.get("/..%5Cdata%5Capp.db").status_code == 404


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
