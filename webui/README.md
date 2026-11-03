# DFS AIP Web Interface

A self-hosted web-based interface for the DFS AIP (Aeronautical Information Publication) updater, shipped as a single Docker container.

## Features

- **Profile Management**: Create, edit, and delete AIP download profiles
- **Automatic Updates**: Schedule nightly updates at a configurable time
- **Incremental & Forced Updates**: Check for new AIRAC cycles quickly, or force a full cache bypass and rebuild
- **Automatic Rollover**: Retain only the newest `N` AIRAC cycles per profile and automatically remove intermediate raw PDFs after OCR succeeds
- **Run History**: View live and past update runs with per-profile stage logs stored in SQLite
- **Document Downloads**: Download OCR'd PDFs directly or wrapped in a `.zip` (ideal for mobile devices that otherwise force inline PDF preview)

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS + shadcn/ui (compiled statically at image build time)
- **Backend**: Python + FastAPI + SQLite + APScheduler (managed with `uv`, serves both `/api/*` and the static SPA)
- **Container**: Single multi-stage Docker image (`webui/Dockerfile`)

## Quick Start

### Using Docker Compose (Recommended)

```bash
# From the repository root:

# Build and start the container
docker compose -f webui/docker-compose.yaml up --build -d

# View logs
docker compose -f webui/docker-compose.yaml logs -f

# Access the web interface
open http://localhost:8080
```

### Development Mode

**Backend (`uv`):**
```bash
cd webui/backend
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Runs on http://localhost:8000
```

**Backend tests:**
```bash
cd webui/backend
uv run pytest tests
```

**Frontend (`bun`):**
```bash
cd webui/frontend
bun install
bun run dev
# Runs on http://localhost:5173 (proxies /api to http://localhost:8000)
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_UPDATE_ENABLED` | `false` | Enable automatic nightly updates |
| `AUTO_UPDATE_HOUR` | `2` | Hour for automatic updates (0-23, 24-hour format) |
| `AUTO_UPDATE_MINUTE` | `0` | Minute for automatic updates (0-59) |
| `RETAIN_CYCLES` | `2` | Number of newest AIRAC cycles kept per profile |
| `RUN_RETENTION_DAYS` | `180` | Days to retain finished run history in SQLite |
| `OCR_JOBS` | `max(2, cpu_count // 2)` | Parallel workers for `ocrmypdf` |
| `MIN_FREE_SPACE_GB` | `1.0` | Minimum free disk space required before starting an update |

### Storage Layout

State is persisted across three volumes:
- `/app/data`: SQLite database (`app.db`) holding profiles, runs, run logs, and the document index. Legacy `profiles.json` and `runs/*.json` are automatically migrated on startup and renamed to `*.migrated`.
- `/app/output`: Generated OCR'd PDFs (`<Profile>_<YYYY-MM-DD>_ocr.pdf`), organized by profile directory.
- `/app/cache`: Upstream `dfs-aip` TOC and page cache.

### Available Filters

| Filter | Description |
|--------|-------------|
| `GEN` | General Information |
| `ENR` | En-Route |
| `AD` | Aerodrome Charts |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/profiles` | List profiles |
| POST | `/api/profiles` | Create a profile |
| PUT | `/api/profiles/{name}` | Update a profile |
| DELETE | `/api/profiles/{name}` | Delete a profile |
| POST | `/api/update/run` | Trigger an update (`?profile=<name>&force=true`) |
| GET | `/api/update/status` | Get live update status and current stage |
| GET | `/api/runs` | List past and running update runs |
| GET | `/api/runs/{run_id}` | Get detailed logs for a run |
| GET | `/api/documents` | List available documents |
| GET | `/api/documents/{profile}/{filename}` | Download or preview (`?preview=true`) a PDF |
| GET | `/api/documents/{profile}/{filename}/zip` | Download a PDF packaged as a `.zip` archive |
| DELETE | `/api/documents/{profile}/{filename}` | Delete a document |
| POST | `/api/cleanup` | Clear cache and/or output directories |

## Directory Structure

```
webui/
├── Dockerfile            # Single multi-stage container build
├── docker-compose.yaml   # Local build compose file
├── backend/
│   ├── main.py           # FastAPI application & SPA static serving
│   ├── db.py             # SQLite persistence & JSON migration
│   ├── rollover.py       # AIRAC cycle retention & partial-file cleanup
│   ├── pyproject.toml    # Python dependencies (uv)
│   ├── uv.lock           # Locked Python dependencies
│   └── tests/            # Pytest test suite
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── lib/api.ts    # API client
│   │   └── components/
│   │       ├── ProfilesSection.tsx
│   │       ├── DocumentsSection.tsx
│   │       ├── RunHistoryTable.tsx
│   │       └── ui/       # shadcn/ui primitives
│   ├── package.json
│   └── vite.config.ts
└── README.md
```
