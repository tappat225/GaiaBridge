"""Shell command executor."""

import asyncio
from pathlib import Path
from typing import Any

from .base import BaseExecutor, ExecResult


class ShellExecutor(BaseExecutor):
    def __init__(self, workspace: str, timeout: int = 120):
        self._workspace = Path(workspace).resolve()
        self._timeout = timeout

    async def execute(self, params: dict[str, Any]) -> ExecResult:
        command = params.get("command", "")
        cwd = params.get("cwd", ".")

        work_dir = (self._workspace / cwd).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(work_dir)),
                timeout=self._timeout)
            stdout, _ = await proc.communicate()
            output = stdout.decode("utf-8", errors="replace")[:100_000]
            return ExecResult(
                success=(proc.returncode == 0),
                output=f"Exit code: {proc.returncode}\n{output}")
        except asyncio.TimeoutError:
            return ExecResult(success=False, error=f"command timed out after {self._timeout}s")
        except Exception as e:
            return ExecResult(success=False, error=str(e))
