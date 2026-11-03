"""
Document naming and rollover helpers.

Documents are stored flat in ``output_dir`` as ``<profile>_<AIRAC date>.pdf`` (raw
intermediate) and ``<profile>_<AIRAC date>_ocr.pdf`` (the OCR'd result that is
actually kept). In-flight writes use a ``.partial`` suffix and are renamed on
success, so "file exists" always means "file is complete".

Everything here works on plain directories so it is easy to test.
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PARTIAL_SUFFIX = ".partial"

_NAME_RE = re.compile(r"^(?P<stem>.+)_(?P<date>\d{4}-\d{2}-\d{2})(?P<ocr>_ocr)?\.pdf$")


@dataclass(frozen=True)
class DocName:
    stem: str          # sanitized profile name
    airac_date: str    # YYYY-MM-DD
    is_ocr: bool


def parse_document_name(filename: str) -> Optional[DocName]:
    m = _NAME_RE.match(filename)
    if not m:
        return None
    return DocName(m["stem"], m["date"], bool(m["ocr"]))


def flatten_output_dir(output_dir: Path) -> None:
    """Move legacy ``<output_dir>/<profile>/*.pdf`` files into ``output_dir`` and remove empty dirs."""
    if not output_dir.is_dir():
        return
    for sub in sorted(p for p in output_dir.iterdir() if p.is_dir()):
        for f in sub.glob("*.pdf"):
            target = output_dir / f.name
            try:
                if not target.exists():
                    os.replace(f, target)
                else:
                    f.unlink(missing_ok=True)
            except OSError as e:
                logger.error(f"Could not move {f} to {target}: {e}")
        try:
            sub.rmdir()
        except OSError:
            pass


def flatten_cache_dir(cache_dir: Path) -> None:
    """Move legacy ``<cache_dir>/dfs-aip/*`` entries up into ``cache_dir``."""
    legacy = cache_dir / "dfs-aip"
    if not legacy.is_dir():
        return
    for item in legacy.iterdir():
        target = cache_dir / item.name
        try:
            if not target.exists():
                os.replace(item, target)
        except OSError as e:
            logger.error(f"Could not move {item} to {target}: {e}")
    try:
        legacy.rmdir()
    except OSError:
        pass


def drop_raw_with_ocr(output_dir: Path, stem: Optional[str] = None) -> list[Path]:
    """Delete raw PDFs whose OCR counterpart exists. Returns the deleted paths."""
    deleted = []
    for f in output_dir.glob("*.pdf"):
        info = parse_document_name(f.name)
        if info is None or info.is_ocr:
            continue
        if stem is not None and info.stem != stem:
            continue
        if (output_dir / f"{info.stem}_{info.airac_date}_ocr.pdf").is_file():
            f.unlink(missing_ok=True)
            deleted.append(f)
    return deleted


def prune_profile_dir(output_dir: Path, retain: int, stem: Optional[str] = None) -> list[Path]:
    """Keep the newest ``retain`` AIRAC cycles per profile in ``output_dir`` and delete the rest.

    The newest *complete* (OCR'd) document for a profile is never deleted, even if newer cycles
    exist that are incomplete, so a failed download can never leave the profile empty.
    Returns the deleted paths.
    """
    by_stem: dict[str, dict[str, list[tuple[Path, DocName]]]] = {}
    for f in output_dir.glob("*.pdf"):
        info = parse_document_name(f.name)
        if info is None:
            continue
        if stem is not None and info.stem != stem:
            continue
        by_stem.setdefault(info.stem, {}).setdefault(info.airac_date, []).append((f, info))

    deleted = []
    for by_date in by_stem.values():
        dates = sorted(by_date, reverse=True)
        keep = set(dates[: max(retain, 1)])
        if not any(any(i.is_ocr for _, i in by_date[d]) for d in keep):
            newest_complete = next(
                (d for d in dates if any(i.is_ocr for _, i in by_date[d])), None
            )
            if newest_complete is not None:
                keep.add(newest_complete)

        for d in dates:
            if d in keep:
                continue
            for f, _ in by_date[d]:
                f.unlink(missing_ok=True)
                deleted.append(f)
    return deleted


def cleanup_partials(*dirs: Path) -> list[Path]:
    """Remove leftover ``*.partial`` files (crashed or killed runs) below each dir."""
    deleted = []
    for base in dirs:
        if not base.is_dir():
            continue
        for f in base.rglob(f"*{PARTIAL_SUFFIX}"):
            if f.is_file():
                try:
                    f.unlink()
                    deleted.append(f)
                except OSError as e:
                    logger.error(f"Could not remove {f}: {e}")
    return deleted
