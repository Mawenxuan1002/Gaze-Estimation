#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
echo "=== Building Docker image ==="
docker build -t gaze-tracker .
echo "=== Exporting to tar ==="
docker save -o gaze-tracker.tar gaze-tracker
echo "=== Done ==="
echo "Load on target: docker load -i gaze-tracker.tar"
echo "Run: docker run -d --name gaze-tracker -p 8081:8081 -v /path/to/config:/app/config gaze-tracker"
