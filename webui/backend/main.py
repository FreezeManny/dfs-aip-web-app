"""
DFS AIP Updater - FastAPI Backend (see db.py for persistence, rollover.py for retention)
"""

import asyncio
import fcntl
import logging
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import db
import rollover

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============== Config ==============

class Settings(BaseSettings):
    """Application settings from environment variables"""
    output_dir: Path = Path("/app/output")
    cache_dir: Path = Path("/app/cache")
    data_dir: Path = Path("/app/data")
    
    auto_update_enabled: bool = False
    auto_update_hour: int = Field(default=2, ge=0, lt=24)
    auto_update_minute: int = Field(default=0, ge=0, lt=60)
    
    ocr_jobs: int = Field(default_factory=lambda: max(2, (os.cpu_count() or 2) // 2), ge=1)
    
    # Minimum free disk space in GB before generating PDFs
    min_free_space_gb: float = Field(default=1.0, ge=0.1)

    # Rollover: number of newest AIRAC cycles kept per profile, and how long run history is kept
    retain_cycles: int = Field(default=2, ge=1)
    run_retention_days: int = Field(default=180, ge=1)

    # Comma-separated list of extra allowed CORS origins. The UI is served from the same
    # origin as the API, so this is only needed for non-standard setups.
    cors_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()

OUTPUT_DIR = settings.output_dir
CACHE_DIR = settings.cache_dir
DATA_DIR = settings.data_dir
DB_FILE = DATA_DIR / "app.db"
PROFILES_FILE = DATA_DIR / "profiles.json"  # legacy, imported into SQLite on first start
RUNS_DIR = DATA_DIR / "runs"                # legacy, imported into SQLite on first start
LOCK_FILE = DATA_DIR / "update.lock"
TMP_DIR = DATA_DIR / "tmp"

# External tools (overridable for tests)
AIP_SCRIPT = os.environ.get("AIP_SCRIPT", "/app/aip.py")
OCRMYPDF_BIN = os.environ.get("OCRMYPDF_BIN", "ocrmypdf")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

db.init(DB_FILE)

# ============== Scheduler ==============

scheduler = AsyncIOScheduler()

async def scheduled_update():
    """Run automatic update (called by scheduler)"""
    logger.info("Starting scheduled automatic update")
    try:
        await run_update()
    except HTTPException as e:
        if e.status_code == 409:
            logger.warning("Scheduled update skipped: update already running")
        else:
            logger.error(f"Scheduled update failed: {e.detail}")
    except Exception as e:
        logger.error(f"Scheduled update failed: {str(e)}")

# ============== App ==============

def _housekeeping_on_startup():
    """Import legacy JSON state, and clean up after a crashed/killed previous process."""
    db.migrate_json(PROFILES_FILE, RUNS_DIR)
    stale = db.fail_stale_runs()
    if stale:
        logger.warning(f"Marked {stale} interrupted run(s) as failed")
    rollover.cleanup_partials(OUTPUT_DIR)
    rollover.flatten_output_dir(OUTPUT_DIR)
    rollover.flatten_cache_dir(CACHE_DIR)
    for leftover in TMP_DIR.iterdir():
        try:
            if leftover.is_file():
                leftover.unlink()
        except OSError as e:
            logger.error(f"Could not remove {leftover}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _housekeeping_on_startup()
    if settings.auto_update_enabled:
        logger.info(f"Auto-update enabled: scheduled for {settings.auto_update_hour:02d}:{settings.auto_update_minute:02d} daily")
        scheduler.add_job(
            scheduled_update,
            CronTrigger(hour=settings.auto_update_hour, minute=settings.auto_update_minute),
            id="auto_update",
            name="Automatic AIP Update",
            replace_existing=True,
        )
        scheduler.start()
    else:
        logger.info("Auto-update disabled")
    
    yield
    
    # Shutdown
    if scheduler.running:
        scheduler.shutdown()


class SelectiveGZipMiddleware:
    """GZip for the SPA assets and JSON API, but never for document downloads.

    PDFs and ZIPs are already compressed; gzipping them wastes CPU and drops Content-Length,
    which large downloads on flaky mobile connections rely on.
    """

    def __init__(self, app):
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not scope["path"].startswith("/api/documents/"):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)


app = FastAPI(title="DFS AIP Updater", version="3.0.0", lifespan=lifespan)
# The UI is served from the same origin as the API, so CORS is only enabled on request.
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SelectiveGZipMiddleware)

_update_lock_file: Optional[object] = None
_current_run_id: Optional[str] = None  # id of the run in progress, if any


def _log_progress(profile: str, stage: str, message: str = "", status: str = "info"):
    """Log progress message with profile context (persisted live to the current run)"""
    # status: "info", "warning", "error", "success"
    if _current_run_id is not None:
        try:
            db.add_log(_current_run_id, profile or "", stage, message, status)
        except Exception:
            logger.exception("Failed to persist run log")
    
    logger.info(f"[{profile}] {stage}: {message}")


# ============== Models ==============

class ProfileData(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    flight_rule: str = Field(default="vfr", pattern=r'^(vfr|ifr)$')
    filters: list[str] = Field(default=[], max_length=100)
    enabled: bool = True
    
    @field_validator('filters')
    @classmethod
    def validate_filters(cls, v: list[str]) -> list[str]:
        """Validate filter format to prevent command injection"""
        for filter_str in v:
            # Only allow: alphanumeric, dash, underscore, forward slash, period, asterisk
            # This matches typical AIP section patterns like "AD-2.EDDF" or "GEN-*"
            if not re.match(r'^[a-zA-Z0-9/_.*-]+$', filter_str):
                raise ValueError(f'Invalid filter format: {filter_str}. Only alphanumeric, dash, underscore, slash, period, and asterisk allowed.')
            if len(filter_str) > 200:
                raise ValueError(f'Filter too long: {filter_str}')
        return v


class CleanupRequest(BaseModel):
    delete_cache: bool = False
    delete_output: bool = False


class DocumentDownloadRequest(BaseModel):
    id: int
    zip: bool = False
    preview: bool = False


# ============== Helpers ==============

def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _acquire_update_lock() -> object:
    """Acquire exclusive lock for update process. Raises HTTPException if already locked."""
    global _update_lock_file
    
    if _update_lock_file is not None:
        raise HTTPException(409, "Update already in progress")
    
    lock_file = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n")
        lock_file.flush()
        _update_lock_file = lock_file
        return lock_file
    except BlockingIOError:
        lock_file.close()
        raise HTTPException(409, "Update already in progress (locked by another process)")
    except Exception as e:
        lock_file.close()
        raise HTTPException(500, f"Failed to acquire lock: {str(e)}")


def _release_update_lock():
    """Release the update lock"""
    global _update_lock_file
    
    if _update_lock_file is not None:
        try:
            fcntl.flock(_update_lock_file.fileno(), fcntl.LOCK_UN)
            _update_lock_file.close()
        except Exception as e:
            logger.error(f"Failed to release lock cleanly: {e}")
        finally:
            _update_lock_file = None
            # Clean up lock file
            try:
                LOCK_FILE.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Failed to remove lock file: {e}")


def _check_disk_space() -> tuple[bool, float]:
    """Check if sufficient disk space is available.
    
    Returns:
        (has_space, free_gb): True if enough space, and the amount of free space in GB
    """
    try:
        stat = shutil.disk_usage(OUTPUT_DIR)
        free_gb = stat.free / (1024 ** 3)
        has_space = free_gb >= settings.min_free_space_gb
        return has_space, free_gb
    except Exception as e:
        logger.error(f"Failed to check disk space: {e}")
        return True, 0.0  # Assume space is available if check fails


def _validate_path(base_dir: Path, *parts: str) -> Path:
    """Validate that the requested path is within base_dir and return resolved path.
    
    Raises HTTPException if path traversal is detected or path is invalid.
    """
    try:
        # Build the requested path
        requested_path = base_dir.joinpath(*parts)
        # Resolve to absolute path (handles .. and symlinks)
        resolved_path = requested_path.resolve()
        resolved_base = base_dir.resolve()
        
        # Check if resolved path is within base directory
        if not resolved_path.is_relative_to(resolved_base):
            raise HTTPException(400, "Invalid path: access denied")
        
        # Additional check: ensure no path component is "." or ".."
        for part in parts:
            if part in ("", ".", "..") or "/" in part or "\\" in part:
                raise HTTPException(400, "Invalid path: illegal characters")
        
        return resolved_path
    except (ValueError, OSError) as e:
        raise HTTPException(400, f"Invalid path: {str(e)}")


# ============== Profile Endpoints ==============

@app.get("/api/profiles")
def list_profiles():
    return {"profiles": db.list_profiles()}


@app.post("/api/profiles")
def create_profile(data: ProfileData):
    if not db.insert_profile(data.model_dump()):
        raise HTTPException(400, f"Profile '{data.name}' already exists")
    return {"status": "ok"}


@app.put("/api/profiles/{name}")
def update_profile(name: str, data: ProfileData):
    if not db.update_profile(name, data.model_dump()):
        if db.profile_exists(name):
            raise HTTPException(400, f"Profile '{data.name}' already exists")
        raise HTTPException(404, "Profile not found")
    return {"status": "ok"}


@app.delete("/api/profiles/{name}")
def delete_profile(name: str):
    if not db.delete_profile(name):
        raise HTTPException(404, "Profile not found")
    return {"status": "ok"}


# ============== Update ==============

async def _generate_raw_pdf(profile: dict, raw_path: Path, cache_path: str, force: bool) -> bool:
    """Download pages and build the raw PDF. Written to a .partial file, renamed on success."""
    name = profile["name"]
    partial = raw_path.with_name(raw_path.name + rollover.PARTIAL_SUFFIX)
    partial.unlink(missing_ok=True)

    _log_progress(name, "pdf_gen", "Generating PDF (forced refresh)" if force else "Generating PDF", "info")
    filter_args = [arg for f in profile.get("filters", []) for arg in ["-f", f]]
    refresh_args = ["--refresh"] if force else []
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", AIP_SCRIPT, "--cache", cache_path,
        "pdf", "--output", str(partial),
        "summary", f"--{profile['flight_rule']}", *filter_args, *refresh_args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stderr_task = asyncio.create_task(proc.stderr.read())

    # Stream stdout to show page downloads
    page_count = 0
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        page_name = line.decode().strip()
        if page_name:
            page_count += 1
            _log_progress(name, "pdf_gen", f"Downloaded page {page_count}: {page_name}", "info")

    await proc.wait()
    stderr = await stderr_task

    if proc.returncode == 0 and partial.exists():
        os.replace(partial, raw_path)
        size_mb = raw_path.stat().st_size / (1024 * 1024)
        _log_progress(name, "pdf_gen", f"PDF complete ({size_mb:.1f} MB)", "success")
        return True

    partial.unlink(missing_ok=True)
    _log_progress(name, "pdf_gen", f"Failed: {stderr.decode()[-1500:]}", "error")
    return False


async def _ocr_pdf(name: str, raw_path: Path, ocr_path: Path) -> bool:
    """OCR ``raw_path``. Written to a .partial file, atomically replacing ``ocr_path`` on success."""
    partial = ocr_path.with_name(ocr_path.name + rollover.PARTIAL_SUFFIX)
    partial.unlink(missing_ok=True)

    _log_progress(name, "ocr", f"Starting OCR: {raw_path.name} -> {ocr_path.name}", "info")
    _log_progress(name, "ocr", f"Input PDF size: {raw_path.stat().st_size / (1024 * 1024):.1f} MB", "info")
    _log_progress(name, "ocr", f"Using {settings.ocr_jobs} parallel worker(s)", "info")

    proc = await asyncio.create_subprocess_exec(
        OCRMYPDF_BIN, "--jobs", str(settings.ocr_jobs), "--verbose", "1", str(raw_path), str(partial),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout_task = asyncio.create_task(proc.stdout.read())

    # Stream stderr to capture OCR progress
    stderr_lines = []
    while True:
        line = await proc.stderr.readline()
        if not line:
            break
        decoded = line.decode().strip()
        stderr_lines.append(decoded)
        if decoded:
            _log_progress(name, "ocr", decoded, "info")
    stdout = await stdout_task
    await proc.wait()

    if proc.returncode == 0 and partial.exists():
        os.replace(partial, ocr_path)
        ocr_size_mb = ocr_path.stat().st_size / (1024 * 1024)
        _log_progress(name, "ocr", f"OCR complete ({ocr_size_mb:.1f} MB)", "success")
        return True

    partial.unlink(missing_ok=True)
    _log_progress(name, "ocr", f"Process exited with code {proc.returncode}", "error")
    _log_progress(name, "ocr", f"Last 10 stderr lines: {stderr_lines[-10:]}", "error")
    if stdout:
        _log_progress(name, "ocr", f"stdout: {stdout.decode()[:500]}", "error")
    return False


async def run_update(profile_name: str | None = None, force: bool = False):
    """Update all enabled profiles (or just ``profile_name``).

    With ``force`` the AIP cache is bypassed and existing documents are rebuilt; the old
    document stays in place until the new one is complete.
    """
    global _current_run_id

    # Acquire lock to prevent concurrent updates
    _acquire_update_lock()

    try:
        run_id = db.start_run(datetime.now().strftime("%Y%m%d_%H%M%S"))
    except Exception:
        _release_update_lock()
        raise
    _current_run_id = run_id
    
    try:
        _log_progress("", "system", "Starting forced update process" if force else "Starting update process", "info")
        
        # Check disk space
        has_space, free_gb = _check_disk_space()
        if not has_space:
            error_msg = f"Insufficient disk space: {free_gb:.2f} GB free, {settings.min_free_space_gb:.2f} GB required"
            _log_progress("", "system", error_msg, "error")
            raise HTTPException(507, error_msg)
        
        _log_progress("", "system", f"Disk space: {free_gb:.2f} GB available", "info")
        profiles = [p for p in db.list_profiles() if p.get("enabled", True)]
        if profile_name:
            profiles = [p for p in profiles if p["name"] == profile_name]

        _log_progress("", "system", f"Found {len(profiles)} profile(s) to process", "info")

        for profile in profiles:
            profile_name_str = profile['name']
            try:
                _log_progress(profile_name_str, "init", "Starting profile processing", "info")
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                cache_path = str(CACHE_DIR)

                # Fetch TOC
                _log_progress(profile_name_str, "toc_fetch", f"Fetching TOC ({profile['flight_rule'].upper()})", "info")
                refresh_args = ["--refresh"] if force else []
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, AIP_SCRIPT, "--cache", cache_path,
                    "toc", "fetch", f"--{profile['flight_rule']}", *refresh_args,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    _log_progress(profile_name_str, "toc_fetch", f"Failed: {stderr.decode()[-1500:]}", "error")
                    continue
                _log_progress(profile_name_str, "toc_fetch", "TOC fetched successfully", "success")

                # Get AIRAC date
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, AIP_SCRIPT, "--cache", cache_path,
                    "toc", "list", f"--{profile['flight_rule']}",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                lines = stdout.decode().strip().split('\n')
                if not lines or not lines[0].strip():
                    _log_progress(profile_name_str, "init", "No AIRAC cycles found", "warning")
                    continue

                airac_date = lines[0].split()[1]
                profile_sanitized = _sanitize(profile['name'])
                output_path = OUTPUT_DIR / f"{profile_sanitized}_{airac_date}.pdf"
                ocr_output_path = OUTPUT_DIR / f"{profile_sanitized}_{airac_date}_ocr.pdf"
                _log_progress(profile_name_str, "init", f"AIRAC date: {airac_date}", "info")

                # The OCR'd PDF is the deliverable: if it exists the cycle is done (unless forced).
                # The raw PDF is only an intermediate that is deleted once OCR succeeds.
                if ocr_output_path.exists() and not force:
                    _log_progress(profile_name_str, "ocr", "OCR PDF already exists", "success")
                else:
                    if force or not output_path.exists():
                        db.mark_pdf_created(run_id)
                        if not await _generate_raw_pdf(profile, output_path, cache_path, force):
                            continue
                    else:
                        _log_progress(profile_name_str, "pdf_gen", "Raw PDF already exists, resuming with OCR", "info")

                    if not await _ocr_pdf(profile_name_str, output_path, ocr_output_path):
                        continue  # keep the raw PDF so OCR can be retried without re-downloading

                # Rollover: drop raw PDFs that have an OCR copy, then old AIRAC cycles
                removed = rollover.drop_raw_with_ocr(OUTPUT_DIR, profile_sanitized)
                removed += rollover.prune_profile_dir(OUTPUT_DIR, settings.retain_cycles, profile_sanitized)
                if removed:
                    _log_progress(
                        profile_name_str, "rollover",
                        f"Removed {len(removed)} file(s): {', '.join(sorted(p.name for p in removed))}",
                        "info",
                    )
                
                _log_progress(profile_name_str, "complete", "Profile processing complete", "success")

            except Exception as e:
                _log_progress(profile_name_str, "error", f"Exception: {str(e)[:200]}", "error")
                logger.exception(f"Profile {profile_name_str} failed with exception")
    except HTTPException:
        raise  # Re-raise HTTP exceptions (like disk space errors)
    except Exception as e:
        _log_progress("", "system", f"Fatal error: {str(e)[:200]}", "error")
        logger.exception("Update process failed with exception")
        raise HTTPException(500, f"Update failed: {str(e)}")
    finally:
        _log_progress("", "system", "Update process finished", "info")
        try:
            db.finish_run(run_id)
            logger.info(f"Saved run {run_id}")
            pruned = db.prune_runs(settings.run_retention_days)
            if pruned:
                logger.info(f"Pruned {pruned} old run(s)")
            rollover.cleanup_partials(OUTPUT_DIR)
        except Exception:
            logger.exception("Post-run housekeeping failed")
        _current_run_id = None
        _release_update_lock()


@app.post("/api/update/run")
async def trigger_update(background_tasks: BackgroundTasks, profile: str | None = None, force: bool = False):
    # Check if update is already running
    if _update_lock_file is not None:
        return JSONResponse({"status": "already_running"}, status_code=409)

    if profile and not db.profile_exists(profile):
        raise HTTPException(404, "Profile not found")
    
    # Check disk space before starting
    has_space, free_gb = _check_disk_space()
    if not has_space:
        raise HTTPException(
            507,
            f"Insufficient disk space: {free_gb:.2f} GB free, {settings.min_free_space_gb:.2f} GB required"
        )
    
    background_tasks.add_task(run_update, profile, force)
    return {"status": "started"}


@app.get("/api/update/status")
def update_status():
    """Whether an update (or cleanup) currently holds the lock, and what the run is doing."""
    run_id = _current_run_id
    status: dict = {"running": _update_lock_file is not None, "run_id": run_id}
    if run_id is not None:
        last = db.last_log(run_id) or {}
        status.update(
            profile=last.get("profile", ""),
            stage=last.get("stage", ""),
            message=last.get("message", ""),
        )
    return status


@app.post("/api/cleanup")
def run_cleanup(data: CleanupRequest):
    try:
        _acquire_update_lock()
    except HTTPException:
         raise HTTPException(409, "Cleanup blocked: Update in progress")

    try:
        results = []
        if data.delete_cache:
            for item in CACHE_DIR.iterdir():
                if item.name == ".gitkeep": continue
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            results.append("Cache cleared")

        if data.delete_output:
            for item in OUTPUT_DIR.iterdir():
                if item.name == ".gitkeep": continue
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            db.reconcile_documents(OUTPUT_DIR)
            results.append("Documents deleted")
            
        logger.info(f"Cleanup performed: {', '.join(results)}")
        return {"status": "ok", "message": ", ".join(results)}
            
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(500, f"Cleanup failed: {str(e)}")
    finally:
        _release_update_lock()


# ============== Run History ==============

@app.get("/api/runs")
def list_runs():
    """List all past runs"""
    return {"runs": db.list_runs()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    """Get logs for a specific run"""
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


# ============== Documents ==============

@app.get("/api/documents")
def list_documents():
    return {"documents": db.reconcile_documents(OUTPUT_DIR)}


class FastFileResponse(FileResponse):
    """FileResponse with 2MB chunk size for high-throughput streaming of large files."""
    chunk_size = 2 * 1024 * 1024

    def __init__(self, *args, chunk_size: int = 2 * 1024 * 1024, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunk_size = chunk_size


def _document_path_by_id(doc_id: int) -> Path:
    doc = db.get_document(doc_id)
    if doc is None:
        db.reconcile_documents(OUTPUT_DIR)
        doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    file_path = _validate_path(OUTPUT_DIR, doc["name"])
    if not file_path.is_file():
        raise HTTPException(404, "Document not found")
    return file_path


def _serve_pdf(file_path: Path, preview: bool = False) -> FastFileResponse:
    media_type = "application/pdf" if preview else "application/octet-stream"
    content_disposition_type = "inline" if preview else "attachment"
    return FastFileResponse(
        file_path,
        media_type=media_type,
        filename=file_path.name,
        content_disposition_type=content_disposition_type,
    )


def _serve_zip(src: Path) -> FastFileResponse:
    fd, tmp_name = tempfile.mkstemp(dir=TMP_DIR, suffix=".zip")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        # PDFs are already compressed, so store instead of deflating.
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            z.write(src, arcname=src.name)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    return FastFileResponse(
        tmp,
        media_type="application/zip",
        filename=f"{src.stem}.zip",
        content_disposition_type="attachment",
        background=BackgroundTask(tmp.unlink, missing_ok=True),
    )


@app.post("/api/documents/download")
def download_document_post(data: DocumentDownloadRequest):
    """Download a document (PDF or ZIP) via POST so no path or document ID appears in the URL."""
    file_path = _document_path_by_id(data.id)
    if data.zip:
        return _serve_zip(file_path)
    return _serve_pdf(file_path, preview=data.preview)


@app.get("/api/documents/{doc_id}")
def download_document(doc_id: int, preview: bool = False):
    file_path = _document_path_by_id(doc_id)
    return _serve_pdf(file_path, preview=preview)


@app.get("/api/documents/{doc_id}/zip")
def download_document_zip(doc_id: int):
    """Download a document wrapped in a ZIP.

    Mobile browsers open PDFs in their viewer instead of saving them; a ZIP is not previewable,
    so it is always saved as a file.
    """
    src = _document_path_by_id(doc_id)
    return _serve_zip(src)


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int):
    _document_path_by_id(doc_id).unlink()
    db.reconcile_documents(OUTPUT_DIR)
    return {"status": "ok"}

# ============== Frontend (static SPA) ==============
# Registered last so the /api routes above take precedence. Only active when a
# built frontend is present (the single-container image); in dev, Vite serves it.

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "static"))


if STATIC_DIR.is_dir():
    _static_root = STATIC_DIR.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (_static_root / full_path).resolve()
        if full_path and candidate.is_relative_to(_static_root) and candidate.is_file():
            headers = {}
            if candidate.parent.name == "assets":
                # Content-hashed filenames: safe to cache forever.
                headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return FileResponse(candidate, headers=headers)
        # index.html must be revalidated so a new release is picked up immediately.
        return FileResponse(_static_root / "index.html", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
