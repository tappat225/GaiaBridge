# WorkBridge Client — Agent Usage Guide

> This document teaches AI agents how to use WorkBridge to operate a remote Linux server. Read it before executing any tools on the remote host.

## Setup

Before any tool calls, ensure these environment variables are set:

```bash
source client/.env
```

Required variables:
- `MCP_URL` — the server endpoint (e.g. `https://your-domain/_mcp`)
- `AUTH_TOKEN` — the Bearer token for authentication

Verify connectivity with `system_info` before doing anything else.

## Available Tools

### run_command — execute a shell command

```
python3 client/mcp_client.py run_command "<shell command>"
```

- Timeout is set by the server (default 60s, configurable).
- Output is truncated at 100KB.
- The working directory defaults to the workspace root. Use `cd` within the command if needed.
- Commands run inside a Docker container — you see the container's filesystem, not the host's directly.

**Good patterns:**
```
run_command "ls -la"
run_command "cat file.txt | head -20"
run_command "python3 script.py"
run_command "cd subdir && make"
```

**Avoid:**
- Interactive commands (`vim`, `less`, `top` without `-n1`)
- Commands that may run indefinitely without producing output
- `sudo` (container runs as non-root)

### read_file — read a file

```
python3 client/mcp_client.py read_file "<path>"
```

- Content is truncated at 200KB.
- Paths are relative to the workspace root, or absolute within `/workspace`.
- The server may restrict which file extensions are readable.

### write_file — create or overwrite a file

```
python3 client/mcp_client.py write_file "<path>" "<content>"
```

- Parent directories are created automatically.
- Content is written as UTF-8 text.
- The file path is relative to the workspace root.
- This is an overwrite operation — it replaces the file entirely if it exists.

**For multi-line content**, use the daemon shell mode or write a heredoc via `run_command`:
```
run_command "cat > file.txt << 'EOF'
line 1
line 2
EOF"
```

### list_directory — list a directory

```
python3 client/mcp_client.py list_directory "<path>"
python3 client/mcp_client.py list_directory .          # workspace root
```

- Shows files with human-readable sizes (B, KB, MB).
- Directories are marked with a trailing `/`.
- Items are sorted: directories first, then alphabetically.

### system_info — check server health

```
python3 client/mcp_client.py system_info
```

- Reports disk usage for the workspace volume.
- Shows memory usage (total, used, free).
- Shows server uptime.

Use this first to verify connectivity, and periodically to check resource availability before large operations.

## Path Rules

All file paths are resolved relative to the **workspace root** (`/workspace` inside the container).

| You send | Resolves to |
|---|---|
| `project/main.py` | `/workspace/project/main.py` |
| `/workspace/project/main.py` | `/workspace/project/main.py` |
| `../etc/passwd` | **denied** (path traversal) |

**Key point:** The `/workspace` prefix is the container-side view. On the host, `/workspace/project/` maps to `/home/ubuntu/repo/project/`. You do not need to worry about the host path — just use workspace-relative paths.

## Daemon Mode (Faster)

If the daemon is running, all client commands reuse a single MCP session, avoiding the TLS + MCP handshake overhead:

```bash
# Start once
python3 client/mcp_daemon.py --daemonize

# All subsequent calls automatically use the daemon
python3 client/mcp_client.py run_command "whoami"
python3 client/mcp_client.py read_file config.yaml

# Stop when done
python3 client/mcp_daemon.py --stop
```

The client auto-detects the daemon socket. No special flags needed.

## Best Practices

1. **Verify first.** Run `system_info` as your first command to confirm connectivity and check disk space.

2. **Explore before writing.** Use `list_directory` and `read_file` to understand the existing structure before creating or modifying files.

3. **Check command results.** Every `run_command` returns an exit code. A non-zero exit code means the command failed — read the output before proceeding.

4. **One command at a time.** The MCP protocol is request-response. Chain operations sequentially, not in parallel.

5. **Use relative paths.** Prefer `project/file.txt` over `/workspace/project/file.txt` — both work, but relative paths are shorter and less error-prone.

6. **Clean up test artifacts.** If you create temporary files or directories during exploration, remove them when done.

7. **Respect the timeout.** If a command needs more than 60 seconds, break it into smaller steps. Long-running builds or downloads are fine — the server timeout can be configured up to 120s.

8. **Prefer write_file for small files.** For configuration files and scripts under ~10KB, `write_file` is simpler than heredocs via `run_command`.

## Interactive Shell

For exploratory work, the interactive shell mode lets you type commands directly:

```bash
cd client/ && source .env
python3 mcp_client.py shell
```

At the `>` prompt, type tool invocations without the `python3 mcp_client.py` prefix:

```
> system_info
> list_directory .
> read_file README.md
> run_command ls -la
> exit
```

Type `help` inside the shell for a quick reference.

## Error Recovery

| Symptom | Likely cause | Action |
|---|---|---|
| `HTTP 401` | Wrong or expired token | Check `AUTH_TOKEN` in `client/.env` |
| `HTTP 502` or connection refused | Server is down | Ask the operator to restart the Docker container |
| `Path traversal denied` | Used `../` or an absolute path outside `/workspace` | Use a workspace-relative path |
| `File not found` | Wrong path or file doesn't exist | Use `list_directory` to verify the path |
| `Command timed out` | Command took too long | Break it into smaller steps, or increase `COMMAND_TIMEOUT` server-side |
| `[truncated at XKB]` | Output exceeded the limit | Use `grep`, `head`, or `tail` to narrow the output |

## Security Boundaries

As an agent, you operate within these limits:

- **Workspace sandbox.** All file access is confined to the workspace directory. You cannot read or write outside it.
- **No root access.** The container runs as a non-root `mcp` user. Commands that require `sudo` will fail.
- **Token-gated.** Every request is authenticated. The token is set by the server operator and cannot be changed from the client side.
- **Timeout kills.** Commands running longer than the configured timeout are terminated automatically.

If you legitimately need to operate outside these boundaries (e.g., install a system package), coordinate with the server operator — do not attempt to bypass the restrictions.
