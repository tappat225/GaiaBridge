#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

CONFIG_PATH="${WORKBRIDGE_CONFIG_FILE:-config.toml}"

host_workspace="$(
  python3 - "$CONFIG_PATH" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as f:
    config = tomllib.load(f)

host_workspace = config.get("deployment", {}).get("host_workspace", "")
if not host_workspace:
    raise SystemExit("deployment.host_workspace is required")

print(host_workspace)
PY
)"

container_workspace="$(
  python3 - "$CONFIG_PATH" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as f:
    config = tomllib.load(f)

workspace = config.get("worker", {}).get("workspace", "/workspace")
print(workspace)
PY
)"

if [[ "$host_workspace" != /* ]]; then
  echo "deployment.host_workspace must be an absolute host path: $host_workspace" >&2
  exit 1
fi

if [[ "$container_workspace" != /* ]]; then
  echo "worker.workspace must be an absolute container path: $container_workspace" >&2
  exit 1
fi

mkdir -p "$host_workspace"

export WORKBRIDGE_HOST_WORKSPACE="$host_workspace"
export WORKBRIDGE_CONTAINER_WORKSPACE="$container_workspace"
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-0}"

docker compose up -d --build
