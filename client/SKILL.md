# WorkBridge Client — Agent Usage Guide

Use this client to dispatch tasks to a configured WorkBridge worker through the Master API.

## Setup

Create `client/config.ini` from the example and fill:

- `master_url` — the Master HTTPS base URL, for example `https://example.com/wb`
- `client_token` — the client bearer token from Master config

Always choose an explicit target node for operations. Use `list_nodes` first.

## Commands

```bash
python3 client/workbridge_client.py list_nodes
python3 client/workbridge_client.py system_info --node tappat_home_ubuntu
python3 client/workbridge_client.py list_directory --node tappat_home_ubuntu .
python3 client/workbridge_client.py read_file --node tappat_home_ubuntu README.md
python3 client/workbridge_client.py write_file --node tappat_home_ubuntu tmp/hello.txt "hello"
python3 client/workbridge_client.py run_command --node tappat_home_ubuntu "pwd && ls -la"
```

## Path Rules

Paths are resolved relative to the worker workspace, normally `/workspace` inside the container.

| You send | Resolves to |
|---|---|
| `project/main.py` | `/workspace/project/main.py` |
| `/workspace/project/main.py` | `/workspace/project/main.py` |
| `../etc/passwd` | denied |

## Practices

1. Run `list_nodes` first and pick an explicit online node.
2. Use `list_directory` and `read_file` before writing.
3. Check command exit codes in `run_command` output.
4. Avoid interactive or long-running commands.
5. Prefer workspace-relative paths.
