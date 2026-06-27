# agent.md — WorkBridge Programming Guide

> This file provides project-level context and rules for AI coding assistants (Claude, Copilot, etc.).

## Project Overview

WorkBridge is a distributed multi-host remote operation and AI Agent coordination system. A central Master node manages multiple Worker nodes over HTTPS + SSE, enabling cross-network task execution.

| Component | Directory | Description |
|---|---|---|
| Shared | `shared/` | Protocol definitions, auth utilities, config schemas |
| Master | `master/` | Central control plane (Starlette + SSE + SQLite) |
| Worker | `worker/` | Execution daemon with pluggable executors |
| MCP Server (legacy) | `server/` | Single-node FastMCP + Docker |
| CLI Client (legacy) | `client/` | Command-line client + persistent session daemon |

## Rules

### 1. Default Language — English Only

**All content in this project must be in English**, including:

- Variable names, function names, class names in code
- Code comments and docstrings
- Commit messages
- Documentation and README
- Program output (stdout/stderr)
- Log messages

Non-English text is prohibited in any of the above contexts, except for end-user-facing UI strings where localization is explicitly required.

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
- Always use `os.environ.get("VAR_NAME", "placeholder")` to read from environment
- Provide `.env.example` template files with `<your-xxx>` placeholders
- Real config files must be listed in `.gitignore`

### 4. Configuration File Pattern

```
Real config (gitignored)     Template (committed)
------------------------     --------------------
server/.env                  server/.env.example
client/.env                  client/.env.example
```

When modifying configuration: update the `.example` template first, then inform the user to sync their local real config.

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

- All file operations in executors must validate paths against workspace boundary
- Use `Path.resolve()` + `startswith()` check against workspace root
- Path traversal (`../`) must be denied
- Workspace root is controlled by `WORKSPACE_DIR` environment variable

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
- Before committing, verify no sensitive files (.env, real tokens) are included
