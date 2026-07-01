# SPDX-License-Identifier: Apache-2.0
"""Shared protocol definitions for GaiaBridge distributed system."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================

class NodeStatus(str, Enum):
    online = "online"
    offline = "offline"


class TaskStatus(str, Enum):
    pending = "pending"
    dispatched = "dispatched"
    running = "running"
    completed = "completed"
    failed = "failed"
    timeout = "timeout"


class TaskType(str, Enum):
    shell = "shell"
    file_read = "file_read"
    file_write = "file_write"
    list_dir = "list_dir"
    system_info = "system_info"


class ErrorCode(str, Enum):
    """Structured machine-readable error codes for task results."""
    node_offline = "node_offline"
    auth_denied = "auth_denied"
    capability_not_found = "capability_not_found"
    schema_invalid = "schema_invalid"
    workspace_violation = "workspace_violation"
    timeout = "timeout"
    output_too_large = "output_too_large"
    execution_failed = "execution_failed"
    worker_unhealthy = "worker_unhealthy"
    rate_limited = "rate_limited"


class Capability(str, Enum):
    """Product-facing capability names exposed to users and agents."""
    system_info = "system.info"
    file_list = "file.list"
    file_read = "file.read"
    file_write = "file.write"
    shell_run = "shell.run"


# Map from product-facing Capability to internal TaskType
CAPABILITY_TO_TASK_TYPE: dict[Capability, TaskType] = {
    Capability.system_info: TaskType.system_info,
    Capability.file_list: TaskType.list_dir,
    Capability.file_read: TaskType.file_read,
    Capability.file_write: TaskType.file_write,
    Capability.shell_run: TaskType.shell,
}

# Reverse map: internal TaskType -> product-facing Capability
TASK_TYPE_TO_CAPABILITY: dict[TaskType, Capability] = {
    v: k for k, v in CAPABILITY_TO_TASK_TYPE.items()
}

# Legacy backward-compatible aliases for CLI
LEGACY_TO_CAPABILITY: dict[str, Capability] = {
    "list_nodes": None,
    "run_command": Capability.shell_run,
    "read_file": Capability.file_read,
    "write_file": Capability.file_write,
    "list_directory": Capability.file_list,
    "system_info": Capability.system_info,
}


# ============================================================
# Node models
# ============================================================

class NodeInfo(BaseModel):
    node_id: str
    hostname: str
    os: str = "linux"
    mode: str = "container"
    capabilities: list[str] = Field(default_factory=lambda: ["shell", "file"])
    workspace: str = "/workspace"
    status: NodeStatus = NodeStatus.online
    last_heartbeat: Optional[datetime] = None
    registered_at: Optional[datetime] = None


class NodeRegisterRequest(BaseModel):
    node_id: str
    hostname: str
    os: str = "linux"
    mode: str = "container"
    capabilities: list[str] = Field(default_factory=lambda: ["shell", "file"])
    workspace: str = "/workspace"


class NodeHeartbeat(BaseModel):
    node_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Task models
# ============================================================

class TaskPayload(BaseModel):
    task_type: TaskType
    params: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    target_node: str
    payload: TaskPayload
    status: TaskStatus = TaskStatus.pending
    created_at: datetime = Field(default_factory=datetime.utcnow)
    timeout: int = 120


class TaskResult(BaseModel):
    task_id: str
    node_id: str
    status: TaskStatus
    output: str = ""
    error: str = ""
    error_code: Optional[str] = None
    truncated: bool = False
    completed_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# SSE event model
# ============================================================

class SSEEvent(BaseModel):
    event: str = "task"
    data: dict[str, Any] = Field(default_factory=dict)

    def serialize(self) -> str:
        import json
        return f"event: {self.event}\ndata: {json.dumps(self.data)}\n\n"
