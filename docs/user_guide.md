# GaiaBridge — User Guide

## Configuration

Configuration is loaded from local files by default. Environment variables are supported as an override layer for container orchestration and secret injection.

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

The Master container reads `/etc/gaia_bridge/master.toml` at runtime. The Compose file mounts the host config and data directories from `~/.gaia_bridge/master/` into the container (paths are set via `GAIABRIDGE_MASTER_CONFIG` and `GAIABRIDGE_MASTER_DATA` environment variables).

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

The Worker container reads `/etc/gaia_bridge/worker.toml`; the provided Compose file mounts the config from `~/.gaia_bridge/worker/config.toml` when deployed through the root deploy script. In container mode, the host workspace selected during deployment is mounted into the container at `worker.workspace`. For example, to expose `/home/ubuntu/repo` to tasks, keep `worker.workspace = "/workspace"` and enter `/home/ubuntu/repo` when the deploy script asks for the host directory to mount.

Host mode installs a stable application copy under `~/.gaia_bridge/worker/app` and runs it through `~/.gaia_bridge/worker/venv`. This keeps the deployed worker independent from the source checkout path after deployment.

### Client (`client/config.ini`)

The client uses INI so it can run on older Python versions without installing extra dependencies. It automatically reads `client/config.ini`, or a custom path passed with `--config` / `GAIABRIDGE_CLIENT_CONFIG`.

| INI key | Env override | Default | Description |
|---|---|---|---|
| `client.master_url` | `MASTER_URL` | `https://<your-domain>/gb` | Master API base URL |
| `client.client_token` | `CLIENT_TOKEN` | (required) | Client bearer token |
| `client.timeout` | `CLIENT_TIMEOUT` | `120` | Synchronous task timeout in seconds |

The client intentionally has no default node. Run `nodes` and pass `<node-id>` on every worker operation.

## CLI Usage

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

## Direct API Usage

Tasks can also be dispatched directly via curl:

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

The `error_code` field is `null`/absent when the task succeeds. The `truncated` boolean flag is `true` when output was capped due to size limits.

## Capability Vocabulary

Workers advertise their capabilities as compact strings. The product-facing names are mapped to internal task types:

| Capability | Task Type | Description |
|---|---|---|
| `system.info` | `system_info` | Host OS, release, memory info |
| `file.list` | `list_dir` | List directory contents |
| `file.read` | `file_read` | Read file content |
| `file.write` | `file_write` | Write content to file |
| `shell.run` | `shell` | Execute a shell command |

Capabilities appear in the `gaia nodes` listing and are used by Agents to select an appropriate worker for a task.
