#!/usr/bin/env bash
#
# Re-sync the vendored copy of the DFS AIP tool from upstream.
#
# The tool in vendor/dfs-aip/ is a verbatim copy of the `basic/` directory of
# https://github.com/hamarituc/dfs-aip. This project uses it unmodified, so we
# vendor it (commit it in-tree) rather than depend on a live submodule/clone:
# the build keeps working even if upstream changes or disappears, and updates
# happen only when you run this script on purpose.
#
# Usage:
#   vendor/update.sh [<upstream-ref>]
#
# <upstream-ref> defaults to the currently pinned commit (see vendor/README.md).
# After running, update the pinned SHA in vendor/README.md and commit.

set -euo pipefail

UPSTREAM_URL="https://github.com/hamarituc/dfs-aip"
DEFAULT_REF="c4dbbffaaec15ab337b14ca92413f8c335b55482"
REF="${1:-$DEFAULT_REF}"

# Resolve paths relative to this script so it works from any CWD.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DEST="$SCRIPT_DIR/dfs-aip"

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

echo "Cloning $UPSTREAM_URL @ $REF ..."
git clone --quiet --no-checkout "$UPSTREAM_URL" "$TMP_DIR/src"
git -C "$TMP_DIR/src" checkout --quiet "$REF"

RESOLVED_SHA="$(git -C "$TMP_DIR/src" rev-parse HEAD)"

if [ ! -d "$TMP_DIR/src/basic" ]; then
  echo "error: upstream ref $REF has no basic/ directory" >&2
  exit 1
fi

echo "Replacing vendor/dfs-aip/ ..."
rm -rf "$DEST"
cp -a "$TMP_DIR/src/basic" "$DEST"

# Keep the license notice in sync (LGPL-3.0).
if [ -f "$TMP_DIR/src/COPYING.md" ]; then
  cp -a "$TMP_DIR/src/COPYING.md" "$REPO_ROOT/COPYING.md"
fi

echo
echo "Done. Vendored upstream commit:"
echo "  $RESOLVED_SHA"
echo
echo "Next steps:"
echo "  1. Update the pinned SHA in vendor/README.md to $RESOLVED_SHA"
echo "  2. Review changes:  git status && git diff --stat"
echo "  3. Commit the vendored update."
