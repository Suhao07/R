#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
mkdir -p state/logs state/config state/data/fileserver state/data/mongo_4/db \
  state/data/mongo_4/configdb state/data/redis state/data/elastic_7

docker compose -f docker-compose.yml config >/dev/null
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml ps
echo "ClearML Web upstream: http://127.0.0.1:8082"
echo "Run ./start_unified_ui.sh for the single http://127.0.0.1:8080 entry."
