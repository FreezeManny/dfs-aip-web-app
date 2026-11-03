# Backend

FastAPI service that drives the vendored [DFS AIP tool](../../vendor/dfs-aip/). It manages
download profiles, runs updates (manually or on a nightly schedule), records run history in SQLite,
prunes old AIRAC cycles, and serves both the generated PDFs (plus ZIP downloads) and the built
frontend SPA.

## Run locally (with `uv`)

```sh
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Run the test suite:

```sh
uv run pytest tests
```

Or via the project's Docker setup, see [`../docker-compose.yaml`](../docker-compose.yaml).

## Configuration

| Env var | Default | Description |
| --- | --- | --- |
| `AUTO_UPDATE_ENABLED` | `false` | Enable the nightly scheduled update |
| `AUTO_UPDATE_HOUR` | `2` | Hour (24h) the nightly update runs |
| `AUTO_UPDATE_MINUTE` | `0` | Minute the nightly update runs |
| `RETAIN_CYCLES` | `2` | Number of newest AIRAC cycles kept per profile |
| `RUN_RETENTION_DAYS` | `180` | Days to retain run history in SQLite |

Data is persisted under `data/` (`app.db` SQLite database), `output/` (generated OCR PDFs), and `cache/`.

## Vendored tool pin

The exact upstream commit bundled by this backend is recorded in
[`VENDOR_REF`](VENDOR_REF). It is updated by [`../../vendor/update.sh`](../../vendor/update.sh).
See [`../../vendor/README.md`](../../vendor/README.md).
