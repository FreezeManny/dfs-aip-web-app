# DFS AIP Web Interface

A simple web-based interface for the DFS AIP (Aeronautical Information Publication) updater.

## Features

- **Profile Management**: Create and delete AIP download profiles
- **Automatic Updates**: Schedule nightly updates at a configurable time
- **Update Control**: Trigger updates manually for all or individual profiles
- **Run History**: View update history with status and detailed logs
- **Document Downloads**: Browse and download generated PDFs (with OCR)

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS + shadcn/ui + Nginx
- **Backend**: FastAPI + APScheduler
- **Container**: Docker with docker-compose

## Quick Start

### Using Docker Compose (Recommended)

```bash
cd docker-webinterface

# Build and start both containers
docker-compose up --build -d

# View logs
docker-compose logs -f

# Access the web interface
open http://localhost:8080
```

### Development Mode

**Backend:**
```bash
cd backend
pip install -r requirements.txt
python main.py
# Runs on http://localhost:8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173 (proxies /api to localhost:8000)
```

## Configuration

### Environment Variables (Backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_UPDATE_ENABLED` | `false` | Enable automatic nightly updates |
| `AUTO_UPDATE_HOUR` | `2` | Hour for automatic updates (0-23, 24-hour format) |
| `AUTO_UPDATE_MINUTE` | `0` | Minute for automatic updates (0-59) |

**Example**: To run updates daily at 3:30 AM, set:
```yaml
environment:
  - AUTO_UPDATE_ENABLED=true
  - AUTO_UPDATE_HOUR=3
  - AUTO_UPDATE_MINUTE=30
```

### Profile Configuration

Profiles are stored in `/app/data/profiles.json`:

```json
[
  {
    "name": "Airport Charts",
    "flight_rule": "vfr",
    "filters": ["AD"],
    "enabled": true
  },
  {
    "name": "General Info",
    "flight_rule": "vfr",
    "filters": ["GEN"],
    "enabled": true
  }
]
```

### Available Filters

| Filter | Description |
|--------|-------------|
| `GEN` | General Information |
| `ENR` | En-Route |
| `AD` | Aerodrome Charts |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get current configuration |
| POST | `/api/config` | Save configuration |
| POST | `/api/config/profile` | Add a new profile |
| DELETE | `/api/config/profile/{name}` | Delete a profile |
| POST | `/api/update/run` | Trigger an update |
| GET | `/api/update/status` | Get update status |
| GET | `/api/logs` | Get historical logs |
| GET | `/api/logs/stream` | SSE stream for live logs |
| GET | `/api/documents` | List available documents |
| GET | `/api/documents/{filename}` | Download a document |
| DELETE | `/api/documents/{filename}` | Delete a document |
| GET | `/api/airac` | Get available AIRAC cycles |

## Directory Structure

```
docker-webinterface/
├── backend/
│   ├── Dockerfile        # Backend container
│   ├── main.py           # FastAPI application
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── Dockerfile        # Frontend container (Nginx)
│   ├── nginx.conf        # Nginx configuration
│   ├── src/
│   │   ├── App.vue
│   │   ├── api.ts        # API client
│   │   └── components/
│   │       ├── ProfileSettings.vue
│   │       ├── LogViewer.vue
│   │       ├── DocumentList.vue
│   │       └── StatusBar.vue
│   ├── package.json
│   └── vite.config.ts
├── data/                 # Mounted volume (shared)
│   ├── config.json
│   ├── output/           # Generated PDFs
│   └── cache/            # AIP cache
├── docker-compose.yaml
└── README.md
```

## Screenshots

The web interface includes three main tabs:

1. **Settings**: Configure AIP download profiles
2. **Logs**: View real-time and historical logs
3. **Documents**: Browse and download generated PDFs

## Notes

- OCR processing is included (using ocrmypdf + tesseract) and runs automatically after PDF generation
- Currently tested with DFS BasicVFR (VFR) only
- The backend container requires network access to fetch DFS resources
- Frontend container proxies `/api/*` requests to the backend via internal Docker network
