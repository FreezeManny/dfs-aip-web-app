"""
DFS AIP Updater - Single-file FastAPI Backend
"""

import asyncio
import fcntl
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

OUTPUT_DIR = settings.output_dir
CACHE_DIR = settings.cache_dir
DATA_DIR = settings.data_dir
PROFILES_FILE = DATA_DIR / "profiles.json"
RUNS_DIR = DATA_DIR / "runs"
LOCK_FILE = DATA_DIR / "update.lock"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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

app = FastAPI(title="DFS AIP Updater", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_update_lock_file: Optional[object] = None
_current_run_logs: dict[str, list] = {}  # profile_name -> list of logs
_current_run_metadata: dict[str, any] = {}  # metadata about the current run


def _log_progress(profile: str, stage: str, message: str = "", status: str = "info"):
    """Log progress message with profile context"""
    msg = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "stage": stage,
        "message": message,
        "status": status,  # "info", "warning", "error", "success"
    }
    
    # Store in current run logs
    if profile and profile != "":
        if profile not in _current_run_logs:
            _current_run_logs[profile] = []
        _current_run_logs[profile].append(msg)
    
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


# ============== Profile Storage ==============

def _load_profiles() -> list[dict]:
    if not PROFILES_FILE.exists():
        return []
    return json.loads(PROFILES_FILE.read_text())


def _save_profiles(profiles: list[dict]) -> None:
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2))


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
    return {"profiles": sorted(_load_profiles(), key=lambda x: x["name"])}


@app.post("/api/profiles")
def create_profile(data: ProfileData):
    profiles = _load_profiles()
    if any(p["name"] == data.name for p in profiles):
        raise HTTPException(400, f"Profile '{data.name}' already exists")
    
    profiles.append(data.model_dump())
    _save_profiles(profiles)
    (OUTPUT_DIR / _sanitize(data.name)).mkdir(parents=True, exist_ok=True)
    return {"status": "ok"}


@app.put("/api/profiles/{name}")
def update_profile(name: str, data: ProfileData):
    profiles = _load_profiles()
    for i, p in enumerate(profiles):
        if p["name"] == name:
            profiles[i] = data.model_dump()
            _save_profiles(profiles)
            return {"status": "ok"}
    raise HTTPException(404, "Profile not found")


@app.delete("/api/profiles/{name}")
def delete_profile(name: str):
    profiles = _load_profiles()
    new_profiles = [p for p in profiles if p["name"] != name]
    if len(new_profiles) == len(profiles):
        raise HTTPException(404, "Profile not found")
    _save_profiles(new_profiles)
    return {"status": "ok"}


# ============== Update ==============

async def run_update(profile_name: str | None = None):
    # Acquire lock to prevent concurrent updates
    _acquire_update_lock()
    
    # Initialize run metadata
    global _current_run_metadata
    _current_run_metadata = {"pdf_created": False}
    
    try:
        _log_progress("", "system", "Starting update process", "info")
        
        # Check disk space
        has_space, free_gb = _check_disk_space()
        if not has_space:
            error_msg = f"Insufficient disk space: {free_gb:.2f} GB free, {settings.min_free_space_gb:.2f} GB required"
            _log_progress("", "system", error_msg, "error")
            raise HTTPException(507, error_msg)
        
        _log_progress("", "system", f"Disk space: {free_gb:.2f} GB available", "info")
        profiles = [p for p in _load_profiles() if p.get("enabled", True)]
        if profile_name:
            profiles = [p for p in profiles if p["name"] == profile_name]

        _log_progress("", "system", f"Found {len(profiles)} profile(s) to process", "info")

        for profile in profiles:
            profile_name_str = profile['name']
            try:
                _log_progress(profile_name_str, "init", "Starting profile processing", "info")
                profile_dir = OUTPUT_DIR / _sanitize(profile["name"])
                profile_dir.mkdir(parents=True, exist_ok=True)
                cache_path = str(CACHE_DIR / "dfs-aip")

                # Fetch TOC
                _log_progress(profile_name_str, "toc_fetch", f"Fetching TOC ({profile['flight_rule'].upper()})", "info")
                proc = await asyncio.create_subprocess_exec(
                    "python3", "/app/aip.py", "--cache", cache_path,
                    "toc", "fetch", f"--{profile['flight_rule']}",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    _log_progress(profile_name_str, "toc_fetch", f"Failed: {stderr.decode()[:200]}", "error")
                    continue
                _log_progress(profile_name_str, "toc_fetch", "TOC fetched successfully", "success")

                # Get AIRAC date
                proc = await asyncio.create_subprocess_exec(
                    "python3", "/app/aip.py", "--cache", cache_path,
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
                output_path = profile_dir / f"{profile_sanitized}_{airac_date}.pdf"
                ocr_output_path = profile_dir / f"{profile_sanitized}_{airac_date}_ocr.pdf"
                _log_progress(profile_name_str, "init", f"AIRAC date: {airac_date}", "info")
                
                # Check if we need to generate PDF
                if output_path.exists():
                    _log_progress(profile_name_str, "pdf_gen", "PDF already exists", "info")
                else:
                    # Generate PDF
                    _log_progress(profile_name_str, "pdf_gen", "Generating PDF", "info")
                    _current_run_metadata["pdf_created"] = True
                    filter_args = [arg for f in profile.get("filters", []) for arg in ["-f", f]]
                    proc = await asyncio.create_subprocess_exec(
                        "python3", "-u", "/app/aip.py", "--cache", cache_path,
                        "pdf", "--output", str(output_path),
                        "summary", f"--{profile['flight_rule']}", *filter_args,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    
                    # Stream stdout to show page downloads
                    page_count = 0
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        page_name = line.decode().strip()
                        if page_name:
                            page_count += 1
                            _log_progress(profile_name_str, "pdf_gen", f"Downloaded page {page_count}: {page_name}", "info")
                    
                    await proc.wait()
                    stderr = await proc.stderr.read()

                    if proc.returncode == 0:
                        size_mb = output_path.stat().st_size / (1024 * 1024)
                        _log_progress(profile_name_str, "pdf_gen", f"PDF complete ({size_mb:.1f} MB)", "success")
                    else:
                        _log_progress(profile_name_str, "pdf_gen", f"Failed: {stderr.decode()[:200]}", "error")
                        continue

                # Check if we need to generate OCR version
                if not ocr_output_path.exists():
                    # Generate OCR version
                    _log_progress(profile_name_str, "ocr", f"Starting OCR: {output_path.name} -> {ocr_output_path.name}", "info")
                    _log_progress(profile_name_str, "ocr", f"Input PDF size: {output_path.stat().st_size / (1024 * 1024):.1f} MB", "info")
                    _log_progress(profile_name_str, "ocr", f"Using {settings.ocr_jobs} parallel worker(s)", "info")
                    
                    proc = await asyncio.create_subprocess_exec(
                        "ocrmypdf", "--jobs", str(settings.ocr_jobs), "--verbose", "1", str(output_path), str(ocr_output_path),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    
                    # Stream stderr to capture OCR progress
                    async def log_stderr():
                        stderr_lines = []
                        while True:
                            line = await proc.stderr.readline()
                            if not line:
                                break
                            decoded = line.decode().strip()
                            stderr_lines.append(decoded)
                            if decoded:
                                _log_progress(profile_name_str, "ocr", decoded, "info")
                        return stderr_lines
                    
                    stderr_lines = await log_stderr()
                    stdout = await proc.stdout.read()
                    await proc.wait()
                    
                    if proc.returncode == 0:
                        ocr_size_mb = ocr_output_path.stat().st_size / (1024 * 1024)
                        _log_progress(profile_name_str, "ocr", f"OCR complete ({ocr_size_mb:.1f} MB)", "success")
                    else:
                        _log_progress(profile_name_str, "ocr", f"Process exited with code {proc.returncode}", "error")
                        _log_progress(profile_name_str, "ocr", f"Last 10 stderr lines: {stderr_lines[-10:]}", "error")
                        if stdout:
                            _log_progress(profile_name_str, "ocr", f"stdout: {stdout.decode()[:500]}", "error")
                else:
                    _log_progress(profile_name_str, "ocr", "OCR PDF already exists", "success")
                
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
        _save_run()
        _current_run_logs.clear()
        _current_run_metadata.clear()
        _release_update_lock()


@app.post("/api/update/run")
async def trigger_update(background_tasks: BackgroundTasks, profile: str | None = None):
    # Check if update is already running
    if _update_lock_file is not None:
        return {"status": "already_running"}
    
    # Check disk space before starting
    has_space, free_gb = _check_disk_space()
    if not has_space:
        raise HTTPException(
            507,
            f"Insufficient disk space: {free_gb:.2f} GB free, {settings.min_free_space_gb:.2f} GB required"
        )
    
    background_tasks.add_task(run_update, profile)
    return {"status": "started"}


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
            # Recreate profile directories
            try:
                for profile in _load_profiles():
                    (OUTPUT_DIR / _sanitize(profile["name"])).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass # Ignore if profiles can't be loaded or created
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
    runs = []
    for run_file in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(run_file.read_text())
            logs = data.get("logs", {})
            metadata = data.get("metadata", {})
            
            # Determine overall status: "success" if all profiles completed without error, else "error"
            status = "success"
            for profile_logs in logs.values():
                if profile_logs and profile_logs[-1].get("status") == "error":
                    status = "error"
                    break
            
            runs.append({
                "id": run_file.stem,
                "timestamp": data.get("timestamp"),
                "profiles": list(logs.keys()),
                "status": status,
                "pdf_created": metadata.get("pdf_created", False),
            })
        except Exception as e:
            logger.error(f"Failed to read run {run_file}: {e}")
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    """Get logs for a specific run"""
    run_file = RUNS_DIR / f"{run_id}.json"
    if not run_file.exists():
        raise HTTPException(404, "Run not found")
    
    try:
        data = json.loads(run_file.read_text())
        return data
    except Exception as e:
        raise HTTPException(500, f"Failed to read run: {str(e)}")


def _save_run():
    """Save current run logs to file"""
    run_timestamp = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    run_data = {
        "id": run_id,
        "timestamp": run_timestamp,
        "logs": _current_run_logs.copy(),
        "metadata": _current_run_metadata.copy(),
    }
    
    run_file = RUNS_DIR / f"{run_id}.json"
    run_file.write_text(json.dumps(run_data, indent=2))
    logger.info(f"Saved run {run_id}")


# ============== Documents ==============

@app.get("/api/documents")
def list_documents():
    documents = []
    for profile_dir in OUTPUT_DIR.iterdir():
        if profile_dir.is_dir():
            for f in profile_dir.glob("*.pdf"):
                stat = f.stat()
                is_ocr = f.stem.endswith("_ocr")
                stem = f.stem.replace("_ocr", "") if is_ocr else f.stem
                # Extract airac_date from "ProfileName_YYYY-MM-DD" format
                parts = stem.split("_", 1)  # Split on first underscore
                airac_date = parts[1] if len(parts) > 1 else stem
                documents.append({
                    "name": f.name,
                    "profile": profile_dir.name,
                    "airac_date": airac_date,
                    "path": str(f.relative_to(OUTPUT_DIR)),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "is_ocr": is_ocr,
                })
    return {"documents": sorted(documents, key=lambda x: x["modified"], reverse=True)}


@app.get("/api/documents/{profile}/{filename}")
def download_document(profile: str, filename: str):
    # Validate path to prevent directory traversal attacks
    file_path = _validate_path(OUTPUT_DIR, profile, filename)
    
    if not file_path.exists():
        raise HTTPException(404, "Document not found")
    if not file_path.is_file():
        raise HTTPException(400, "Invalid path: not a file")
    
    return FileResponse(file_path, media_type="application/pdf", filename=filename)


@app.delete("/api/documents/{profile}/{filename}")
def delete_document(profile: str, filename: str):
    # Validate path to prevent directory traversal attacks
    file_path = _validate_path(OUTPUT_DIR, profile, filename)
    
    if not file_path.exists():
        raise HTTPException(404, "Document not found")
    if not file_path.is_file():
        raise HTTPException(400, "Invalid path: not a file")
    
    file_path.unlink()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
