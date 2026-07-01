# SPDX-License-Identifier: Apache-2.0
"""System information executor - gathers host OS and resource info."""

import asyncio
import platform
from typing import Any

from .base import BaseExecutor, ExecResult


class SystemInfoExecutor(BaseExecutor):
    """Gather system information without shell commands."""

    async def execute(self, params: dict[str, Any]) -> ExecResult:
        try:
            hostname = platform.node()
            system = platform.system()
            release = platform.release()
            machine = platform.machine()
            processor = platform.processor()

            info_lines = [
                f"hostname: {hostname}",
                f"system: {system}",
                f"release: {release}",
                f"machine: {machine}",
                f"processor: {processor}",
            ]

            # Try to read OS-release info on Linux
            if system == "Linux":
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "cat", "/etc/os-release",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    stdout, _ = await proc.communicate()
                    if proc.returncode == 0:
                        for line in stdout.decode("utf-8", errors="replace").splitlines():
                            if "=" in line:
                                key, val = line.split("=", 1)
                                val = val.strip("\"'")
                                if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
                                    info_lines.append(f"os_{key.lower()}: {val}")
                except Exception:
                    pass

                # Memory info
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "free", "-h",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    stdout, _ = await proc.communicate()
                    if proc.returncode == 0:
                        mem_lines = stdout.decode("utf-8", errors="replace").splitlines()
                        if len(mem_lines) >= 2:
                            info_lines.append("memory: " + mem_lines[1])
                except Exception:
                    pass

            return ExecResult(success=True, output="\n".join(info_lines))
        except Exception as e:
            return ExecResult(success=False, error=f"system_info failed: {e}")
