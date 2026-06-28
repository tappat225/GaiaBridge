#!/usr/bin/env python3
"""Cross-platform deploy script for WorkBridge master."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Deploy WorkBridge master")
    parser.add_argument("--cn", action="store_true", help="Use China mirrors for apt/pip")
    args = parser.parse_args()

    os.chdir(SCRIPT_DIR)

    if not Path("config.toml").exists():
        sys.exit("error: config.toml not found. Copy config.toml.example and fill tokens first.")

    env = os.environ.copy()
    env.setdefault("DOCKER_BUILDKIT", "0")

    if args.cn:
        env.setdefault("APT_MIRROR", "mirrors.tuna.tsinghua.edu.cn")
        env.setdefault("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")

    print("Deploying master...")

    result = subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        env=env,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
