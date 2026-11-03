# Frontend

React + TypeScript + Vite + Tailwind UI for the DFS AIP web interface. It talks to the
[backend](../backend/) over `/api`, lets you manage download profiles, trigger incremental or
forced updates, watch live progress, browse run history, and download generated PDFs or ZIPs.

In production it is compiled to static files during the multi-stage Docker build
([`../Dockerfile`](../Dockerfile)) and served directly by the FastAPI backend.

## Develop

```sh
corepack enable pnpm
pnpm install
pnpm dev      # Vite dev server with HMR (proxies /api to http://localhost:8000)
```

## Scripts

| Command | Description |
| --- | --- |
| `pnpm dev` | Start the Vite dev server |
| `pnpm build` | Type-check and build to `dist/` |
| `pnpm lint` | Run ESLint |
| `pnpm preview` | Preview the production build |
