# WorkBridge

Remote server control via MCP (Model Context Protocol). Allows an AI agent to safely operate a remote Linux server over HTTPS — execute shell commands, read/write files, and check system status.

## Directory Structure

```
WorkBridge/
├── server/                         # Server: Docker container + MCP Server
│   ├── server.py                   #   FastMCP application
│   ├── Dockerfile                  #   Container image
│   ├── docker-compose.yml          #   One-command startup
│   ├── requirements.txt            #   Python dependencies
│   ├── nginx-mcp.conf.example      #   Nginx config template
│   └── .env.example                #   Environment variable template
├── client/                         # Client: CLI + Daemon
│   ├── mcp_client.py               #   Command-line client
│   ├── mcp_daemon.py               #   Persistent session daemon
│   ├── test_nginx.py               #   End-to-end test script
│   └── .env.example                #   Environment variable template
├── README.md
└── .gitignore
```

## Architecture

```
Remote AI Agent
       │
       ▼
HTTPS + Bearer Token Auth (Nginx)
       │
       ▼
WorkBridge MCP Server  (FastMCP, streamable-HTTP)
  ── runs inside Docker container
       │
       ▼
Host filesystem  (mounted at /workspace inside container)
```

- **Server:** Python FastMCP app (`server/server.py`) — exposes 5 MCP tools over HTTP
- **Daemon:** `client/mcp_daemon.py` — persistent session manager via Unix socket (avoids TLS handshake per call)
- **Client:** `client/mcp_client.py` — CLI for ad-hoc commands; auto-detects daemon or falls back to direct HTTPS
- **Proxy:** Nginx handles TLS termination and Bearer token validation, then forwards to the container

## Tools

| Tool | What it does |
|---|---|
| `run_command` | Execute a shell command (timeout configurable) |
| `read_file` | Read text from a file |
| `write_file` | Write / overwrite a text file (creates parent dirs) |
| `list_directory` | List directory contents with sizes |
| `system_info` | Disk usage, memory, uptime |

All paths are **relative to the workspace root** (`/workspace` inside the container).

## Quick Start

### 1. Configure the server

```bash
cd server/

# Create real config files from templates
cp nginx-mcp.conf.example nginx-mcp.conf
cp .env.example .env

# Edit nginx-mcp.conf: replace <your-bearer-token> with a real token
# Edit .env: set workspace directory and timeout as needed
```

Merge the content of `nginx-mcp.conf` into your Nginx HTTPS server block.

### 2. Build & run the server

```bash
cd server/
docker compose up -d --build
```

Server listens on `127.0.0.1:9020` (local only — exposed by Nginx).

### 3. Configure the client

```bash
cd client/

# Create real config file from template
cp .env.example .env

# Edit .env: fill in your real MCP_URL and AUTH_TOKEN
# Then load it in your shell: source .env
```

### 4. Use the CLI client

```bash
cd client/

# Load environment variables
source .env

# Direct HTTPS (TLS + MCP handshake on every call)
python3 mcp_client.py write_file path/to/file.txt "content here"
python3 mcp_client.py read_file path/to/file.txt
python3 mcp_client.py run_command "ls -la"
python3 mcp_client.py list_directory .
python3 mcp_client.py system_info

# Interactive shell
python3 mcp_client.py shell
```

### 5. Start the daemon (faster — keeps one MCP session alive)

```bash
cd client/
source .env

python3 mcp_daemon.py --daemonize   # start in background
python3 mcp_client.py write_file ... # automatically uses daemon socket
python3 mcp_daemon.py --stop        # stop when done
```

### 6. Connect an AI agent

Point any MCP-compatible client to `https://<your-domain>/_mcp` with header:

```
Authorization: Bearer <your-token>
```

The server follows the standard MCP JSON-RPC protocol over streamable HTTP.

## Configuration

### Server (`server/.env`)

| Env var | Default | Description |
|---|---|---|
| `WORKSPACE_DIR` | `/workspace` | Root directory for all file operations |
| `COMMAND_TIMEOUT` | `60` | Shell command timeout in seconds |
| `MCP_PORT` | `8000` | Port the MCP server listens on |
| `ALLOWED_READ_EXTENSIONS` | (all) | Comma-separated list of allowed file extensions |

### Client (`client/.env`)

| Env var | Default | Description |
|---|---|---|
| `MCP_URL` | `https://<your-domain>/_mcp` | MCP server endpoint URL |
| `AUTH_TOKEN` | `<your-bearer-token>` | Bearer token for authentication |
| `MCP_SOCKET_PATH` | `/tmp/mcp-daemon.sock` | Daemon Unix socket path |
| `MCP_PID_FILE` | `/tmp/mcp-daemon.pid` | Daemon PID file path |

### Nginx (`server/nginx-mcp.conf`)

Copy `nginx-mcp.conf.example` to `nginx-mcp.conf`, replace `<your-bearer-token>` with a real token, then merge the content into your Nginx HTTPS server block.

## Filesystem Mapping

The container mounts the host's repo directory:

```
Host:  /home/ubuntu/repo/
              │
              ├── WorkBridge/       ← this project
              ├── new-project/      ← projects you create via the agent
              └── ...               ← anything else you put there
              │
              ▼  (Docker volume mount)
Container:  /workspace/
```

**What this means in practice:** When the agent writes to `new-project/hello.txt`, the file appears at `/home/ubuntu/repo/new-project/hello.txt` on the host. The agent sees `/workspace`; you see `/home/ubuntu/repo`. Everything else is the same relative structure.

## Path Resolution Rules

| You send | Resolves to (in container) | Maps to (on host) |
|---|---|---|
| `new-project/hello.txt` | `/workspace/new-project/hello.txt` | `/home/ubuntu/repo/new-project/hello.txt` |
| `/workspace/new-project/hello.txt` | `/workspace/new-project/hello.txt` | `/home/ubuntu/repo/new-project/hello.txt` |
| `/workspace/foo/bar` | `/workspace/foo/bar` | `/home/ubuntu/repo/foo/bar` |
| `../../etc/passwd` | **denied** (path traversal) | — |

**Key rule:** `/workspace` is the root of your world. Both `new-project/hello.txt` and `/workspace/new-project/hello.txt` point to the same location.

## Security

- **No hardcoded secrets** — tokens and URLs are loaded from environment variables or local config files (gitignored)
- **Path traversal blocked** — `../` and absolute paths outside `/workspace` are rejected
- **Bearer token required** — Nginx rejects unauthenticated requests
- **Local-only container port** — MCP server binds to `127.0.0.1`, not exposed to the internet
- **Non-root user** — Container runs as `mcp` user, not root
- **Command timeout** — Long-running commands are killed automatically

## Troubleshooting

### Agent wrote files but I can't find them

Check the path you used. If you sent `/workspace/new-project/file.txt`, the file is at `/home/ubuntu/repo/new-project/file.txt` on the host — **not** `/home/ubuntu/repo/workspace/new-project/file.txt`. The `/workspace` prefix inside the container maps to `/home/ubuntu/repo` on the host.

### "Path traversal denied" error

You tried to access a path outside `/workspace`. Use relative paths or paths starting with `/workspace/`.

### Daemon won't start

Check if a stale instance is running: `python3 mcp_daemon.py --stop` then retry.

### Client can't connect

Make sure you've sourced the `.env` file: `source client/.env`
Verify the env vars are set: `echo $MCP_URL`
