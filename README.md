# WorkBridge

Multi-host remote operation and AI Agent coordination system. A central Master node manages and dispatches tasks to multiple Worker nodes over HTTPS + SSE, enabling cross-network execution without requiring inbound ports on worker machines.

## Directory Structure

```
WorkBridge/
├── shared/                         # Shared protocol and utilities
│   ├── protocol.py                 #   Pydantic models (Node, Task, SSEEvent, enums)
│   ├── auth.py                     #   Token generation and verification
│   └── config.py                   #   MasterConfig / WorkerConfig schemas
├── master/                         # Master: central control plane
│   ├── app.py                      #   Starlette application entry point
│   ├── registry.py                 #   Node registry (SQLite)
│   ├── broker.py                   #   SSE connection pool manager
│   ├── router.py                   #   Task dispatch and Future matching
│   ├── auth.py                     #   Bearer token middleware
│   ├── api/
│   │   ├── nodes.py                #   Node register/heartbeat/list/SSE
│   │   └── tasks.py                #   Task dispatch/result endpoints
│   ├── Dockerfile                  #   Container image
│   ├── docker-compose.yml          #   One-command startup
│   ├── requirements.txt            #   Python dependencies
│   └── config.toml.example         #   Configuration template
├── worker/                         # Worker: execution plane
│   ├── daemon.py                   #   Main process (register + SSE listen + reconnect)
│   ├── reporter.py                 #   Result reporter (POST back to Master)
│   ├── executor/
│   │   ├── base.py                 #   Abstract executor interface
│   │   ├── shell.py                #   Shell command executor
│   │   └── file.py                 #   File read/write/list executor
│   ├── Dockerfile                  #   Container image
│   ├── docker-compose.yml          #   One-command startup
│   ├── requirements.txt            #   Python dependencies
│   └── config.toml.example         #   Configuration template
├── client/                         # Client: CLI + Daemon
│   ├── mcp_client.py               #   Command-line client
│   ├── mcp_daemon.py               #   Persistent MCP session daemon
│   ├── test_nginx.py               #   End-to-end test script
│   └── config.ini.example          #   Configuration template
├── README.md
├── agent.md
└── .gitignore
```

## Architecture

```
[Client / Agent]
    | (HTTPS POST: dispatch tasks)
    v
[Master (public IP) -- central router]
    ^ (HTTPS POST: report results)
    | (SSE long-poll: push task instructions)
    |
    +-- [Worker @ Node A]
    +-- [Worker @ Node B]
    +-- [Worker @ Node C]
    ...
```

### Design Constraints

- **All-outbound connections**: Workers only need outbound HTTPS. No inbound ports required.
- **Central routing hub**: All inter-node communication routes through Master.
- **Capability/intelligence split**: Workers provide execution; Agents provide LLM decisions.
- **Container sandbox**: All nodes run in Docker with restricted filesystem access.

### Components

| Component | Role |
|---|---|
| **Master** | Node registry, SSE broker, task router, auth gateway |
| **Worker** | Lightweight daemon that connects to Master, executes tasks, reports results |
| **Client** | CLI tool or SDK to dispatch tasks to Master |

## Quick Start

### 1. Deploy Master (on public IP server)

```bash
cd master/
cp config.toml.example config.toml
# Edit config.toml: set auth.node_token and auth.client_token
# Generate tokens with: python3 -c "import secrets; print(secrets.token_hex(32))"

# Default deployment
./deploy.sh

# China mirrors for apt/pip
./deploy.sh --cn
```

Master listens on `127.0.0.1:9210`. Use Nginx to expose it over HTTPS.

### 2. Configure Nginx

Merge the following into your HTTPS server block (see `master/nginx.conf.example`):

```nginx
location /wb/ {
    proxy_pass http://127.0.0.1:9210/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # SSE requires disabled buffering
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

Then reload: `sudo nginx -t && sudo systemctl reload nginx`

### 3. Deploy Worker (on any node)

```bash
cd worker/
cp config.toml.example config.toml
# Edit config.toml: set worker.node_id, worker.master_url, and auth.node_token
# Use the SAME node_token from Master config
# Set deployment.host_workspace to the absolute host path this worker may operate in

# Default deployment
./deploy.sh

# China mirrors for apt/pip
./deploy.sh --cn
```

The worker connects outbound to Master and waits for tasks.

By default, tasks run inside the container under `/workspace`. The helper script
reads `deployment.host_workspace` from `config.toml`, mounts that host path to
`worker.workspace`, and starts the service:

```bash
./deploy.sh
```

If you run Docker Compose directly, set `WORKBRIDGE_HOST_WORKSPACE` to the host
path and keep `WORKBRIDGE_CONTAINER_WORKSPACE` aligned with `worker.workspace`:

```bash
DOCKER_BUILDKIT=0 \
WORKBRIDGE_HOST_WORKSPACE=/home/ubuntu/repo \
WORKBRIDGE_CONTAINER_WORKSPACE=/workspace \
docker compose up -d
```

### 4. Same-machine Master + Worker

When Master and Worker run on the same host, point the Worker directly
at localhost to avoid network path issues with SSE streaming:

```toml
# worker/config.toml
master_url = "http://127.0.0.1:9210"
```

### 5. Dispatch a task

```bash
# Via nginx proxy (external clients):
curl -X POST https://<master-domain>/wb/api/tasks/dispatch \
  -H "Authorization: Bearer <client-token>" \
  -H "Content-Type: application/json" \
  -d '{"target_node": "worker-1", "payload": {"task_type": "shell", "params": {"command": "uname -a"}}}'

# Or direct to Master port (local):
curl -X POST http://127.0.0.1:9210/api/tasks/dispatch \
  -H "Authorization: Bearer <client-token>" \
  -H "Content-Type: application/json" \
  -d '{"target_node": "worker-1", "payload": {"task_type": "shell", "params": {"command": "uname -a"}}}'
```

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/nodes/register` | Node Token | Register a worker node |
| POST | `/api/nodes/heartbeat` | Node Token | Update node heartbeat |
| GET | `/api/nodes` | - | List all registered nodes |
| GET | `/api/events?node_id=X` | Node Token | SSE event stream for a worker |
| POST | `/api/tasks/dispatch` | Client Token | Dispatch task (async) |
| POST | `/api/tasks/dispatch_sync` | Client Token | Dispatch and wait for result |
| POST | `/api/tasks/result` | Node Token | Worker reports task result |
| GET | `/api/tasks/{task_id}` | - | Get task result |
| GET | `/health` | - | Health check |

## Configuration

Configuration is loaded from local files by default. Environment variables are
still supported as an override layer for container orchestration and secret
injection.

Load order:

```text
environment variables > configuration file > defaults
```

### Master (`master/config.toml`)

| TOML key | Env override | Default | Description |
|---|---|---|---|
| `master.host` | `MASTER_HOST` | `0.0.0.0` | Bind address |
| `master.port` | `MASTER_PORT` | `9210` | Listen port |
| `auth.node_token` | `NODE_TOKEN` | (required) | Token for worker authentication |
| `auth.client_token` | `CLIENT_TOKEN` | (required) | Token for client/agent authentication |
| `master.heartbeat_timeout` | `HEARTBEAT_TIMEOUT` | `60` | Seconds before marking node offline |
| `master.db_path` | `MASTER_DB` | `/app/data/registry.db` | SQLite database path |

The Master container reads `/etc/workbridge/master.toml`; the provided Compose
file mounts `master/config.toml` there automatically.

### Worker (`worker/config.toml`)

| TOML key | Env override | Default | Description |
|---|---|---|---|
| `worker.node_id` | `NODE_ID` | (required) | Unique identifier for this worker |
| `worker.master_url` | `MASTER_URL` | `https://localhost:9210` | Master endpoint URL |
| `auth.node_token` | `NODE_TOKEN` | (required) | Authentication token (must match Master) |
| `worker.workspace` | `WORKSPACE_DIR` | `/workspace` | Container workspace path used by task executors |
| `worker.command_timeout` | `COMMAND_TIMEOUT` | `120` | Shell command timeout in seconds |
| `worker.reconnect_interval` | `RECONNECT_INTERVAL` | `5` | Seconds between reconnect attempts |
| `deployment.host_workspace` | - | (required by `worker/deploy.sh`) | Host path mounted into `worker.workspace` |

The Worker container reads `/etc/workbridge/worker.toml`; the provided Compose
file mounts `worker/config.toml` there automatically. When using
`worker/deploy.sh`, `deployment.host_workspace` is injected into Docker Compose
as `WORKBRIDGE_HOST_WORKSPACE` and mounted at `worker.workspace`.

### Client (`client/config.ini`)

The client uses INI so it can run on older Python versions without installing
extra dependencies. It automatically reads `client/config.ini`, or a custom path
passed with `--config` / `WORKBRIDGE_CLIENT_CONFIG`.

| INI key | Env override | Default | Description |
|---|---|---|---|
| `client.mcp_url` | `MCP_URL` | `https://<your-domain>/_mcp` | MCP server endpoint |
| `client.auth_token` | `AUTH_TOKEN` | (required) | Bearer token |
| `client.socket_path` | `MCP_SOCKET_PATH` | `/tmp/mcp-daemon.sock` | Daemon Unix socket path |
| `client.pid_file` | `MCP_PID_FILE` | `/tmp/mcp-daemon.pid` | Daemon PID file path |

## Build System

### Docker build requirements

Two flags are REQUIRED to build on machines where Docker's default bridge
network has no DNS resolution (common on cloud VMs):

| Flag | Why |
|---|---|
| `DOCKER_BUILDKIT=0` | BuildKit's `--network=host` does not work reliably; the legacy builder passes host networking through to intermediate containers |
| `--network=host` | Lets the build container use the host's network stack so `apt-get` and `pip` can reach external repos |

### ARG scoping (Dockerfile)

ARGs declared *before* `FROM` are only visible in the `FROM` instruction.
To use them in `RUN` steps, re-declare them after `FROM` (without default values):

```dockerfile
ARG APT_MIRROR=deb.debian.org
FROM ${PYTHON_IMAGE}
ARG APT_MIRROR          # re-declare to bring into scope
RUN sed -i "s|http://deb.debian.org|http://${APT_MIRROR}|g" ...
```

### Sudo and environment variables

`sudo` strips most environment variables by default. When running `docker
compose build` with `sudo`, env vars like `APT_MIRROR` never reach the
docker-compose process. Either:

- Pass them explicitly: `sudo -E env APT_MIRROR=... docker compose build`
- Or build directly with `docker build` and pass `--build-arg`

### Mirror configuration

| Build arg | Default (international) | China example |
|---|---|---|
| `PYTHON_IMAGE` | `python:3.12-slim` | (keep default, Docker Hub works) |
| `APT_MIRROR` | `deb.debian.org` | `mirrors.tuna.tsinghua.edu.cn` |
| `PIP_INDEX_URL` | `https://pypi.org/simple` | `https://pypi.tuna.tsinghua.edu.cn/simple` |

The docker-compose files read these from environment variables with
international defaults. To switch to Chinese mirrors, run either deploy script
with `--cn`:

```bash
./deploy.sh --cn
```

That option sets:

```bash
DOCKER_BUILDKIT=0
APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

You can still override any of those values explicitly before invoking the
script, or pass them as `--build-arg` to `docker build`.

## Security

- **Dual token scheme**: Node Token (worker identity) and Client Token (dispatch authority) are separate
- **All-outbound networking**: Workers never expose inbound ports
- **Path traversal blocked**: All file operations enforce workspace boundary via realpath validation
- **Container isolation**: Both Master and Worker run as non-root in Docker containers
- **Command timeout**: Long-running commands are killed automatically
- **No hardcoded secrets**: Tokens are loaded from local config files or environment overrides
- **Local-only Master port**: Master binds to 127.0.0.1, exposed only via Nginx reverse proxy

## Troubleshooting

### Build fails with "Undetermined Error" (apt-get)

The build container cannot reach the Debian repositories. Three fixes:

1. Use `DOCKER_BUILDKIT=0 docker build --network=host` (legacy builder + host network)
2. Use a mirror closer to your server via `--build-arg APT_MIRROR=...`
3. Check that the `APTMIRROR` build arg is **re-declared after `FROM`** in the Dockerfile (ARG scoping rule)

### Build fails with "deb.debian.org" in logs even though mirror is set

The `--build-arg` value is not reaching the `RUN` instruction. Most likely
the ARG is declared before `FROM` but not re-declared inside the stage.
See "ARG scoping" in the Build System section above.

### Worker cannot connect to Master

- Verify Master is reachable: `curl <MASTER_URL>/health`
- Check `NODE_TOKEN` matches the Master configuration
- Ensure outbound HTTPS is not blocked by firewall

### Task dispatched but no result / Worker shows no "executing task" log

- Check if the target worker is online: `GET /api/nodes`
- Verify the worker SSE connection is active (Master logs show "broker: node X connected")
- Check worker logs: `docker compose logs worker`
- **SSE line-ending mismatch**: `sse-starlette` sends events separated by
  `\r\n\r\n` (CRLF, per the SSE spec). If the worker splits the stream by
  `\n\n` (LF only), events will never be parsed. The daemon must use
  `\r\n\r\n` as the event delimiter, or normalize line endings first.
- **Same-machine worker**: prefer `master_url = "http://127.0.0.1:9210"`
  to avoid SSE streaming issues through the public IP / NAT path.
- **Blocking HTTP client**: `urllib.request.urlopen().read()` may hang
  indefinitely on SSE streams served by uvicorn. Use an async HTTP
  client (`httpx`, `aiohttp`) with streaming support instead.

### Rebuild after code changes

```bash
cd <project-root>
DOCKER_BUILDKIT=0 docker build --no-cache --network=host \
  --build-arg APT_MIRROR=mirrors.tuna.tsinghua.edu.cn \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t workbridge-master -f master/Dockerfile .
cd master/ && docker compose up -d
# Repeat for worker/
```
