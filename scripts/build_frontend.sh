#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cd frontend

# Use pnpm from PATH, falling back to corepack (bundled with Node >= 16.13).
if command -v pnpm >/dev/null 2>&1; then
  PNPM=pnpm
elif command -v corepack >/dev/null 2>&1; then
  PNPM="corepack pnpm"
else
  echo "pnpm not found — install pnpm or Node with corepack" >&2
  exit 1
fi

$PNPM install --frozen-lockfile
$PNPM typecheck
$PNPM build
echo "Frontend built → src/web/static/app/"
