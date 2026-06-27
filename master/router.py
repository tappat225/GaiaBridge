"""Task router: dispatches tasks and matches results."""

import asyncio
import logging
from typing import Optional

from shared.protocol import Task, TaskResult, TaskStatus

from .broker import Broker

logger = logging.getLogger(__name__)


class Router:
    def __init__(self, broker: Broker):
        self._broker = broker
        self._pending: dict[str, asyncio.Future] = {}
        self._results: dict[str, TaskResult] = {}

    async def dispatch(self, task: Task) -> bool:
        """Push task to target node via broker. Returns False if node offline."""
        if not self._broker.is_connected(task.target_node):
            return False

        fut = asyncio.get_event_loop().create_future()
        self._pending[task.task_id] = fut

        sent = await self._broker.push(task.target_node, "task", task.model_dump(mode="json"))
        if not sent:
            self._pending.pop(task.task_id, None)
            return False

        logger.info("router: dispatched task %s to %s", task.task_id, task.target_node)
        return True

    async def wait_result(self, task_id: str, timeout: int = 120) -> Optional[TaskResult]:
        """Wait for task result with timeout."""
        fut = self._pending.get(task_id)
        if not fut:
            return self._results.get(task_id)
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(task_id, None)
            return TaskResult(
                task_id=task_id, node_id="",
                status=TaskStatus.timeout, error="task timed out")

    def submit_result(self, result: TaskResult):
        """Called when worker reports back."""
        self._results[result.task_id] = result
        fut = self._pending.pop(result.task_id, None)
        if fut and not fut.done():
            fut.set_result(result)
        logger.info("router: result for task %s: %s", result.task_id, result.status)

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        return self._results.get(task_id)
