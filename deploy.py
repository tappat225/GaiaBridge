#!/usr/bin/env python3
"""GaiaBridge unified interactive deployment script.

Zero CLI arguments. Entirely menu-driven.

Usage:
    python3 deploy.py
"""

import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import pwd
    _HAS_PWD = True
except ImportError:
    _HAS_PWD = False

SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR_NAMES = ("shared", "worker")
WORKER_SERVICE_NAME = "gaia-bridge-worker"
WORKER_WINDOWS_TASK_NAME = "GaiaBridgeWorker"
MASTER_CONTAINER_NAME = "gaia-bridge-master"
WORKER_CONTAINER_NAME = "gaia-bridge-worker"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    """Ask a question with an optional default value."""
    if default:
        value = input(f"{prompt} [{default}]: ").strip()
        return value if value else default
    while True:
        value = input(f"{prompt}: ").strip()
        if value:
            return value


def _ask_yn(prompt: str, default_yes: bool = True) -> bool:
    """Ask a yes/no question."""
    hint = "Y/n" if default_yes else "y/N"
    answer = input(f"{prompt} [{hint}]: ").strip().lower()
    if not answer:
        return default_yes
    return answer in ("y", "yes")


def _ask_choice(prompt: str, options: list[str]) -> int:
    """Ask a numbered multiple-choice question. Returns 0-based index."""
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        try:
            choice = int(input(f"Choice [1-{len(options)}]: ").strip())
            if 1 <= choice <= len(options):
                return choice - 1
        except ValueError:
            pass
        print(f"Please enter a number between 1 and {len(options)}.")


def _get_user_home() -> Path:
    """Return the real user's home directory, even when running under sudo.

    When deploy.py is invoked with ``sudo``, ``Path.home()`` resolves to
    ``/root`` because the effective user is root.  This helper checks the
    ``SUDO_USER`` environment variable and, when present, returns the
    original user's home directory instead.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and _HAS_PWD:
        return Path(pwd.getpwnam(sudo_user).pw_dir)
    return Path.home()


def _generate_token() -> str:
    """Generate a cryptographically random hex token."""
    return secrets.token_hex(32)


def _write_toml(path: Path, sections: dict[str, dict[str, str]]) -> None:
    """Write a simple TOML file from nested dicts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for section, kvs in sections.items():
            f.write(f"[{section}]\n")
            for k, v in kvs.items():
                if isinstance(v, str):
                    f.write(f'{k} = "{v}"\n')
                elif isinstance(v, bool):
                    f.write(f"{k} = {str(v).lower()}\n")
                else:
                    f.write(f"{k} = {v}\n")
            f.write("\n")


def _docker_compose_up(component_dir: Path, env: dict[str, str]) -> int:
    """Run docker compose up -d --build in the given component directory."""
    os.chdir(component_dir)
    cmd = ["docker", "compose", "up", "-d", "--build"]
    result = subprocess.run(cmd, env=env)
    return result.returncode


def _detect_docker() -> bool:
    """Check if Docker is available."""
    return shutil.which("docker") is not None


def _venv_bin(venv_dir: Path, executable: str) -> Path:
    """Return a virtualenv executable path for the current platform."""
    if sys.platform == "win32":
        suffix = ".exe" if executable in ("python", "pip") else ""
        return venv_dir / "Scripts" / f"{executable}{suffix}"
    return venv_dir / "bin" / executable


def _sync_worker_app(app_dir: Path) -> None:
    """Install a runnable copy of worker code under the user data directory."""
    if app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True, exist_ok=True)

    for name in APP_DIR_NAMES:
        shutil.copytree(
            SCRIPT_DIR / name,
            app_dir / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "config.toml"),
        )

    shutil.copy2(SCRIPT_DIR / "worker" / "requirements.txt", app_dir / "requirements.txt")


def _run_checked(cmd: list[str], **kwargs) -> None:
    """Run a command and raise on failure."""
    subprocess.run(cmd, check=True, **kwargs)


def _command_ok(cmd: list[str]) -> bool:
    """Return True when a command exits successfully."""
    return subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def _python_needs_tomli(python_exe: str | None = None) -> bool:
    """Return True when the Python interpreter is older than 3.11.

    Python 3.11 added ``tomllib`` to the standard library.  Older versions
    need the third-party ``tomli`` package to parse TOML configuration files.
    """
    exe = python_exe or sys.executable
    result = subprocess.run(
        [exe, "-c", "import sys; print(sys.version_info[:2])"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return True  # assume the worst if we can't determine the version
    try:
        major, minor = eval(result.stdout.strip())
        return (major, minor) < (3, 11)
    except Exception:
        return True


def _docker_container_running(name: str) -> bool:
    """Return True if a Docker container exists and is running."""
    if not _detect_docker():
        return False
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def _stop_docker_container(name: str) -> None:
    """Stop a running Docker container."""
    _run_checked(["docker", "stop", name])


def _linux_user_service_running(name: str) -> bool:
    """Return True if a Linux systemd user service is active."""
    return _command_ok(["systemctl", "--user", "is-active", "--quiet", name])


def _stop_linux_user_service(name: str) -> None:
    """Stop a Linux systemd user service."""
    _run_checked(["systemctl", "--user", "stop", name])


def _windows_task_running(name: str) -> bool:
    """Return True if a Windows scheduled task is running."""
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return any(
        line.strip().lower() == "status: running"
        for line in result.stdout.splitlines()
    )


def _stop_windows_task(name: str) -> None:
    """Stop a Windows scheduled task."""
    _run_checked(["schtasks", "/End", "/TN", name])


def _confirm_stop_running(kind: str, name: str, stop_func) -> bool:
    """Ask whether to stop a running service before deployment."""
    print()
    print(f"Detected running {kind}: {name}")
    if not _ask_yn("Stop it before continuing?", default_yes=True):
        print("Deployment cancelled.")
        return False
    stop_func(name)
    print(f"Stopped {kind}: {name}")
    return True


def _prepare_master_container_deploy() -> bool:
    """Stop an existing Master container if the user agrees."""
    if _docker_container_running(MASTER_CONTAINER_NAME):
        return _confirm_stop_running("master container", MASTER_CONTAINER_NAME, _stop_docker_container)
    return True


def _prepare_worker_container_deploy() -> bool:
    """Stop an existing Worker container if the user agrees."""
    if _docker_container_running(WORKER_CONTAINER_NAME):
        return _confirm_stop_running("worker container", WORKER_CONTAINER_NAME, _stop_docker_container)
    return True


def _prepare_worker_host_deploy() -> bool:
    """Stop an existing host-mode Worker service if the user agrees."""
    if sys.platform == "linux" and _linux_user_service_running(WORKER_SERVICE_NAME):
        return _confirm_stop_running("worker user service", WORKER_SERVICE_NAME, _stop_linux_user_service)
    if sys.platform == "win32" and _windows_task_running(WORKER_WINDOWS_TASK_NAME):
        return _confirm_stop_running("worker scheduled task", WORKER_WINDOWS_TASK_NAME, _stop_windows_task)
    return True


def _prepare_worker_deploy() -> bool:
    """Stop any existing Worker process, regardless of deployment mode."""
    if not _prepare_worker_container_deploy():
        return False
    if not _prepare_worker_host_deploy():
        return False
    return True


def _write_linux_launcher(gaia_dir: Path, app_dir: Path, config_path: Path, venv_dir: Path) -> Path:
    """Write the Linux host-mode launcher script."""
    launcher_dir = gaia_dir / "bin"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher_path = launcher_dir / "run_worker.sh"
    python_cmd = _venv_bin(venv_dir, "python")
    launcher_path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"cd '{app_dir}'\n"
        f"export GAIABRIDGE_CONFIG='{config_path}'\n"
        f"exec '{python_cmd}' -m worker.daemon\n",
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)
    return launcher_path


def _write_windows_launcher(gaia_dir: Path, app_dir: Path, config_path: Path, venv_dir: Path) -> Path:
    """Write the Windows host-mode launcher script."""
    launcher_dir = gaia_dir / "bin"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher_path = launcher_dir / "run_worker.cmd"
    python_cmd = _venv_bin(venv_dir, "python")
    launcher_path.write_text(
        "@echo off\r\n"
        f'cd /d "{app_dir}"\r\n'
        f'set "GAIABRIDGE_CONFIG={config_path}"\r\n'
        f'"{python_cmd}" -m worker.daemon\r\n',
        encoding="utf-8",
    )
    return launcher_path


def _print_nginx_guide(port: int, path_prefix: str = "/gb") -> None:
    """Print an nginx reverse-proxy configuration guide after deploy."""
    print()
    print("=" * 60)
    print("  Exposing Master via HTTPS with nginx")
    print("=" * 60)
    print(f"""
The Master listens on 0.0.0.0:{port} (HTTP only).
To expose it securely under a domain, add a reverse-proxy
location block to your nginx site config:

    # --- Add this inside your HTTPS server block ---
    location {path_prefix}/ {{
        proxy_pass http://127.0.0.1:{port}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support -- buffering MUST be disabled
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;

        # Future WebSocket upgrade
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}

After editing, apply the change:

    sudo nginx -t && sudo nginx -s reload

Your Master will then be reachable at:
    https://<your-domain>{path_prefix}/health
""")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# master deployment (container only)
# ---------------------------------------------------------------------------

def _deploy_master_interactive(env: dict[str, str]) -> int:
    """Interactive Master configuration and deployment."""
    print()
    print("--- Master Configuration ---")
    print()

    bind_addr = _ask("Bind address", "0.0.0.0")
    port = _ask("Port", "9210")
    heartbeat = _ask("Heartbeat timeout (s)", "60")
    db_path = _ask("Database path", "/app/data/registry.db")

    print()
    print("--- Authentication Tokens ---")
    print()

    node_token_choice = _ask_choice("Node Token (worker auth):", [
        "Generate random token (recommended)",
        "Enter manually",
    ])
    if node_token_choice == 0:
        node_token = _generate_token()
        print(f"  Generated node token: {node_token}")
    else:
        node_token = _ask("Node Token")

    client_token_choice = _ask_choice("Client Token (API/client auth):", [
        "Generate random token (recommended)",
        "Enter manually",
    ])
    if client_token_choice == 0:
        client_token = _generate_token()
        print(f"  Generated client token: {client_token}")
    else:
        client_token = _ask("Client Token")

    print()
    use_cn = _ask_yn("Use China mirrors (tuna.tsinghua.edu.cn)?")

    # Resolve paths under ~/.gaia_bridge/
    gaia_home = _get_user_home() / ".gaia_bridge"
    master_config_dir = gaia_home / "master"
    master_data_dir = master_config_dir / "data"

    print()
    print("--- Review ---")
    print(f"  Listen:           {bind_addr}:{port}")
    print(f"  DB path (host):   {master_data_dir}/registry.db")
    print(f"  DB path (container): {db_path}")
    print(f"  Config (host):    {master_config_dir / 'config.toml'}")
    print(f"  Node token:       {node_token[:8]}... (auto-generated)" if node_token_choice == 0 else f"  Node token:       {node_token}")
    print(f"  Client token:     {client_token[:8]}... (auto-generated)" if client_token_choice == 0 else f"  Client token:     {client_token}")
    print(f"  China mirrors:    {'yes' if use_cn else 'no'}")
    print()

    if not _ask_yn("Save and deploy?"):
        print("Cancelled.")
        return 0

    if not _prepare_master_container_deploy():
        return 1

    # Create ~/.gaia_bridge/master/{data,} directories
    master_config_dir.mkdir(parents=True, exist_ok=True)
    master_data_dir.mkdir(parents=True, exist_ok=True)

    # Write master config to ~/.gaia_bridge/master/config.toml
    config_path = master_config_dir / "config.toml"
    _write_toml(config_path, {
        "master": {
            "host": bind_addr,
            "port": port,
            "heartbeat_timeout": heartbeat,
            "db_path": db_path,
        },
        "auth": {
            "node_token": node_token,
            "client_token": client_token,
        },
    })
    print(f"Config written to {config_path}")

    if use_cn:
        env.setdefault("APT_MIRROR", "mirrors.tuna.tsinghua.edu.cn")
        env.setdefault("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")

    # Point docker-compose at ~/.gaia_bridge/ paths
    env["GAIABRIDGE_MASTER_CONFIG"] = str(config_path)
    env["GAIABRIDGE_MASTER_DATA"] = str(master_data_dir)

    print("Deploying master (container mode)...")
    ret = _docker_compose_up(SCRIPT_DIR / "master", env)
    if ret == 0:
        print("Master deployed successfully.")
        print(f"  Config:      {config_path}")
        print(f"  Data:        {master_data_dir}")
        print(f"  Node token:  {node_token}")
        print(f"  Client token: {client_token}")
        print("  Keep these tokens - workers and clients need them to connect.")
        _print_nginx_guide(int(port))
    else:
        print("Master deployment failed. Check docker compose output above.")
    return ret


# ---------------------------------------------------------------------------
# worker deployment (container + host)
# ---------------------------------------------------------------------------

def _deploy_worker_container(env: dict[str, str], node_id: str, master_url: str,
                              node_token: str, workspace: str, host_workspace: str,
                              use_cn: bool) -> int:
    """Deploy Worker in container mode via docker compose."""
    worker_dir = SCRIPT_DIR / "worker"

    # Write worker config to ~/.gaia_bridge/worker/config.toml
    config_dir = _get_user_home() / ".gaia_bridge" / "worker"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    _write_toml(config_path, {
        "worker": {
            "mode": "container",
            "node_id": node_id,
            "master_url": master_url,
            "workspace": workspace,
            "command_timeout": "120",
            "reconnect_interval": "5",
        },
        "auth": {
            "node_token": node_token,
        },
    })
    print(f"Worker config written to {config_path}")

    if use_cn:
        env.setdefault("APT_MIRROR", "mirrors.tuna.tsinghua.edu.cn")
        env.setdefault("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")

    env["GAIABRIDGE_HOST_WORKSPACE"] = host_workspace
    env["GAIABRIDGE_CONTAINER_WORKSPACE"] = workspace
    env["GAIABRIDGE_WORKER_CONFIG"] = str(config_path)

    host_path = Path(host_workspace)
    host_path.mkdir(parents=True, exist_ok=True)

    print(f"Deploying worker (container mode)...")
    print(f"  Host workspace:      {host_workspace}")
    print(f"  Container workspace: {workspace}")

    ret = _docker_compose_up(worker_dir, env)
    if ret == 0:
        print("Worker deployed successfully.")
        print(f"  Config: {config_path}")
    else:
        print("Worker deployment failed. Check docker compose output above.")
    return ret


def _deploy_worker_host(node_id: str, master_url: str, node_token: str,
                         workspace: str, command_timeout: str,
                         reconnect_interval: str, use_cn: bool) -> int:
    """Deploy Worker in host mode as a native OS service."""
    if sys.platform not in ("linux", "win32"):
        print("Host mode service deployment currently supports Linux and Windows only.")
        return 1

    gaia_dir = _get_user_home() / ".gaia_bridge" / "worker"
    gaia_dir.mkdir(parents=True, exist_ok=True)
    app_dir = gaia_dir / "app"

    # 1. Write config.toml
    config_path = gaia_dir / "config.toml"
    _write_toml(config_path, {
        "worker": {
            "mode": "host",
            "node_id": node_id,
            "master_url": master_url,
            "workspace": workspace,
            "command_timeout": command_timeout,
            "reconnect_interval": reconnect_interval,
        },
        "auth": {
            "node_token": node_token,
        },
    })
    print(f"Config written to {config_path}")

    # 2. Install a stable application copy under ~/.gaia_bridge/worker/app
    print(f"Installing worker application copy to {app_dir} ...")
    _sync_worker_app(app_dir)

    # 3. Create venv
    venv_dir = gaia_dir / "venv"
    venv_python = str(_venv_bin(venv_dir, "python"))
    if not venv_dir.exists():
        print(f"Creating virtual environment at {venv_dir} ...")
        _run_checked([sys.executable, "-m", "venv", str(venv_dir)])

    # 4. pip install requirements
    pip_cmd = str(_venv_bin(venv_dir, "pip"))
    req_file = app_dir / "requirements.txt"

    pip_env = os.environ.copy()
    if use_cn:
        pip_env["PIP_INDEX_URL"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
        print("Using China mirror for pip.")

    # Python < 3.11 needs the third-party ``tomli`` package to parse TOML.
    needs_tomli = _python_needs_tomli(venv_python) if venv_dir.exists() else _python_needs_tomli()
    if needs_tomli:
        print()
        print("=" * 60)
        print("  Notice: Python < 3.11 detected")
        print("=" * 60)
        print("  tomllib (TOML parser) was added in Python 3.11.")
        print("  The third-party package 'tomli' will be installed")
        print("  automatically so the worker can read its config file.")
        print("=" * 60)
        print()

    print(f"Installing dependencies from {req_file} ...")
    install_cmd = [pip_cmd, "install", "-r", str(req_file)]
    if needs_tomli:
        install_cmd.append("tomli")
    _run_checked(install_cmd, env=pip_env)

    # 5. Install and start the platform service
    if sys.platform == "linux":
        launcher_path = _write_linux_launcher(gaia_dir, app_dir, config_path, venv_dir)
        _deploy_worker_host_linux(launcher_path)
    else:
        launcher_path = _write_windows_launcher(gaia_dir, app_dir, config_path, venv_dir)
        _deploy_worker_host_windows(launcher_path)

    print()
    print("Worker deployed successfully (host mode).")
    print(f"  Config:      {config_path}")
    print(f"  App:         {app_dir}")
    print(f"  Filesystem:  full host access")
    print(f"  Venv:        {venv_dir}")
    print()
    _print_host_management_commands()
    return 0


def _deploy_worker_host_linux(launcher_path: Path) -> None:
    """Install and start the Linux systemd user service."""
    _write_systemd_service(launcher_path)

    print("Enabling linger for user service...")
    subprocess.run(["loginctl", "enable-linger"], check=False)

    print("Enabling and starting systemd user service...")
    _run_checked(["systemctl", "--user", "daemon-reload"])
    _run_checked(["systemctl", "--user", "enable", "--now", WORKER_SERVICE_NAME])


def _write_systemd_service(launcher_path: Path, systemd_dir: Path | None = None) -> Path:
    """Write the systemd user service unit file."""
    unit = f"""[Unit]
Description=GaiaBridge Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={launcher_path}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""

    systemd_dir = systemd_dir or _get_user_home() / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    unit_path = systemd_dir / f"{WORKER_SERVICE_NAME}.service"
    unit_path.write_text(unit, encoding="utf-8")
    print(f"Systemd unit written to {unit_path}")
    return unit_path


def _deploy_worker_host_windows(launcher_path: Path) -> None:
    """Install and start a Windows scheduled task for the worker."""
    print("Creating Windows scheduled task...")
    subprocess.run(["schtasks", "/Delete", "/TN", WORKER_WINDOWS_TASK_NAME, "/F"], check=False)
    _run_checked([
        "schtasks", "/Create",
        "/TN", WORKER_WINDOWS_TASK_NAME,
        "/SC", "ONLOGON",
        "/TR", str(launcher_path),
        "/RL", "LIMITED",
        "/F",
    ])
    _run_checked(["schtasks", "/Run", "/TN", WORKER_WINDOWS_TASK_NAME])


def _print_host_management_commands() -> None:
    """Print platform-specific host service management commands."""
    print("Management commands:")
    if sys.platform == "linux":
        print(f"  systemctl --user status {WORKER_SERVICE_NAME}")
        print(f"  systemctl --user restart {WORKER_SERVICE_NAME}")
        print(f"  journalctl --user -u {WORKER_SERVICE_NAME} -f")
    elif sys.platform == "win32":
        print(f"  schtasks /Query /TN {WORKER_WINDOWS_TASK_NAME}")
        print(f"  schtasks /Run /TN {WORKER_WINDOWS_TASK_NAME}")
        print(f"  schtasks /End /TN {WORKER_WINDOWS_TASK_NAME}")


def _deploy_worker_interactive(env: dict[str, str]) -> int:
    """Interactive Worker configuration and deployment."""
    print()
    print("--- Worker Configuration ---")
    print()

    # Mode selection
    mode_idx = _ask_choice("Deployment mode:", [
        "Container mode  -- Docker sandbox, limited filesystem access\n"
        "                      Mounts a selected host directory as /workspace",
        "Host mode       -- runs natively, full system capabilities\n"
        "                      Linux systemd service for trusted machines",
    ])
    mode = "container" if mode_idx == 0 else "host"

    print()
    print("--- Identity ---")

    import platform
    default_node_id = platform.node() or "worker-1"
    node_id = _ask("Node ID (unique name)", default_node_id)
    master_url = _ask("Master URL (e.g. https://your-server.com/gb)")

    print()
    print("--- Authentication ---")
    node_token = _ask("Node Token (must match Master's node_token)")

    print()
    if mode == "container":
        print("--- Workspace (Container Mode) ---")
        container_ws = _ask("Container workspace path", "/workspace")
        default_host_ws = str(_get_user_home() / ".gaia_bridge" / "workspace")
        host_ws = _ask("Host directory to mount", default_host_ws)
        command_timeout = "120"
        reconnect_interval = "5"
        workspace_for_config = container_ws
    else:
        print("--- Host Mode (full filesystem access) ---")
        workspace_for_config = "/"
        host_ws = "/"                    # not used in host mode, but keep variable clean
        container_ws = "/workspace"      # ditto
        command_timeout = _ask("Command timeout (s)", "120")
        reconnect_interval = _ask("Reconnect interval (s)", "5")

    print()
    use_cn = _ask_yn("Use China mirrors for pip?")

    # Config location: both modes now use ~/.gaia_bridge/worker/
    config_location = str(_get_user_home() / ".gaia_bridge" / "worker" / "config.toml")

    print()
    print("--- Review ---")
    print(f"  Mode:             {mode}")
    print(f"  Node ID:          {node_id}")
    print(f"  Master URL:       {master_url}")
    if mode == "container":
        print(f"  Container ws:     {container_ws}")
        print(f"  Host mount:       {host_ws}")
    else:
        print(f"  Filesystem:       full host access")
        print(f"  Command timeout:  {command_timeout}s")
        print(f"  Reconnect:        {reconnect_interval}s")
    print(f"  Config location:  {config_location}")
    print(f"  China mirrors:    {'yes' if use_cn else 'no'}")
    print()

    if not _ask_yn("Save and deploy?"):
        print("Cancelled.")
        return 0

    if not _prepare_worker_deploy():
        return 1

    if mode == "container":
        return _deploy_worker_container(
            env, node_id, master_url, node_token,
            container_ws, host_ws, use_cn,
        )
    else:
        return _deploy_worker_host(
            node_id, master_url, node_token,
            workspace_for_config, command_timeout,
            reconnect_interval, use_cn,
        )


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    print("=================================")
    print("    GaiaBridge Deployment")
    print("=================================")
    print()

    if not _detect_docker():
        print("WARNING: Docker not detected. Container mode deployments will fail.")
        print("         Host mode worker deployment is still available.")
        print()

    component_idx = _ask_choice("Which component would you like to deploy?", [
        "Master  -- central control plane (public server)",
        "Worker  -- execution node (any machine)",
        "Both    -- master + worker on this machine",
    ])

    env = os.environ.copy()
    env.setdefault("DOCKER_BUILDKIT", "0")

    ret = 0

    if component_idx == 0:  # Master only
        ret = _deploy_master_interactive(env)
    elif component_idx == 1:  # Worker only
        ret = _deploy_worker_interactive(env)
    elif component_idx == 2:  # Both
        ret = _deploy_master_interactive(env)
        if ret == 0:
            print()
            print("Master is up. Now configuring Worker...")
            # Pre-fill Master URL for local setup
            # (Worker flow will ask its own questions)
            ret = _deploy_worker_interactive(env)

    return ret


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nDeployment cancelled.")
        sys.exit(130)
    except EOFError:
        print("\n\nDeployment cancelled.")
        sys.exit(130)
