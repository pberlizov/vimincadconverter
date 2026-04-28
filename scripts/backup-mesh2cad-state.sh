#!/usr/bin/env bash
# Archive MESH2CAD_STATE_DIR to a timestamped tarball (SQLite + uploads + jobs).
set -euo pipefail
STATE="${MESH2CAD_STATE_DIR:?Set MESH2CAD_STATE_DIR to your state directory}"
DEST="${1:-./mesh2cad-state-backup-$(date -u +%Y%m%dT%H%M%SZ).tar.gz}"
PARENT="$(dirname "$STATE")"
BASE="$(basename "$STATE")"
tar -C "$PARENT" -czf "$DEST" "$BASE"
echo "Wrote $DEST"
