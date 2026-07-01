# SPDX-License-Identifier: Apache-2.0
"""File operation executor with workspace boundary enforcement."""

from pathlib import Path
from typing import Any

from .base import BaseExecutor, ExecResult
from shared.protocol import ErrorCode


class FileExecutor(BaseExecutor):
    def __init__(self, workspace: str):
        self._workspace = Path(workspace).resolve()

    def _resolve(self, path: str) -> tuple[Path, str | None]:
        """Resolve path against workspace and validate boundary.

        Returns (resolved_path, None) on success, or (None, error_code) if
        the path escapes the workspace.
        """
        resolved = (self._workspace / path).resolve()
        try:
            resolved.relative_to(self._workspace)
        except ValueError:
            return None, ErrorCode.workspace_violation.value
        return resolved, None

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
        except Exception as e:
            return ExecResult(success=False, error=str(e))

    async def _read(self, path: str) -> ExecResult:
        fp, err = self._resolve(path)
        if err:
            return ExecResult(success=False, error=f"path escapes workspace: {path}", error_code=err)
        if not fp.exists():
            return ExecResult(success=False, error=f"file not found: {path}")
        content = fp.read_text(encoding="utf-8", errors="replace")
        return ExecResult(success=True, output=content)

    async def _write(self, path: str, content: str) -> ExecResult:
        fp, err = self._resolve(path)
        if err:
            return ExecResult(success=False, error=f"path escapes workspace: {path}", error_code=err)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        size = len(content.encode("utf-8"))
        return ExecResult(success=True, output=f"Written {size} bytes to {path}")

    async def _list(self, path: str) -> ExecResult:
        dp, err = self._resolve(path)
        if err:
            return ExecResult(success=False, error=f"path escapes workspace: {path}", error_code=err)
        if not dp.is_dir():
            return ExecResult(success=False, error=f"not a directory: {path}")
        items = sorted(dp.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = []
        for item in items:
            if item.is_dir():
                lines.append(f"{item.name}/")
            else:
                lines.append(f"{item.name}  ({item.stat().st_size}B)")
        return ExecResult(success=True, output="\n".join(lines) if lines else "(empty)")
