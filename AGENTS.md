# agent.md — GaiaBridge Programming Guide

> This file provides project-level context and rules for AI coding assistants (Claude, Copilot, etc.).

## Project Overview

GaiaBridge is a distributed multi-host remote operation and AI Agent coordination system. A central Master node manages multiple Worker nodes over HTTPS + SSE, enabling cross-network task execution.

| Component | Directory | Description |
|---|---|---|
| Shared | `shared/` | Protocol definitions, auth utilities, config schemas |
| Master | `master/` | Central control plane (Starlette + SSE + SQLite) |
| Worker | `worker/` | Execution daemon with pluggable executors |
| MCP Server (legacy) | `server/` | Single-node FastMCP + Docker |
| MCP Server (legacy) | `server/` | Single-node FastMCP + Docker |
| CLI Client (legacy) | `client/` | Command-line client + persistent session daemon |

## Rules

### 0. Structured Error Codes

Task results carry machine-readable error codes alongside human messages:

| Code | Meaning |
|---|---|
| `node_offline` | Target worker is not connected |
| `auth_denied` | Token missing or invalid |
| `capability_not_found` | Task type not supported by worker |
| `schema_invalid` | Request body failed validation |
| `workspace_violation` | Path resolved outside workspace boundary |
| `timeout` | Command or sync-wait exceeded deadline |
| `output_too_large` | Result output exceeded `max_output_size` |
| `execution_failed` | Generic execution error |
| `worker_unhealthy` | Worker reported unhealthy state |
| `rate_limited` | Too many requests |

The `TaskResult` model includes `error_code: Optional[str]` and `truncated: bool` fields.

### 0.1 Capability Vocabulary

Product-facing capability names (used in CLI and registration):

| Capability | Task Type | Description |
|---|---|---|
| `system.info` | `system_info` | Host OS and resource info |
| `file.list` | `list_dir` | List directory contents |
| `file.read` | `file_read` | Read file content |
| `file.write` | `file_write` | Write content to file |
| `shell.run` | `shell` | Execute shell command |

The `Capability` enum and mapping tables are in `shared/protocol.py`.

### 0.2 CLI Commands

| Command | Legacy Alias | Description |
|---|---|---|
| `gaia nodes` | `list_nodes` | List registered workers |
| `gaia run <node> <cmd>` | `run_command` | Execute shell command |
| `gaia read <node> <path>` | `read_file` | Read a file |
| `gaia write <node> <path> <content>` | `write_file` | Write content to a file |
| `gaia ls <node> [path]` | `list_directory` | List directory contents |
| `gaia info <node>` | `system_info` | Show system information |

Old command names remain usable for backward compatibility.

### 0.3 Output Size Limit

Worker config `max_output_size` (env: `MAX_OUTPUT_SIZE`) caps result output
at 200,000 bytes by default. Exceeding this returns `output_too_large` with an
empty output and truncated flag set.

Truncation is applied centrally in the worker daemon (`_truncate`) — executors
no longer hardcode their own slice limits, so the configured maximum is always
authoritative.

### 1. Default Language — English Only

All project content must be in English, including code (names, comments, docstrings), commit messages, program output, and log messages.

**Exception:** Documentation and README files may use other languages. End-user-facing UI strings may also use other languages when localization is explicitly required.

### 2. No Special Characters in Program Output

All program output (including `print()`, log messages, tool return strings, CLI output) **must NOT contain**:

- Emoji characters
- Unicode box-drawing or decorative characters
- ANSI escape sequences
- Fullwidth symbols or special Unicode punctuation
- Non-ASCII quotes, dashes, or ellipses

**Allowed character set:** ASCII printable characters only (0x20-0x7E).

### 3. No Hardcoded Secrets

- Tokens, keys, URLs, and domain names **must never** be hardcoded in source code
- Load application configuration through the project config loaders
- Environment variables may override file-based configuration for deployment and secrets
- Provide `config.toml.example` or `config.ini.example` template files with `<your-xxx>` placeholders
- Real config files must be listed in `.gitignore`

### 4. Configuration File Pattern

```
Real config (gitignored)     Template (committed)
------------------------     --------------------
master/config.toml           master/config.toml.example
worker/config.toml           worker/config.toml.example
client/config.ini            client/config.ini.example
```

When modifying configuration: update the matching `.example` template first, then inform the user to sync their local real config.

### 5. Directory Structure and Separation

- `shared/` — protocol models, auth utilities, config schemas (used by master + worker)
- `master/` — control plane (Starlette app, registry, broker, router, API endpoints)
- `worker/` — execution plane (daemon, executors, reporter)
- `server/` — legacy single-node MCP server (Docker-based)
- `client/` — legacy CLI client and daemon

Cross-directory imports must go through `shared/`. Master and Worker must not import from each other directly.

### 6. Protocol and Data Models

- All inter-service data structures are defined in `shared/protocol.py` using Pydantic
- Use `model_dump(mode="json")` for serialization
- Task types are enumerated in `TaskType`; node/task statuses in `NodeStatus`/`TaskStatus`
- New task types require adding to the enum and implementing a corresponding executor

### 7. Executor Pattern (Worker)

- All executors inherit from `worker/executor/base.py:BaseExecutor`
- Implement `async execute(self, params: dict) -> ExecResult`
- ExecResult has: `success: bool`, `output: str`, `error: str`
- New executors are registered in `worker/daemon.py:_handle_task()`

### 8. API Authentication

- Two token types: `NODE_TOKEN` (workers) and `CLIENT_TOKEN` (clients/agents)
- Node endpoints (`/api/nodes/*`, `/api/events`, `/api/tasks/result`) require Node Token
- Client endpoints (`/api/tasks/dispatch*`) require Client Token
- Tokens are passed as `Authorization: Bearer <token>` headers

### 9. SSE Communication

- Workers connect to `GET /api/events?node_id=X` with Node Token
- Master pushes task events as SSE with `event: task` and JSON data
- Master sends `event: ping` every 30s to keep connections alive
- Workers must handle reconnection on connection loss

### 10. Path Security

- **Container mode**: filesystem isolation is provided by Docker namespace boundaries
- **Host mode**: the worker has full host filesystem access; security is enforced
  at the tool-calling / Master layer rather than at the filesystem level
- **Workspace boundary enforcement**: all file and shell executors resolve paths
  against the configured workspace and reject paths that escape it, returning
  `workspace_violation` error code. Path traversal (`../../`) is blocked at the
  executor level for read, write, list, and shell cwd operations.
- Worker workspace is configured by `worker.workspace` or the `WORKSPACE_DIR`
  override. In container mode it defaults to `/workspace`; in host mode to `/`.
- The Docker host directory mounted at `/workspace` is controlled by
  `GAIABRIDGE_HOST_WORKSPACE`

### 11. Error Handling

- Executors return `ExecResult(success=False, error="...")` on failure — never raise
- Master API returns JSON error responses with appropriate HTTP status codes
- Worker reports failures via Reporter with `TaskStatus.failed`
- Shell commands have timeout protection via `asyncio.wait_for`

### 12. Python Code Style

- Use `asyncio` async patterns throughout master and worker
- Module-level constants: `UPPER_CASE`
- Function names: `snake_case`
- Import order: standard library -> third-party -> local modules
- Type hints on function signatures
- Pydantic models for all protocol data structures
- Dataclasses for configuration

### 13. Git Commits

- Commit messages must be in English, using a concise imperative style
- Example: `Add task dispatch endpoint to master API`
- Before committing, verify no sensitive files (.env, real config files, real tokens) are included

### 14. Docker Build

- **ARG scoping**: ARGs declared before `FROM` are only visible to the
  `FROM` instruction. To use them in `RUN` steps, re-declare them after
  `FROM` (without default values).
- **Build network**: Some cloud VMs have no DNS on Docker's default bridge.
  Use `DOCKER_BUILDKIT=0 docker build --network=host` to let build
  containers use the host network stack.
- **International mirrors**: Dockerfiles accept `APT_MIRROR` and
  `PIP_INDEX_URL` build args. Defaults are international (deb.debian.org,
  pypi.org). For China deployments, pass
  `APT_MIRROR=mirrors.tuna.tsinghua.edu.cn` and
  `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`.
- **No `.env` files**: Mirror configuration goes through docker-compose
  build args with environment variable overrides, not `.env` files.

### 15. SSE Implementation

- `sse-starlette` sends SSE events separated by `\r\n\r\n` (CRLF), per the
  SSE spec. Worker daemons must split the byte stream by `\r\n\r\n`, NOT
  `\n\n`.
- Workers must use an async HTTP client (`httpx`, `aiohttp`) for SSE
  streaming. Synchronous `urllib` may hang on uvicorn-served chunked
  responses.
- Master SSE endpoint (`/api/events?node_id=X`) requires Node Token auth.
  It uses server-sent events with `event: task` and `event: ping` types.
- Nginx must have `proxy_buffering off`, `proxy_cache off`, and long
  timeouts (`proxy_read_timeout 3600s`) for the SSE location block.

### 16. Workspace

- The workspace setting is a base directory for resolving relative task
  paths — it is not a security boundary.
- In **container mode**, Worker `config.toml` must use the container path
  (`/workspace`) for the workspace setting — NOT the host path. The
  user-selected host workspace is bind-mounted into that container path.
  Docker provides real filesystem isolation.
- In **host mode**, workspace is set to `/` (full host filesystem access).
  Security is enforced at the Master / tool-calling layer.
- `GAIABRIDGE_HOST_WORKSPACE` (env) controls which host directory is
  mounted to `/workspace` in the worker container (container mode only).

### 17. Deployment

- Root `deploy.py` is the single entry point for all deployments. It is
  entirely menu-driven — zero CLI arguments.
- Old `master/deploy.py` and `worker/deploy.py` are removed.
- Master deploys in container mode only (Docker). Worker supports both
  container and host modes.
- Host mode Worker deploys as a Linux systemd user service or a Windows
  Scheduled Task. Config is written to
  `~/.gaia_bridge/worker/config.toml`.
- Config directory `~/.gaia_bridge/` is cross-platform (Linux, macOS,
  Windows) and is the **canonical home for all persistent data**:
  ```
  ~/.gaia_bridge/
  ├── master/
  │   ├── config.toml         # Master configuration
  │   └── data/               # SQLite database + other persistent data
  ├── worker/
  │   ├── config.toml         # Worker configuration
  │   ├── app/                # Host-mode deployed application copy
  │   ├── bin/                # Host-mode launcher scripts
  │   ├── logs/               # Host-mode worker logs
  │   └── venv/               # Host-mode Python virtual environment
  └── workspace/              # Host-mode default workspace
  ```
- Docker containers mount config and data paths from `~/.gaia_bridge/` via environment
  variables (`GAIABRIDGE_MASTER_CONFIG`, `GAIABRIDGE_MASTER_DATA`,
  `GAIABRIDGE_WORKER_CONFIG`). Worker container mode mounts the
  user-selected host workspace via `GAIABRIDGE_HOST_WORKSPACE`. The
  docker-compose files accept these env vars for the host-side paths
  while the container-side paths stay fixed (`/etc/gaia_bridge/`,
  `/app/data/`, `/workspace`).
