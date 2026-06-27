#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

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

if [[ ! -f config.toml ]]; then
  echo "config.toml not found. Copy config.toml.example and fill tokens first." >&2
  exit 1
fi

export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-0}"

if [[ "$USE_CN_MIRRORS" == "1" ]]; then
  export APT_MIRROR="${APT_MIRROR:-mirrors.tuna.tsinghua.edu.cn}"
  export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
fi

docker compose up -d --build
