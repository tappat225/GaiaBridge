"""
Remote MCP Server — allows external AI agents to operate this server remotely over HTTPS.

Exposed tools:
  - run_command    : execute shell commands (with timeout protection)
  - read_file      : read files under the workspace directory
  - write_file     : write files under the workspace directory
  - list_directory : list directory contents
  - system_info    : view system status (disk, memory, etc.)

Authentication is handled by Nginx via Authorization Bearer Token.
This service only processes the MCP protocol itself.
"""

import asyncio
import subprocess
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ============================================================
# Configuration
# ============================================================
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace"))
COMMAND_TIMEOUT = int(os.environ.get("COMMAND_TIMEOUT", "60"))  # seconds
ALLOWED_READ_EXTENSIONS = os.environ.get("ALLOWED_READ_EXTENSIONS", "").split(",") if os.environ.get("ALLOWED_READ_EXTENSIONS") else None  # None = allow all

# ============================================================
# FastMCP instance
# ============================================================
mcp = FastMCP(
    name="Remote Server Agent",
    instructions="""
You are an AI agent with remote access to a cloud server. Use the available tools to:
- Execute shell commands via run_command (commands have a {timeout}s timeout)
- Read and write files in the workspace directory
- List directory contents
- Check system status

Always verify your actions before executing. The workspace is the primary directory for file operations.
""".format(timeout=COMMAND_TIMEOUT),
    host="0.0.0.0",
    port=int(os.environ.get("MCP_PORT", "8000")),
)


# ============================================================
# Helper functions
# ============================================================
def _resolve_path(path: str) -> Path:
    """Resolve a user-supplied path into the workspace directory.

    Resolution rules:
      Relative paths             →  joined under WORKSPACE
        "foo/bar.txt"            →  /workspace/foo/bar.txt
      Absolute paths already     →  used directly (no double-prefix)
        under WORKSPACE             /workspace/foo  →  /workspace/foo
      Other absolute paths       →  rebased under WORKSPACE
        /home/me/x               →  /workspace/home/me/x

    Path traversal (../) is always denied.
    """
    ws = WORKSPACE.resolve()
    p = Path(path)

    if p.is_absolute():
        try:
            # Already under workspace? Use directly (avoids /workspace/foo
            # becoming /workspace/workspace/foo)
            p.relative_to(ws)
            resolved = p
        except ValueError:
            # Outside workspace — rebase: strip leading /, join under ws
            resolved = ws / p.relative_to("/")
    else:
        resolved = ws / p

    resolved = resolved.resolve()
    if not str(resolved).startswith(str(ws)):
        raise ValueError(f"Path traversal denied: {path} → {resolved}")
    return resolved


# ============================================================
# Tool definitions
# ============================================================
@mcp.tool()
async def run_command(command: str, cwd: str = ".") -> str:
    """Execute a shell command inside the workspace directory.

    The command runs with a timeout ({timeout}s). Working directory is relative
    to the workspace unless cwd is an absolute path within the workspace.

    Args:
        command: The shell command to execute.
        cwd: Working directory for the command, relative to workspace.

    Returns:
        stdout + stderr output of the command (truncated at 100KB).
    """.format(timeout=COMMAND_TIMEOUT)
    try:
        working_dir = _resolve_path(cwd)
        working_dir.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.wait_for(
            asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(working_dir),
            ),
            timeout=COMMAND_TIMEOUT,
        )

        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace")
        if len(output) > 100_000:
            output = output[:100_000] + "\n... [output truncated at 100KB]"
        return f"Exit code: {proc.returncode}\n\n{output}"
    except asyncio.TimeoutError:
        return f"Error: Command timed out after {COMMAND_TIMEOUT}s"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def read_file(path: str) -> str:
    """Read the contents of a file in the workspace.

    Args:
        path: Relative or absolute path within the workspace.

    Returns:
        File contents as string (truncated at 200KB).
    """
    try:
        filepath = _resolve_path(path)
        if not filepath.exists():
            return f"Error: File not found: {filepath.relative_to(WORKSPACE)}"
        if filepath.is_dir():
            return f"Error: Path is a directory, not a file: {filepath.relative_to(WORKSPACE)}"
        if ALLOWED_READ_EXTENSIONS and filepath.suffix not in ALLOWED_READ_EXTENSIONS:
            return f"Error: File extension '{filepath.suffix}' is not in allowed list"

        content = filepath.read_text(encoding="utf-8", errors="replace")
        if len(content) > 200_000:
            content = content[:200_000] + "\n... [content truncated at 200KB]"
        return content
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write content to a file in the workspace. Creates parent directories automatically.

    Args:
        path: Relative or absolute path within the workspace.
        content: The text content to write.

    Returns:
        Confirmation message with the file path.
    """
    try:
        filepath = _resolve_path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        rel = filepath.relative_to(WORKSPACE)
        size = len(content.encode("utf-8"))
        return f"Written {size} bytes to {rel}"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error writing file: {e}"


@mcp.tool()
async def list_directory(path: str = ".") -> str:
    """List the contents of a directory in the workspace.

    Args:
        path: Relative or absolute path within the workspace. Defaults to root.

    Returns:
        Directory listing with file sizes and types.
    """
    try:
        dirpath = _resolve_path(path)
        if not dirpath.exists():
            return f"Error: Directory not found: {dirpath.relative_to(WORKSPACE)}"
        if not dirpath.is_dir():
            return f"Error: Not a directory: {dirpath.relative_to(WORKSPACE)}"

        lines = []
        items = sorted(dirpath.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        for item in items:
            rel = item.relative_to(WORKSPACE)
            if item.is_dir():
                lines.append(f"{rel}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    sizestr = f"{size}B"
                elif size < 1024 * 1024:
                    sizestr = f"{size / 1024:.1f}KB"
                else:
                    sizestr = f"{size / (1024 * 1024):.1f}MB"
                lines.append(f"{rel}  ({sizestr})")

        if not lines:
            return f"Directory is empty: {dirpath.relative_to(WORKSPACE)}"
        return "\n".join(lines)
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


@mcp.tool()
async def system_info() -> str:
    """Get system information: disk usage, memory, and uptime.

    Returns:
        Summary of disk and memory usage.
    """
    try:
        # Disk usage
        disk = subprocess.run(
            ["df", "-h", str(WORKSPACE)],
            capture_output=True, text=True, timeout=10
        )
        # Memory
        mem = subprocess.run(
            ["free", "-h"],
            capture_output=True, text=True, timeout=10
        )
        # Uptime
        uptime = subprocess.run(
            ["uptime"],
            capture_output=True, text=True, timeout=10
        )
        return (
            f"=== Disk Usage ({WORKSPACE}) ===\n{disk.stdout}\n"
            f"=== Memory ===\n{mem.stdout}\n"
            f"=== Uptime ===\n{uptime.stdout}"
        )
    except Exception as e:
        return f"Error getting system info: {e}"


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    # streamable-http transport; host/port already set in FastMCP constructor
    mcp.run(transport="streamable-http")
