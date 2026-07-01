English | [中文](README_zh.md)

# GaiaBridge

Multi-host remote operation and AI Agent coordination system. A central Master node manages and dispatches tasks to multiple Worker nodes over HTTPS + SSE, enabling cross-network execution without requiring inbound ports on worker machines.

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
- **Dual deployment modes**: Workers support container (Docker) and host (native) deployment. Container mode bind-mounts a selected host directory as the worker workspace; host mode runs commands directly on the host system.

### Components

| Component | Role |
|---|---|
| **Master** | Node registry, SSE broker, task router, auth gateway |
| **Worker** | Lightweight daemon that connects to Master, executes tasks, reports results |
| **Client** | CLI tool or SDK to dispatch tasks to Master |

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
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── config.toml.example
├── worker/                         # Worker: execution plane
│   ├── daemon.py                   #   Main process (register + SSE listen + reconnect)
│   ├── reporter.py                 #   Result reporter (POST back to Master)
│   ├── executor/
│   │   ├── base.py                 #   Abstract executor interface
│   │   ├── shell.py                #   Shell command executor
│   │   ├── file.py                 #   File read/write/list executor
│   │   └── system_info.py          #   System info executor (no shell)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── config.toml.example
├── client/                         # Client: CLI + Daemon
│   ├── gaia_bridge_client.py
│   └── config.ini.example
├── docs/
│   ├── deploy.md                   # Deployment guide
│   └── user_guide.md               # User guide
├── README.md
├── README_zh.md
├── agent.md
└── .gitignore
```

## Quick Deploy

```bash
cd GaiaBridge/
python3 deploy.py
```

The deploy script is entirely menu-driven. It guides you through Master, Worker, or both. See [docs/deploy.md](docs/deploy.md) for the full deployment guide including Nginx setup, build flags, mirror configuration, and troubleshooting.

## Quick Use

```bash
# List registered workers
python client/gaia_bridge_client.py nodes

# Run a shell command on a worker
python client/gaia_bridge_client.py run worker-1 "uname -a"
```

See [docs/user_guide.md](docs/user_guide.md) for the full user guide including configuration reference, all CLI commands, direct API usage, error codes, and capability vocabulary.

## Contributing

Contributions are welcome. Please open an issue or pull request on GitHub.

## License

GaiaBridge uses an open-core licensing model:

- `client/`, `worker/`, `shared/`, `docs/`, deployment tooling, and root-level project files are licensed under Apache-2.0.
- `master/` is the Community Master and is licensed under AGPL-3.0-only.
- Commercial Master management, hosted service, billing, tenant administration, regional relay, enterprise policy, and related cloud features will be developed separately under proprietary commercial terms.

See [LICENSE](LICENSE) for the full repository license notice.
