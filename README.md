English | [中文](README_zh.md)

# GaiaBridge

Multi-host remote operation and AI Agent coordination system. A central Master node manages and dispatches tasks to multiple Worker nodes over HTTPS + SSE, enabling cross-network execution without requiring inbound ports on worker machines.

## Directory Structure

```
GaiaBridge/
├── deploy.py                       # Unified interactive deploy script (menu-driven)
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
│   │   ├── file.py                 #   File read/write/list executor
│   │   └── system_info.py          #   System info executor (no shell)
│   ├── Dockerfile                  #   Container image
│   ├── docker-compose.yml          #   One-command startup
│   ├── requirements.txt            #   Python dependencies
│   └── config.toml.example         #   Configuration template
├── client/                         # Client: CLI + Daemon
│   ├── gaia_bridge_client.py        #   Command-line client
│   └── config.ini.example          #   Configuration template
├── README.md
├── README_zh.md
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
- **Dual deployment modes**: Workers support container (Docker) and host
  (native) deployment. Container mode bind-mounts a selected host directory as
  the worker workspace; host mode runs commands directly on the host system.

### Components

| Component | Role |
|---|---|
| **Master** | Node registry, SSE broker, task router, auth gateway |
| **Worker** | Lightweight daemon that connects to Master, executes tasks, reports results |
| **Client** | CLI tool or SDK to dispatch tasks to Master |

## Quick Start

### 1. Deploy

```bash
cd GaiaBridge/
python3 deploy.py
```

The unified deploy script is entirely menu-driven — no command-line arguments
required. It guides you through configuration for Master, Worker, or both.

#### Master (central control plane)

Master always deploys in container mode (Docker). The script will prompt for:

- Bind address and port
- Authentication tokens (auto-generate or enter manually)
- Mirror selection (international or China mirrors)

Configuration and persistent data are stored under `~/.gaia_bridge/master/`:

```
~/.gaia_bridge/master/
├── config.toml    # Master configuration
└── data/          # SQLite database (registry.db)
```

Master listens on `127.0.0.1:9210`. Use Nginx to expose it over HTTPS.

#### Worker (execution node)

Worker supports two deployment modes:

- **Container mode** — Docker sandbox with a selected host directory mounted as
  `/workspace`. Best for shared servers and workloads that should only access a
  bounded workspace.
- **Host mode** — runs natively as a Linux systemd user service or a Windows
  Scheduled Task, with commands executed on the host system. Best for trusted
  personal machines.

### 2. Configure Nginx

Merge the following into your HTTPS server block (see `master/nginx.conf.example`):

```nginx
location /gb/ {
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

### 3. Same-machine Master + Worker

When Master and Worker run on the same host, choose "Both" in the deploy menu.
The script deploys Master first, then Worker. Point the Worker directly at
localhost to avoid network path issues with SSE streaming:

```toml
# worker/config.toml
master_url = "http://127.0.0.1:9210"
```

### 4. Use the CLI

The `gaia` client provides short commands for common operations:

```bash
# List registered workers
python client/gaia_bridge_client.py nodes

# Run a shell command
python client/gaia_bridge_client.py run worker-1 "uname -a"

# Read a file
python client/gaia_bridge_client.py read worker-1 /etc/hostname

# List directory contents
python client/gaia_bridge_client.py ls worker-1 /tmp

# Get system info
python client/gaia_bridge_client.py info worker-1
```

Legacy command names are also supported for backward compatibility:

```bash
python client/gaia_bridge_client.py list_nodes
python client/gaia_bridge_client.py run_command --node worker-1 "uptime"
python client/gaia_bridge_client.py system_info --node worker-1
```

Alternatively, dispatch tasks directly via curl:

```bash
# Via nginx proxy (external clients):
curl -X POST https://<master-domain>/gb/api/tasks/dispatch \
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
| `master.db_path` | `MASTER_DB` | `/app/data/registry.db` | SQLite database path (container-side) |

The Master container reads `/etc/gaia_bridge/master.toml` at runtime. The
Compose file mounts the host config and data directories from
`~/.gaia_bridge/master/` into the container (paths are set via
`GAIABRIDGE_MASTER_CONFIG` and `GAIABRIDGE_MASTER_DATA` environment
variables).

### Worker (`worker/config.toml`)

| TOML key | Env override | Default | Description |
|---|---|---|---|
| `worker.mode` | `WORKER_MODE` | `container` | Deployment mode: `"host"` or `"container"` |
| `worker.node_id` | `NODE_ID` | (required) | Unique identifier for this worker |
| `worker.master_url` | `MASTER_URL` | `https://localhost:9210` | Master endpoint URL |
| `auth.node_token` | `NODE_TOKEN` | (required) | Authentication token (must match Master) |
| `worker.workspace` | `WORKSPACE_DIR` | `/workspace` | Workspace path (container: `/workspace`; host: `~/gaia_bridge_workspace`) |
| `worker.command_timeout` | `COMMAND_TIMEOUT` | `120` | Shell command timeout in seconds |
| `worker.max_output_size` | `MAX_OUTPUT_SIZE` | `200000` | Maximum result output bytes before truncation |
| `worker.reconnect_interval` | `RECONNECT_INTERVAL` | `5` | Seconds between reconnect attempts |

Config file locations (resolved in order of priority):

1. `$GAIABRIDGE_CONFIG` environment variable
2. `~/.gaia_bridge/worker/config.toml` (host mode default)
3. `/etc/gaia_bridge/worker.toml` (container mode default)
4. `worker/config.toml` (dev mode fallback)

The Worker container reads `/etc/gaia_bridge/worker.toml`; the provided Compose
file mounts the config from `~/.gaia_bridge/worker/config.toml` when deployed
through the root deploy script. In container mode, the host workspace selected
during deployment is mounted into the container at `worker.workspace`.
For example, to expose `/home/ubuntu/repo` to tasks, keep
`worker.workspace = "/workspace"` and enter `/home/ubuntu/repo` when the deploy
script asks for the host directory to mount.

Host mode installs a stable application copy under `~/.gaia_bridge/worker/app`
and runs it through `~/.gaia_bridge/worker/venv`. This keeps the deployed worker
independent from the source checkout path after deployment.

### Client (`client/config.ini`)

The client uses INI so it can run on older Python versions without installing
extra dependencies. It automatically reads `client/config.ini`, or a custom path
passed with `--config` / `GAIABRIDGE_CLIENT_CONFIG`.

| INI key | Env override | Default | Description |
|---|---|---|---|
| `client.master_url` | `MASTER_URL` | `https://<your-domain>/gb` | Master API base URL |
| `client.client_token` | `CLIENT_TOKEN` | (required) | Client bearer token |
| `client.timeout` | `CLIENT_TIMEOUT` | `120` | Synchronous task timeout in seconds |

The client intentionally has no default node. Run `nodes` and pass
`<node-id>` on every worker operation.

## Structured Error Codes

Task results include machine-readable error codes for programmatic handling:

| Code | Meaning |
|---|---|
| `node_offline` | Target worker is not connected to Master |
| `auth_denied` | Bearer token missing or does not match |
| `capability_not_found` | Worker does not support the requested task type |
| `schema_invalid` | Request body failed validation |
| `workspace_violation` | File path resolved outside the configured workspace boundary |
| `timeout` | Command or sync-wait exceeded the configured deadline |
| `output_too_large` | Result output exceeded `max_output_size`; output is empty |
| `execution_failed` | Generic execution failure (check `error` field) |
| `worker_unhealthy` | Worker reported an unhealthy state |
| `rate_limited` | Too many requests (not yet enforced) |

The `error_code` field is `null`/absent when the task succeeds. The `truncated`
boolean flag is `true` when output was capped due to size limits.

## Capability Vocabulary

Workers advertise their capabilities as compact strings. The product-facing names
are mapped to internal task types:

| Capability | Task Type | Description |
|---|---|---|
| `system.info` | `system_info` | Host OS, release, memory info |
| `file.list` | `list_dir` | List directory contents |
| `file.read` | `file_read` | Read file content |
| `file.write` | `file_write` | Write content to file |
| `shell.run` | `shell` | Execute a shell command |

Capabilities appear in the `gaia nodes` listing and are used by Agents to select
an appropriate worker for a task.

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
international defaults. To switch to Chinese mirrors, answer "yes" when the
deploy script asks about mirror selection:

```
Use China mirrors (tuna.tsinghua.edu.cn)? [Y/n]:
```

Selecting China mirrors sets:

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
- Check worker logs:
  - Container mode: `docker compose logs worker`
  - Linux host mode: `journalctl --user -u gaia-bridge-worker -f`
  - Windows host mode: `schtasks /Query /TN GaiaBridgeWorker`
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
  -t gaia-bridge-master -f master/Dockerfile .
cd master/ && docker compose up -d
# Repeat for worker/
```

## License

GaiaBridge uses an open-core licensing model:

- `client/`, `worker/`, `shared/`, `doc/`, deployment tooling, and root-level
  project files are licensed under Apache-2.0.
- `master/` is the Community Master and is licensed under AGPL-3.0-only.
- Commercial Master management, hosted service, billing, tenant
  administration, regional relay, enterprise policy, and related cloud
  features may be developed separately under proprietary commercial terms.

See [LICENSE](LICENSE) for the full repository license notice.
