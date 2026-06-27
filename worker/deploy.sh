#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

CONFIG_PATH="${WORKBRIDGE_CONFIG_FILE:-config.toml}"
USE_CN_MIRRORS=0

usage() {
  cat <<'EOF'
Usage: ./deploy.sh [--cn]

Options:
  --cn       Use China mirrors for apt and pip during Docker build.
  -h, --help Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cn)
      USE_CN_MIRRORS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

toml_get() {
  local section="$1"
  local key="$2"
  local fallback="${3:-}"

  awk -v section="$section" -v key="$key" -v fallback="$fallback" '
    /^[[:space:]]*\[/ {
      in_section = ($0 ~ "^[[:space:]]*\\[" section "\\][[:space:]]*($|#)")
      next
    }
    in_section {
      line = $0
      sub(/[[:space:]]*#.*/, "", line)
      pattern = "^[[:space:]]*" key "[[:space:]]*="
      if (line ~ pattern) {
        sub(pattern "[[:space:]]*", "", line)
        sub(/[[:space:]]+$/, "", line)
        if (line ~ /^".*"$/) {
          sub(/^"/, "", line)
          sub(/"$/, "", line)
        }
        print line
        found = 1
        exit
      }
    }
    END {
      if (!found && fallback != "") {
        print fallback
      }
    }
  ' "$CONFIG_PATH"
}

host_workspace="$(toml_get deployment host_workspace)"
container_workspace="$(toml_get worker workspace /workspace)"

if [[ -z "$host_workspace" ]]; then
  echo "deployment.host_workspace is required" >&2
  exit 1
fi

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

if [[ "$USE_CN_MIRRORS" == "1" ]]; then
  export APT_MIRROR="${APT_MIRROR:-mirrors.tuna.tsinghua.edu.cn}"
  export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
fi

docker compose up -d --build
