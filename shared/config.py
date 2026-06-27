"""Configuration schema for Master and Worker."""

import os
from dataclasses import dataclass


@dataclass
class MasterConfig:
    host: str = os.environ.get("MASTER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("MASTER_PORT", "8100"))
    node_token: str = os.environ.get("NODE_TOKEN", "")
    client_token: str = os.environ.get("CLIENT_TOKEN", "")
    heartbeat_timeout: int = int(os.environ.get("HEARTBEAT_TIMEOUT", "60"))
    db_path: str = os.environ.get("MASTER_DB", "registry.db")


@dataclass
class WorkerConfig:
    node_id: str = os.environ.get("NODE_ID", "")
    master_url: str = os.environ.get("MASTER_URL", "https://localhost:8100")
    node_token: str = os.environ.get("NODE_TOKEN", "")
    workspace: str = os.environ.get("WORKSPACE_DIR", "/workspace")
    command_timeout: int = int(os.environ.get("COMMAND_TIMEOUT", "120"))
    reconnect_interval: int = int(os.environ.get("RECONNECT_INTERVAL", "5"))
