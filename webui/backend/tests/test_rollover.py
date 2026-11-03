from rollover import (
    PARTIAL_SUFFIX,
    cleanup_partials,
    drop_raw_with_ocr,
    parse_document_name,
    prune_profile_dir,
)


def touch(d, *names):
    for n in names:
        (d / n).write_bytes(b"x")


def names(d):
    return sorted(p.name for p in d.iterdir())


def test_parse_document_name():
    info = parse_document_name("My_Profile_2026-11-12_ocr.pdf")
    assert (info.stem, info.airac_date, info.is_ocr) == ("My_Profile", "2026-11-12", True)
    info = parse_document_name("VFR_2026-11-12.pdf")
    assert (info.stem, info.airac_date, info.is_ocr) == ("VFR", "2026-11-12", False)
    assert parse_document_name("notes.pdf") is None
    assert parse_document_name("VFR_2026-11-12.pdf.partial") is None


def test_prune_keeps_newest_n_cycles(tmp_path):
    touch(
        tmp_path,
        "P_2026-09-17_ocr.pdf", "P_2026-10-15_ocr.pdf", "P_2026-11-12_ocr.pdf", "P_2026-08-20_ocr.pdf",
    )
    deleted = prune_profile_dir(tmp_path, retain=2)
    assert names(tmp_path) == ["P_2026-10-15_ocr.pdf", "P_2026-11-12_ocr.pdf"]
    assert len(deleted) == 2


def test_prune_never_deletes_newest_complete_document(tmp_path):
    # The two newest cycles only have raw PDFs (e.g. OCR failed); the old OCR'd one must survive.
    touch(tmp_path, "P_2026-09-17_ocr.pdf", "P_2026-10-15.pdf", "P_2026-11-12.pdf", "P_2026-08-20_ocr.pdf")
    prune_profile_dir(tmp_path, retain=2)
    assert "P_2026-09-17_ocr.pdf" in names(tmp_path)
    assert "P_2026-08-20_ocr.pdf" not in names(tmp_path)
    assert "P_2026-11-12.pdf" in names(tmp_path)


def test_prune_ignores_foreign_files(tmp_path):
    touch(tmp_path, "readme.txt", "P_2026-11-12_ocr.pdf")
    prune_profile_dir(tmp_path, retain=1)
    assert names(tmp_path) == ["P_2026-11-12_ocr.pdf", "readme.txt"]


def test_drop_raw_only_when_ocr_exists(tmp_path):
    touch(tmp_path, "P_2026-10-15.pdf", "P_2026-10-15_ocr.pdf", "P_2026-11-12.pdf")
    deleted = drop_raw_with_ocr(tmp_path)
    assert [p.name for p in deleted] == ["P_2026-10-15.pdf"]
    assert names(tmp_path) == ["P_2026-10-15_ocr.pdf", "P_2026-11-12.pdf"]


def test_cleanup_partials(tmp_path):
    sub = tmp_path / "prof"
    sub.mkdir()
    touch(sub, f"P_2026-11-12.pdf{PARTIAL_SUFFIX}", "P_2026-11-12_ocr.pdf")
    cleanup_partials(tmp_path, tmp_path / "missing")
    assert names(sub) == ["P_2026-11-12_ocr.pdf"]
