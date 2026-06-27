"""Node registry backed by SQLite."""

import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional

from shared.protocol import NodeInfo, NodeStatus


class Registry:
    def __init__(self, db_path: str = "registry.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    os TEXT DEFAULT 'linux',
                    capabilities TEXT DEFAULT 'shell,file',
                    workspace TEXT DEFAULT '/workspace',
                    status TEXT DEFAULT 'online',
                    last_heartbeat TEXT,
                    registered_at TEXT
                )
            """)

    def register(self, node_id: str, hostname: str, os_name: str = "linux",
                 capabilities: list[str] = None, workspace: str = "/workspace") -> NodeInfo:
        now = datetime.utcnow().isoformat()
        caps = ",".join(capabilities or ["shell", "file"])
        with self._lock, self._conn() as conn:
            conn.execute("""
                INSERT INTO nodes (node_id, hostname, os, capabilities, workspace, status, last_heartbeat, registered_at)
                VALUES (?, ?, ?, ?, ?, 'online', ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    hostname=excluded.hostname, os=excluded.os,
                    capabilities=excluded.capabilities, workspace=excluded.workspace,
                    status='online', last_heartbeat=excluded.last_heartbeat
            """, (node_id, hostname, os_name, caps, workspace, now, now))
        return self.get(node_id)

    def heartbeat(self, node_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "UPDATE nodes SET last_heartbeat=?, status='online' WHERE node_id=?",
                (now, node_id))
            return cur.rowcount > 0

    def get(self, node_id: str) -> Optional[NodeInfo]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        if not row:
            return None
        return NodeInfo(
            node_id=row["node_id"], hostname=row["hostname"], os=row["os"],
            capabilities=row["capabilities"].split(","),
            workspace=row["workspace"], status=NodeStatus(row["status"]),
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"]) if row["last_heartbeat"] else None,
            registered_at=datetime.fromisoformat(row["registered_at"]) if row["registered_at"] else None,
        )

    def list_all(self) -> list[NodeInfo]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM nodes").fetchall()
        return [self.get(row["node_id"]) for row in rows]

    def mark_offline(self, node_id: str):
        with self._lock, self._conn() as conn:
            conn.execute("UPDATE nodes SET status='offline' WHERE node_id=?", (node_id,))

    def sweep_stale(self, timeout_seconds: int = 60):
        cutoff = (datetime.utcnow() - timedelta(seconds=timeout_seconds)).isoformat()
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE nodes SET status='offline' WHERE last_heartbeat < ? AND status='online'",
                (cutoff,))
