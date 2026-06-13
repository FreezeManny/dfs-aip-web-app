# Backend

FastAPI service that drives the vendored [DFS AIP tool](../../vendor/dfs-aip/). It manages
download profiles, runs updates (manually or on a nightly schedule), records run history, and
serves the generated PDFs to the frontend.

## Run locally

```sh
pip install -r ../../vendor/dfs-aip/requirements.txt -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Or via the project's Docker setup, see [`../docker-compose.yaml`](../docker-compose.yaml).

## Configuration

| Env var | Default | Description |
| --- | --- | --- |
| `AUTO_UPDATE_ENABLED` | `true` | Enable the nightly scheduled update |
| `AUTO_UPDATE_HOUR` | `2` | Hour (24h) the nightly update runs |
| `AUTO_UPDATE_MINUTE` | `0` | Minute the nightly update runs |

Data is persisted under `data/` (profiles), `output/` (generated PDFs), and `cache/`.

## Vendored tool pin

The exact upstream commit bundled by this backend is recorded in
[`VENDOR_REF`](VENDOR_REF). It is updated by [`../../vendor/update.sh`](../../vendor/update.sh);
changing it bumps the backend's release version. See [`../../vendor/README.md`](../../vendor/README.md).
