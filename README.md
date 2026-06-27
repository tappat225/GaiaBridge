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
│   └── api/
│       ├── nodes.py                #   Node register/heartbeat/list/SSE
│       └── tasks.py                #   Task dispatch/result endpoints
├── worker/                         # Worker: execution plane
│   ├── daemon.py                   #   Main process (register + SSE listen + reconnect)
│   ├── reporter.py                 #   Result reporter (POST back to Master)
│   └── executor/
│       ├── base.py                 #   Abstract executor interface
│       ├── shell.py                #   Shell command executor
│       └── file.py                 #   File read/write/list executor
├── server/                         # Legacy: single-node MCP Server (Docker)
│   ├── server.py                   #   FastMCP application
│   ├── Dockerfile                  #   Container image
│   ├── docker-compose.yml          #   One-command startup
│   ├── requirements.txt            #   Python dependencies
│   ├── nginx-mcp.conf.example      #   Nginx config template
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
- **Capability/intelligence split**: Workers provide execution ("hands"); Agents provide LLM decision-making ("brain").
- **Container sandbox**: All execution nodes run in restricted containers with mounted workdirs only.

### Components

| Component | Role |
|---|---|
| **Master** | Node registry, SSE broker, task router, auth gateway |
| **Worker** | Lightweight daemon that connects to Master, executes tasks, reports results |
| **Client** | CLI tool or SDK to dispatch tasks to Master |
| **Server (legacy)** | Single-node MCP server for direct AI agent access |

## Communication Model

- **Worker -> Master**: Persistent SSE connection () for receiving task pushes
- **Worker -> Master**: HTTPS POST to report execution results
- **Client -> Master**: HTTPS API for task dispatch and status queries
- **Heartbeat**: Master sends SSE pings every 30s; sweeps stale nodes based on configurable timeout

## API Endpoints (Master)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST |  | Node Token | Register a worker node |
| POST |  | Node Token | Update node heartbeat |
| GET |  | - | List all registered nodes |
| GET |  | Node Token | SSE event stream for a worker |
| POST |  | Client Token | Dispatch task (async) |
| POST |  | Client Token | Dispatch and wait for result |
| POST |  | Node Token | Worker reports task result |
| GET |  | - | Get task result |
| GET |  | - | Health check |

## Quick Start

### Legacy single-node mode (MCP Server)

See  directory. Start with:

```bash
cd server/
docker compose up -d --build
```

### Distributed mode (Master + Workers)

#### 1. Start Master

```bash
export MASTER_HOST=0.0.0.0
export MASTER_PORT=8100
export NODE_TOKEN=<your-node-token>
export CLIENT_TOKEN=<your-client-token>
export MASTER_DB=registry.db
export HEARTBEAT_TIMEOUT=60

cd WorkBridge
python3 -m master.app
```

#### 2. Start Worker (on any node)

```bash
export NODE_ID=worker-1
export MASTER_URL=https://<master-domain>:8100
export NODE_TOKEN=<your-node-token>
export WORKSPACE_DIR=/workspace
export COMMAND_TIMEOUT=120

cd WorkBridge
python3 -m worker.daemon
```

#### 3. Dispatch a task (from Client)

```bash
curl -X POST https://<master-domain>:8100/api/tasks/dispatch_sync   -H "Authorization: Bearer <client-token>"   -H "Content-Type: application/json"   -d '{"target_node": "worker-1", "payload": {"task_type": "shell", "params": {"command": "uname -a"}}}'
```

## Configuration

### Master

| Env var | Default | Description |
|---|---|---|
|  |  | Bind address |
|  |  | Listen port |
|  | (required) | Token for worker authentication |
|  | (required) | Token for client/agent authentication |
|  |  | Seconds before marking node offline |
|  |  | SQLite database path |

### Worker

| Env var | Default | Description |
|---|---|---|
|  | (required) | Unique identifier for this worker |
|  | (required) | Master endpoint URL |
|  | (required) | Authentication token |
|  |  | Root directory for file operations |
|  |  | Shell command timeout in seconds |
|  |  | Seconds between reconnect attempts |

### Legacy MCP Client ()

| Env var | Default | Description |
|---|---|---|
|  |  | MCP server endpoint |
|  | (required) | Bearer token |
|  |  | Daemon Unix socket path |
|  |  | Daemon PID file path |

## Security

- **Dual token scheme**: Node Token (worker identity) and Client Token (dispatch authority) are separate
- **All-outbound networking**: Workers never expose inbound ports
- **Path traversal blocked**: All file operations enforce workspace boundary via realpath validation
- **Container isolation**: Workers run as non-root in containers with only workspace mounted
- **Command timeout**: Long-running commands are killed automatically
- **No hardcoded secrets**: All tokens loaded from environment variables

## Troubleshooting

### Worker cannot connect to Master

- Verify  is reachable: 
- Check  matches the Master configuration
- Ensure outbound HTTPS is not blocked by firewall

### Task dispatched but no result

- Check if the target worker is online: 
- Verify the worker's SSE connection is active (Master logs show "broker: node X connected")
- Check worker logs for execution errors

### Legacy MCP client issues

- Daemon timeout: client now auto-falls back to direct mode on daemon failure
- Source  before starting daemon: 
