# Frontend

React + TypeScript + Vite + Tailwind UI for the DFS AIP web interface. It talks to the
[backend](../backend/) over `/api`, lets you manage download profiles, trigger updates, watch
progress (via SSE), browse run history, and download generated PDFs.

In production it is built to static files and served by nginx, which also reverse-proxies `/api`
to the backend — see [`Dockerfile`](Dockerfile) and [`nginx.conf`](nginx.conf).

## Develop

```sh
corepack enable pnpm
pnpm install
pnpm dev      # Vite dev server with HMR
```

The dev server expects the backend reachable at `/api` (configure a proxy in
[`vite.config.ts`](vite.config.ts) if running the backend separately).

## Scripts

| Command | Description |
| --- | --- |
| `pnpm dev` | Start the Vite dev server |
| `pnpm build` | Type-check and build to `dist/` |
| `pnpm lint` | Run ESLint |
| `pnpm preview` | Preview the production build |
