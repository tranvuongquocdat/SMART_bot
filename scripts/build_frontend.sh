#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cd frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
echo "Frontend built → src/web/static/app/"
