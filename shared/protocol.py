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
