# SPDX-License-Identifier: Apache-2.0
"""Configuration schemas and loaders for Master and Worker."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pwd
    _HAS_PWD = True
except ImportError:
    _HAS_PWD = False

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 and older
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def _get_user_home() -> Path:
    """Return the real user's home directory, even when running under sudo."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and _HAS_PWD:
        return Path(pwd.getpwnam(sudo_user).pw_dir)
    return Path.home()


def _read_toml(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    if not path:
        return {}

    config_path = Path(path)
    if not config_path.exists():
        return {}

    if tomllib is None:
        raise RuntimeError("TOML configuration requires Python 3.11 or newer")

    with config_path.open("rb") as f:
        return tomllib.load(f)


def _env(name: str, fallback: Any) -> Any:
    value = os.environ.get(name)
    return fallback if value is None or value == "" else value


def _as_int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} must be an integer") from e


def _default_path(service: str) -> str:
    env_name = f"CAPOWN_{service.upper()}_CONFIG"
    configured = os.environ.get("CAPOWN_CONFIG", os.environ.get(env_name, ""))
    if configured:
        return configured

    candidates = [
        _get_user_home() / ".capown" / service / "config.toml",
        Path("/etc/capown") / f"{service}.toml",
        Path(__file__).resolve().parent.parent / service / "config.toml",
    ]
    return str(next((candidate for candidate in candidates if candidate.exists()), ""))


@dataclass
class MasterConfig:
    host: str = "0.0.0.0"
    port: int = 9210
    node_token: str = ""
    client_token: str = ""
    heartbeat_timeout: int = 60
    db_path: str = "/app/data/registry.db"

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> "MasterConfig":
        data = _read_toml(path or _default_path("master"))
        master = data.get("master", {})
        auth = data.get("auth", {})

        return cls(
            host=str(_env("MASTER_HOST", master.get("host", cls.host))),
            port=_as_int(_env("MASTER_PORT", master.get("port", cls.port)), "MASTER_PORT"),
            node_token=str(_env("NODE_TOKEN", auth.get("node_token", cls.node_token))),
            client_token=str(_env("CLIENT_TOKEN", auth.get("client_token", cls.client_token))),
            heartbeat_timeout=_as_int(
                _env("HEARTBEAT_TIMEOUT", master.get("heartbeat_timeout", cls.heartbeat_timeout)),
                "HEARTBEAT_TIMEOUT",
            ),
            db_path=str(_env("MASTER_DB", master.get("db_path", cls.db_path))),
        )


@dataclass
class WorkerConfig:
    mode: str = "container"   # "host" | "container"
    node_id: str = ""
    master_url: str = "https://localhost:9210"
    node_token: str = ""
    workspace: str = "/workspace"
    command_timeout: int = 120
    reconnect_interval: int = 5
    max_output_size: int = 200_000

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> "WorkerConfig":
        data = _read_toml(path or _default_path("worker"))
        worker = data.get("worker", {})
        auth = data.get("auth", {})

        return cls(
            mode=str(_env("WORKER_MODE", worker.get("mode", cls.mode))),
            node_id=str(_env("NODE_ID", worker.get("node_id", cls.node_id))),
            master_url=str(_env("MASTER_URL", worker.get("master_url", cls.master_url))),
            node_token=str(_env("NODE_TOKEN", auth.get("node_token", cls.node_token))),
            workspace=str(_env("WORKSPACE_DIR", worker.get("workspace", cls.workspace))),
            command_timeout=_as_int(
                _env("COMMAND_TIMEOUT", worker.get("command_timeout", cls.command_timeout)),
                "COMMAND_TIMEOUT",
            ),
            reconnect_interval=_as_int(
                _env("RECONNECT_INTERVAL", worker.get("reconnect_interval", cls.reconnect_interval)),
                "RECONNECT_INTERVAL",
            ),
            max_output_size=_as_int(
                _env("MAX_OUTPUT_SIZE", worker.get("max_output_size", cls.max_output_size)),
                "MAX_OUTPUT_SIZE",
            ),
        )


def load_master_config(path: str | os.PathLike[str] | None = None) -> MasterConfig:
    return MasterConfig.load(path)


def load_worker_config(path: str | os.PathLike[str] | None = None) -> WorkerConfig:
    return WorkerConfig.load(path)
