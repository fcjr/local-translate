#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> Collecting Rust licenses..."
(cd "$ROOT_DIR/src-tauri" && cargo-about generate --format json) \
  > "$TMP_DIR/rust.json" 2>/dev/null

echo "==> Collecting JavaScript licenses..."
(cd "$ROOT_DIR" && pnpm licenses list --json) \
  > "$TMP_DIR/js.json" 2>/dev/null

echo "==> Collecting Python licenses..."
(cd "$ROOT_DIR" && uv run pip-licenses --format=json --with-license-file --no-license-path --with-urls) \
  > "$TMP_DIR/python.json" 2>/dev/null

echo "==> Generating Credits.html..."
node "$ROOT_DIR/scripts/merge-licenses.mjs" \
  "$TMP_DIR/rust.json" \
  "$TMP_DIR/js.json" \
  "$TMP_DIR/python.json" \
  "$ROOT_DIR/src-tauri/Credits.html"
