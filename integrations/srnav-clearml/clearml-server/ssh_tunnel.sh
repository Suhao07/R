#!/usr/bin/env bash
set -euo pipefail

# Optional remote-access helper.  The server itself remains loopback-only on
# the host.  Usage: ./ssh_tunnel.sh user@gpu-host [ssh-options...]
if [[ $# -lt 1 ]]; then
  echo "usage: $0 user@host [ssh-options...]" >&2
  exit 2
fi

exec ssh "$@" \
  -N \
  -o ExitOnForwardFailure=yes \
  -L 8008:127.0.0.1:8008 \
  -L 8080:127.0.0.1:8080 \
  -L 8081:127.0.0.1:8081
