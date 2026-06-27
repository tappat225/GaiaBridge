"""File operation executor."""

from pathlib import Path
from typing import Any

from .base import BaseExecutor, ExecResult


class FileExecutor(BaseExecutor):
    def __init__(self, workspace: str):
        self._workspace = Path(workspace).resolve()

    def _resolve(self, path: str) -> Path:
        p = (self._workspace / path).resolve()
        if not str(p).startswith(str(self._workspace)):
            raise ValueError("path traversal denied")
        return p

    async def execute(self, params: dict[str, Any]) -> ExecResult:
        action = params.get("action", "read")
        try:
            if action == "read":
                return await self._read(params["path"])
            elif action == "write":
                return await self._write(params["path"], params["content"])
            elif action == "list":
                return await self._list(params.get("path", "."))
            else:
                return ExecResult(success=False, error=f"unknown action: {action}")
        except ValueError as e:
            return ExecResult(success=False, error=str(e))
        except Exception as e:
            return ExecResult(success=False, error=str(e))

    async def _read(self, path: str) -> ExecResult:
        fp = self._resolve(path)
        if not fp.exists():
            return ExecResult(success=False, error=f"file not found: {path}")
        content = fp.read_text(encoding="utf-8", errors="replace")[:200_000]
        return ExecResult(success=True, output=content)

    async def _write(self, path: str, content: str) -> ExecResult:
        fp = self._resolve(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        size = len(content.encode("utf-8"))
        return ExecResult(success=True, output=f"Written {size} bytes to {path}")

    async def _list(self, path: str) -> ExecResult:
        dp = self._resolve(path)
        if not dp.is_dir():
            return ExecResult(success=False, error=f"not a directory: {path}")
        items = sorted(dp.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = []
        for item in items:
            rel = item.relative_to(self._workspace)
            if item.is_dir():
                lines.append(f"{rel}/")
            else:
                lines.append(f"{rel}  ({item.stat().st_size}B)")
        return ExecResult(success=True, output="\n".join(lines) if lines else "(empty)")
