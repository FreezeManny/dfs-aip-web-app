# DFS AIP Web Interface

A self-hosted web UI around the [DFS AIP](https://github.com/hamarituc/dfs-aip) tool, which
downloads and print-prepares the German DFS Aeronautical Information Publication (basicAIP /
VFR) as PDFs.

The UI lets you manage download profiles, schedule nightly updates, trigger updates manually,
browse run history, and download the generated (OCR'd) PDFs (or ZIP archives for mobile devices) —
all from a single container.

## Quick start

Run the published image from the GitHub Container Registry — no build needed:

```sh
docker compose up -d
# then open http://localhost:8080
```

This uses the [`docker-compose.yaml`](docker-compose.yaml) in the project root, which pulls
`ghcr.io/freezemanny/dfs-aip`:

```yaml
services:
  dfs-aip:
    image: ghcr.io/freezemanny/dfs-aip:latest
    container_name: dfs-aip
    ports:
      - "8080:8000"
    environment:
      # Auto-update configuration
      - AUTO_UPDATE_ENABLED=true
      - AUTO_UPDATE_HOUR=2    # 2 AM (24-hour format)
      - AUTO_UPDATE_MINUTE=0  # 00 minutes
      # Rollover (defaults shown)
      # - RETAIN_CYCLES=2          # newest AIRAC cycles kept per profile
      # - RUN_RETENTION_DAYS=180   # how long run history is kept
    volumes:
      - data:/app/data      # SQLite database (profiles, run history)
      - output:/app/output  # Generated PDFs
      - aip-cache:/app/cache  # Cache
    restart: unless-stopped

volumes:
  data:
  output:
  aip-cache:
```

> **Upgrading from the two-container setup (`dfs-aip-frontend` + `dfs-aip-backend`):**
> Replace both services in your `docker-compose.yaml` with the single `dfs-aip` service above.
> Existing `profiles.json` and `runs/*.json` files in the `data` volume are imported into SQLite automatically on first start (and renamed to `*.migrated`).

To build the image locally from source instead:

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
  Dockerfile       Multi-stage build (Vite static SPA + FastAPI runtime)
  backend/         FastAPI backend (uv) that drives the tool and serves the SPA
  frontend/        React + TypeScript + Vite + Tailwind UI
  docker-compose.yaml
```

## Contributing

Every PR is **squash-merged**, and the squash commit message is the **PR title**. That single
title is therefore the only string release-please ever reads, and the only one that has to be
a [Conventional Commit](https://www.conventionalcommits.org/) — the **PR Title** check enforces
it. Commits *inside* your branch are yours: `wip`, `fixup`, `asdf`, whatever helps you save
work. None of them reach `main` or the changelog, so there is no commit-message hook to install.

Title format:

```
<type>(<optional scope>): <description>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
`chore`, `revert`. Append `!` for a breaking change (e.g. `feat!:`). Because the squash body is
the **PR description**, that is also where a `BREAKING CHANGE:` footer goes. Examples:

```
feat(frontend): add run-history filter
fix(backend): handle empty profile list
chore(deps): bump vite
```

> Only `feat`, `fix`, and breaking changes bump a version; the rest don't trigger a release.
> A PR that does two unrelated things collapses into one changelog entry under one type. The fix
> is to split the PR.

The other checks on a PR: **backend** (byte-compile, pytest, and build the combined Docker image)
and **frontend** (eslint, `tsc`, Vite build).

## Attribution & license

The actual AIP processing is done by **[hamarituc/dfs-aip](https://github.com/hamarituc/dfs-aip)**
by Mario Haustein and contributors, licensed under **LGPL-3.0**. A verbatim copy of that tool is
vendored under [`vendor/dfs-aip/`](vendor/dfs-aip/) and used unmodified; see
[`vendor/README.md`](vendor/README.md) for the pinned version and update procedure, and
[`COPYING.md`](COPYING.md) for the license.

This project (the web interface in `webui/`) is distributed under the same LGPL-3.0 license.
