# Frontend

React + TypeScript + Vite + Tailwind UI for the DFS AIP web interface. It talks to the
[backend](../backend/) over `/api`, lets you manage download profiles, trigger updates, browse
run history, and download generated PDFs or ZIPs.

In production it is compiled to static files during the multi-stage Docker build
([`../Dockerfile`](../Dockerfile)) and served directly by the FastAPI backend.

## Develop

```sh
bun install
bun run dev   # Vite dev server with HMR (proxies /api to http://localhost:8000)
```

## Scripts

| Command | Description |
| --- | --- |
| `bun run dev` | Start the Vite dev server |
| `bun run build` | Type-check and build to `dist/` |
| `bun run lint` | Run ESLint |
| `bun run preview` | Preview the production build |
