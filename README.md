# DFS AIP Web Interface

A self-hosted web UI around the [DFS AIP](https://github.com/hamarituc/dfs-aip) tool, which
downloads and print-prepares the German DFS Aeronautical Information Publication (basicAIP /
VFR) as PDFs.

The UI lets you manage download profiles, schedule nightly updates, trigger updates manually,
browse run history, and download the generated (OCR'd) PDFs — all from the browser.

## Quick start

Run the published images from the GitHub Container Registry — no build needed:

```sh
docker compose up -d
# then open http://localhost:8080
```

This uses the [`docker-compose.yaml`](docker-compose.yaml) in the project root, which pulls
`ghcr.io/freezemanny/dfs-aip-frontend` and `ghcr.io/freezemanny/dfs-aip-backend`:

```yaml
services:
  frontend:
    image: ghcr.io/freezemanny/dfs-aip-frontend:latest
    container_name: dfs-aip-frontend
    ports:
      - "8080:80"
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - dfs-aip-network

  backend:
    image: ghcr.io/freezemanny/dfs-aip-backend:latest
    container_name: dfs-aip-backend
    environment:
      # Auto-update configuration
      - AUTO_UPDATE_ENABLED=true
      - AUTO_UPDATE_HOUR=2    # 2 AM (24-hour format)
      - AUTO_UPDATE_MINUTE=0  # 00 minutes
    volumes:
      - data:/app/data      # Profiles JSON
      - output:/app/output  # Generated PDFs
      - aip-cache:/app/cache  # Cache
    restart: unless-stopped
    networks:
      - dfs-aip-network

volumes:
  data:
  output:
  aip-cache:
```

To build the images locally from source instead:

```sh
docker compose -f webui/docker-compose.yaml up --build -d
```

See [`webui/README.md`](webui/README.md) for configuration, environment variables, and the API.

## Repository layout

```
vendor/          Vendored, unmodified copy of the upstream DFS AIP tool
  dfs-aip/         the tool itself (used as-is by the backend)
  README.md        pinned upstream version + how to update
  update.sh        re-sync script
webui/           The web interface (this project's own code)
  backend/         FastAPI backend that drives the tool
  frontend/        React + TypeScript + Vite + Tailwind UI
  docker-compose.yaml
```

## Attribution & license

The actual AIP processing is done by **[hamarituc/dfs-aip](https://github.com/hamarituc/dfs-aip)**
by Mario Haustein and contributors, licensed under **LGPL-3.0**. A verbatim copy of that tool is
vendored under [`vendor/dfs-aip/`](vendor/dfs-aip/) and used unmodified; see
[`vendor/README.md`](vendor/README.md) for the pinned version and update procedure, and
[`COPYING.md`](COPYING.md) for the license.

This project (the web interface in `webui/`) is distributed under the same LGPL-3.0 license.
