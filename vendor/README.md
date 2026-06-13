# Vendored: DFS AIP tool

`dfs-aip/` is a **verbatim, vendored copy** of the `basic/` directory from the upstream
project:

- **Upstream:** https://github.com/hamarituc/dfs-aip
- **Pinned commit:** `c4dbbffaaec15ab337b14ca92413f8c335b55482`
  ("Server wants a custom User-Agent", 2025-09-29)
- **License:** LGPL-3.0 (see [`../COPYING.md`](../COPYING.md))

## Why it's vendored

The web interface in [`../webui/`](../webui/) uses this tool unmodified — it just shells out to
`python3 aip.py ...`. Rather than depend on a live git submodule or a build-time `git clone`,
the tool is committed in-tree so that:

- the build keeps working **even if upstream changes or is deleted**, and
- upstream changes only reach a build when we deliberately pull them.

## Do not hand-edit `dfs-aip/`

Treat `dfs-aip/` as read-only third-party code. To pull a newer (or older) upstream version:

```sh
vendor/update.sh <upstream-ref>   # ref defaults to the pinned commit above
```

The script clones upstream at that ref, replaces `vendor/dfs-aip/` with upstream's `basic/`,
and refreshes `../COPYING.md`. Afterwards:

1. Update the **Pinned commit** line above to the SHA the script prints.
2. Review with `git status` / `git diff --stat`.
3. Commit the vendored update with a conventional commit (e.g. `fix(backend): ...`).

The script also writes the resolved SHA to [`../webui/backend/VENDOR_REF`](../webui/backend/VENDOR_REF).
That file lives inside the backend package on purpose: the backend image bundles this vendored
code, so a vendor update must bump the **backend** version. Release Please attributes commits to a
package by path, and `vendor/` is outside `webui/backend/`, so the `VENDOR_REF` file is what links
a vendor sync to a backend release.
