# WorkBridge

Remote server control via MCP (Model Context Protocol). Allows an AI agent to safely operate a remote Linux server over HTTPS — execute shell commands, read/write files, and check system status.

## Directory Structure

```
WorkBridge/
├── server/                  # 服务端：Docker 容器 + MCP Server
│   ├── server.py            #   FastMCP 主程序
│   ├── Dockerfile           #   容器镜像
│   ├── docker-compose.yml   #   一键启动
│   ├── requirements.txt     #   Python 依赖
│   ├── nginx-mcp.conf.example  # Nginx 配置模板
│   └── .env.example         #   环境变量模板
├── client/                  # 客户端：CLI + Daemon
│   ├── mcp_client.py        #   命令行客户端
│   ├── mcp_daemon.py        #   持久会话守护进程
│   ├── test_nginx.py        #   端到端测试脚本
│   └── .env.example         #   环境变量模板
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

# 创建真实配置文件
cp nginx-mcp.conf.example nginx-mcp.conf
cp .env.example .env

# 编辑 nginx-mcp.conf，替换 <your-bearer-token> 为真实 token
# 编辑 .env，设置工作目录和超时等参数
```

将 `nginx-mcp.conf` 的内容合并到你的 Nginx HTTPS server 块中。

### 2. Build & run the server

```bash
cd server/
docker compose up -d --build
```

Server listens on `127.0.0.1:9020` (local only — exposed by Nginx).

### 3. Configure the client

```bash
cd client/

# 创建真实配置文件
cp .env.example .env

# 编辑 .env，填入真实的 MCP_URL 和 AUTH_TOKEN
# 然后在 shell 中加载：source .env
```

### 4. Use the CLI client

```bash
cd client/

# 加载环境变量
source .env

# Direct HTTPS（每次调用都做 TLS + MCP 握手）
python3 mcp_client.py write_file path/to/file.txt "content here"
python3 mcp_client.py read_file path/to/file.txt
python3 mcp_client.py run_command "ls -la"
python3 mcp_client.py list_directory .
python3 mcp_client.py system_info

# Interactive shell
python3 mcp_client.py shell
```

### 5. Start the daemon（faster — keeps one MCP session alive）

```bash
cd client/
source .env

python3 mcp_daemon.py --daemonize   # 后台启动
python3 mcp_client.py write_file ... # 自动走 daemon socket
python3 mcp_daemon.py --stop        # 停止
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

复制 `nginx-mcp.conf.example` → `nginx-mcp.conf`，替换 `<your-bearer-token>` 为真实 token，然后将内容合并到你的 HTTPS server 块中。

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
