#!/bin/bash
# Stop + start in one go. Use this after editing src/ — uvicorn is launched
# fresh, no docker rebuild. Qdrant container stays up across the restart.
set -e
cd "$(dirname "$0")/.."

./scripts/stop.sh
./scripts/start.sh
