# GaiaBridge — Deployment Guide

## Prerequisites

- Docker and Docker Compose installed on the Master host
- Python 3.x available on any Worker host running in host mode
- Outbound HTTPS access from all Worker hosts to the Master

## Deploy Script

```bash
cd GaiaBridge/
python3 deploy.py
```

The unified deploy script is entirely menu-driven — no command-line arguments required. It guides you through configuration for Master, Worker, or both.

### Master (central control plane)

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

### Worker (execution node)

Worker supports two deployment modes:

- **Container mode** — Docker sandbox with a selected host directory mounted as `/workspace`. Best for shared servers and workloads that should only access a bounded workspace.
- **Host mode** — runs natively as a Linux systemd user service or a Windows Scheduled Task, with commands executed on the host system. Best for trusted personal machines.

### Same-machine Master + Worker

When Master and Worker run on the same host, choose "Both" in the deploy menu. The script deploys Master first, then Worker. Point the Worker directly at localhost to avoid network path issues with SSE streaming:

```toml
# worker/config.toml
master_url = "http://127.0.0.1:9210"
```

## Configure Nginx

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

## Security

- **Dual token scheme**: Node Token (worker identity) and Client Token (dispatch authority) are separate
- **All-outbound networking**: Workers never expose inbound ports
- **Path traversal blocked**: All file operations enforce workspace boundary via realpath validation
- **Container isolation**: Both Master and Worker run as non-root in Docker containers
- **Command timeout**: Long-running commands are killed automatically
- **No hardcoded secrets**: Tokens are loaded from local config files or environment overrides
- **Local-only Master port**: Master binds to 127.0.0.1, exposed only via Nginx reverse proxy

## Build System

### Docker build requirements

Two flags are REQUIRED to build on machines where Docker's default bridge network has no DNS resolution (common on cloud VMs):

| Flag | Why |
|---|---|
| `DOCKER_BUILDKIT=0` | BuildKit's `--network=host` does not work reliably; the legacy builder passes host networking through to intermediate containers |
| `--network=host` | Lets the build container use the host's network stack so `apt-get` and `pip` can reach external repos |

### ARG scoping (Dockerfile)

ARGs declared *before* `FROM` are only visible in the `FROM` instruction. To use them in `RUN` steps, re-declare them after `FROM` (without default values):

```dockerfile
ARG APT_MIRROR=deb.debian.org
FROM ${PYTHON_IMAGE}
ARG APT_MIRROR          # re-declare to bring into scope
RUN sed -i "s|http://deb.debian.org|http://${APT_MIRROR}|g" ...
```

### Sudo and environment variables

`sudo` strips most environment variables by default. When running `docker compose build` with `sudo`, env vars like `APT_MIRROR` never reach the docker-compose process. Either:

- Pass them explicitly: `sudo -E env APT_MIRROR=... docker compose build`
- Or build directly with `docker build` and pass `--build-arg`

### Mirror configuration

| Build arg | Default (international) | China example |
|---|---|---|
| `PYTHON_IMAGE` | `python:3.12-slim` | (keep default, Docker Hub works) |
| `APT_MIRROR` | `deb.debian.org` | `mirrors.tuna.tsinghua.edu.cn` |
| `PIP_INDEX_URL` | `https://pypi.org/simple` | `https://pypi.tuna.tsinghua.edu.cn/simple` |

The docker-compose files read these from environment variables with international defaults. To switch to China mirrors, answer "yes" when the deploy script asks:

```
Use China mirrors (tuna.tsinghua.edu.cn)? [Y/n]:
```

Selecting China mirrors sets:

```bash
DOCKER_BUILDKIT=0
APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

You can still override any of those values explicitly before invoking the script, or pass them as `--build-arg` to `docker build`.

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

## Troubleshooting

### Build fails with "Undetermined Error" (apt-get)

The build container cannot reach the Debian repositories. Three fixes:

1. Use `DOCKER_BUILDKIT=0 docker build --network=host` (legacy builder + host network)
2. Use a mirror closer to your server via `--build-arg APT_MIRROR=...`
3. Check that the `APT_MIRROR` build arg is **re-declared after `FROM`** in the Dockerfile (ARG scoping rule)

### Build fails with "deb.debian.org" in logs even though mirror is set

The `--build-arg` value is not reaching the `RUN` instruction. Most likely the ARG is declared before `FROM` but not re-declared inside the stage. See "ARG scoping" in the Build System section above.

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
- **SSE line-ending mismatch**: `sse-starlette` sends events separated by `\r\n\r\n` (CRLF, per the SSE spec). If the worker splits the stream by `\n\n` (LF only), events will never be parsed. The daemon must use `\r\n\r\n` as the event delimiter, or normalize line endings first.
- **Same-machine worker**: prefer `master_url = "http://127.0.0.1:9210"` to avoid SSE streaming issues through the public IP / NAT path.
- **Blocking HTTP client**: `urllib.request.urlopen().read()` may hang indefinitely on SSE streams served by uvicorn. Use an async HTTP client (`httpx`, `aiohttp`) with streaming support instead.
