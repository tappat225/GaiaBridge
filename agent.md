# agent.md — WorkBridge Programming Guide

> This file provides project-level context and rules for AI coding assistants (Claude, Copilot, etc.).

## Project Overview

WorkBridge is an MCP (Model Context Protocol) based remote server control system. AI agents can safely operate a remote Linux server over HTTPS — execute commands, read/write files, and check system status.

| Component | Directory | Description |
|---|---|---|
| MCP Server | `server/` | FastMCP + Docker, exposes 5 tools |
| CLI Client | `client/` | Command-line client + persistent session daemon |
| Nginx | `server/nginx-mcp.conf` | TLS termination + Bearer token authentication |

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

All program output (including `print()`, log messages, MCP tool return strings, CLI output) **must NOT contain**:

- Emoji characters (e.g. checkmarks, crosses, warning signs, folders)
- Unicode box-drawing or decorative characters (e.g. ─ ═ ▸ ●)
- ANSI escape sequences (color codes, bold, blink, etc.)
- Fullwidth symbols or special Unicode punctuation
- Non-ASCII quotes, dashes, or ellipses

**Allowed character set:** ASCII printable characters only (0x20–0x7E), including English letters, digits, and standard punctuation.

**Correct:**
```
Written 1024 bytes to path/to/file.txt
Error: File not found: config.yaml
Exit code: 0
```

**Incorrect:**
```
✅ Written 1024 bytes to path/to/file.txt   ← emoji
Error: File not found —— config.yaml       ← fullwidth dash
```

### 3. No Hardcoded Secrets

- Tokens, keys, URLs, and domain names **must never** be hardcoded in source code
- Always use `os.environ.get("VAR_NAME", "placeholder")` to read from environment
- Provide `.env.example` template files with `<your-xxx>` placeholders
- Real config files must be listed in `.gitignore`
- Before committing, verify: `grep -rn "password\|token\|secret\|api_key" --include="*.py" --include="*.conf"` returns no real values

### 4. Configuration File Pattern

```
Real config (gitignored)     Template (committed)
------------------------     --------------------
server/.env                  server/.env.example
server/nginx-mcp.conf        server/nginx-mcp.conf.example
client/.env                  client/.env.example
```

When modifying configuration: update the `.example` template first, then inform the user to sync their local real config.

### 5. Directory Separation

- `server/` — all server-side code (FastMCP, Docker, Nginx config)
- `client/` — all client-side code (CLI, Daemon, test scripts)
- Do not cross-reference code across directories; if shared logic is needed, extract it into a `common/` or `shared/` directory

### 6. MCP Tool Return Value Convention

- All functions decorated with `@mcp.tool()` **must return a string** (MCP protocol requires `text` content type)
- Error messages start with `Error: ` prefix
- Success results are plain text: single results on one line, multiple results one per line
- File sizes use human-readable format (`1024B` / `1.0KB` / `2.5MB`)

### 7. Path Security

- All tool function path parameters **must** go through `_resolve_path()`
- Path traversal (`../`) must be detected and rejected after resolution
- Absolute paths outside the workspace should be rebased under the workspace rather than outright rejected (see `_resolve_path` in `server.py`)
- Workspace root is controlled by the `WORKSPACE_DIR` environment variable, defaulting to `/workspace`

### 8. Error Handling

- MCP tool functions use try/except and return error strings instead of raising exceptions
- Command execution has timeout protection (`asyncio.wait_for` + `COMMAND_TIMEOUT`)
- File reads are capped at 200KB with truncation notice
- Command output is capped at 100KB with truncation notice
- Truncated output appends `... [truncated at XKB]` at the end

### 9. Testing

- End-to-end test script: `client/test_nginx.py`
- Tests cover all 5 MCP tools: write_file -> read_file -> run_command -> list_directory -> system_info
- After modifying tool signatures in `server.py`, **must sync** the `arguments` dicts in the test script
- Docker test environment requires the container to be running and Nginx proxying correctly

### 10. Python Code Style

- Use `asyncio` async patterns (tool functions in `server.py`)
- Module-level constants: `UPPER_CASE`
- Function names: `snake_case`
- Configuration variables are grouped in a `# === Configuration ===` block at the top of each file
- Import order: standard library -> third-party -> local modules, with a blank line between groups
- Match the existing comment density — comment key logic and configuration; self-documenting code does not require forced comments

### 11. Docker & Deployment

- Docker Compose is run from the `server/` directory: `cd server && docker compose up -d --build`
- The container runs as the non-root `mcp` user
- MCP Server port (8000) binds only to `127.0.0.1`; Nginx reverse-proxies it externally
- After modifying `Dockerfile` or `requirements.txt`, rebuild the image with `--build`

### 12. Git Commits

- Commit messages must be in English, using a concise imperative style
- Example: `Add command timeout to run_command tool`
- Before committing, run `git diff --staged` to verify no sensitive files (.env, nginx-mcp.conf, etc.) are included
