"""SSE connection pool manager (Broker)."""

import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Broker:
    """Manages SSE event queues for connected worker nodes."""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    def connect(self, node_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self._queues[node_id] = q
        logger.info("broker: node %s connected", node_id)
        return q

    def disconnect(self, node_id: str):
        self._queues.pop(node_id, None)
        logger.info("broker: node %s disconnected", node_id)

    def is_connected(self, node_id: str) -> bool:
        return node_id in self._queues

    def connected_nodes(self) -> list[str]:
        return list(self._queues.keys())

    async def push(self, node_id: str, event: str, data: dict) -> bool:
        q = self._queues.get(node_id)
        if not q:
            return False
        msg = {"event": event, "data": data}
        await q.put(msg)
        return True

    async def broadcast_ping(self):
        for node_id in list(self._queues.keys()):
            await self.push(node_id, "ping", {})
