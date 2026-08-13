#!/usr/bin/env bash
set -euo pipefail

# Start the local ClearML services and expose one loopback URL:
#   http://127.0.0.1:8080/          ClearML Web
#   http://127.0.0.1:8080/research/ Research Hub experiment workbench
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOW_ROOT="$(cd -- "$ROOT_DIR/../../.." && pwd)"
cd "$ROOT_DIR"
./start_local_server.sh
cd "$WORKFLOW_ROOT"
echo "Open the unified editable workspace at http://127.0.0.1:8080/research/ (no token required)."
echo "ClearML Task details at /projects/<project_id>/tasks/<task_id>/general show same-page buttons for ClearML and 实验校阅工作台."
exec "${RESEARCH_HUB_PYTHON:-python}" -m research_hub gateway \
  --host 127.0.0.1 \
  --port 8080 \
  --hub-port 8765 \
  --clearml-host 127.0.0.1 \
  --clearml-port 8082
