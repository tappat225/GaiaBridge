#!/usr/bin/env python3
"""Cross-platform deploy script for GaiaBridge worker."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def read_toml_value(config_path, section, key, fallback=""):
    in_section = False
    with open(config_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("["):
                in_section = stripped.strip("[] ") == section
                continue
            if in_section and "=" in stripped:
                k, _, v = stripped.partition("=")
                k = k.strip()
                if k == key:
                    v = v.split("#")[0].strip().strip('"')
                    return v
    return fallback


def main():
    parser = argparse.ArgumentParser(description="Deploy GaiaBridge worker")
    parser.add_argument("--cn", action="store_true", help="Use China mirrors for apt/pip")
    args = parser.parse_args()

    os.chdir(SCRIPT_DIR)

    config_path = os.environ.get("GAIABRIDGE_CONFIG_FILE", "config.toml")
    if not Path(config_path).exists():
        sys.exit(f"error: config file not found: {config_path}")

    host_workspace = read_toml_value(config_path, "deployment", "host_workspace")
    container_workspace = read_toml_value(config_path, "worker", "workspace", "/workspace")

    if not host_workspace:
        sys.exit("error: deployment.host_workspace is required in config")

    # Validate absolute path (Unix / or Windows drive letter)
    host_path = Path(host_workspace)
    if not host_path.is_absolute():
        sys.exit(f"error: deployment.host_workspace must be absolute: {host_workspace}")

    if not container_workspace.startswith("/"):
        sys.exit(f"error: worker.workspace must be an absolute container path: {container_workspace}")

    host_path.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["GAIABRIDGE_HOST_WORKSPACE"] = host_workspace
    env["GAIABRIDGE_CONTAINER_WORKSPACE"] = container_workspace
    env.setdefault("DOCKER_BUILDKIT", "0")

    if args.cn:
        env.setdefault("APT_MIRROR", "mirrors.tuna.tsinghua.edu.cn")
        env.setdefault("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")

    print(f"Deploying worker...")
    print(f"  Host workspace:      {host_workspace}")
    print(f"  Container workspace: {container_workspace}")

    result = subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        env=env,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
