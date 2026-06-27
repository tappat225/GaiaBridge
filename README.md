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
│   └── .env.example                #   Environment variable template
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
│   └── .env.example                #   Environment variable template
├── client/                         # Client: CLI + Daemon
│   ├── mcp_client.py               #   Command-line client
│   ├── mcp_daemon.py               #   Persistent MCP session daemon
│   ├── test_nginx.py               #   End-to-end test script
│   └── .env.example                #   Environment variable template
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
cp .env.example .env
# Edit .env: set NODE_TOKEN and CLIENT_TOKEN

docker compose up -d --build
```

Master listens on `127.0.0.1:9210`. Use Nginx to expose it over HTTPS.

### 2. Deploy Worker (on any node)

```bash
cd worker/
cp .env.example .env
# Edit .env: set NODE_ID, MASTER_URL, NODE_TOKEN, WORKSPACE_DIR

docker compose up -d --build
```

The worker connects outbound to Master and waits for tasks.

### 3. Dispatch a task

```bash
curl -X POST https://<master-domain>:9210/api/tasks/dispatch_sync \
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

### Master (`master/.env`)

| Env var | Default | Description |
|---|---|---|
| `MASTER_HOST` | `0.0.0.0` | Bind address |
| `MASTER_PORT` | `9210` | Listen port |
| `NODE_TOKEN` | (required) | Token for worker authentication |
| `CLIENT_TOKEN` | (required) | Token for client/agent authentication |
| `HEARTBEAT_TIMEOUT` | `60` | Seconds before marking node offline |
| `MASTER_DB` | `/app/data/registry.db` | SQLite database path |

### Worker (`worker/.env`)

| Env var | Default | Description |
|---|---|---|
| `NODE_ID` | (required) | Unique identifier for this worker |
| `MASTER_URL` | (required) | Master endpoint URL |
| `NODE_TOKEN` | (required) | Authentication token (must match Master) |
| `WORKSPACE_DIR` | `/home/ubuntu/repo` | Host directory to mount as workspace |
| `COMMAND_TIMEOUT` | `120` | Shell command timeout in seconds |
| `RECONNECT_INTERVAL` | `5` | Seconds between reconnect attempts |

### Client (`client/.env`)

| Env var | Default | Description |
|---|---|---|
| `MCP_URL` | `https://<your-domain>/_mcp` | MCP server endpoint |
| `AUTH_TOKEN` | (required) | Bearer token |
| `MCP_SOCKET_PATH` | `/tmp/mcp-daemon.sock` | Daemon Unix socket path |
| `MCP_PID_FILE` | `/tmp/mcp-daemon.pid` | Daemon PID file path |

## Security

- **Dual token scheme**: Node Token (worker identity) and Client Token (dispatch authority) are separate
- **All-outbound networking**: Workers never expose inbound ports
- **Path traversal blocked**: All file operations enforce workspace boundary via realpath validation
- **Container isolation**: Both Master and Worker run as non-root in Docker containers
- **Command timeout**: Long-running commands are killed automatically
- **No hardcoded secrets**: All tokens loaded from environment variables
- **Local-only Master port**: Master binds to 127.0.0.1, exposed only via Nginx reverse proxy

## Troubleshooting

### Worker cannot connect to Master

- Verify Master is reachable: `curl <MASTER_URL>/health`
- Check `NODE_TOKEN` matches the Master configuration
- Ensure outbound HTTPS is not blocked by firewall

### Task dispatched but no result

- Check if the target worker is online: `GET /api/nodes`
- Verify the worker SSE connection is active (Master logs show "broker: node X connected")
- Check worker logs: `docker compose logs worker`

### Rebuild after code changes

```bash
cd master/  # or worker/
docker compose up -d --build
```
