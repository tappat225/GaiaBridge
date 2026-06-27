"""Worker daemon: connects to Master via SSE and executes tasks."""

import asyncio
import json
import logging
import platform
import ssl
import urllib.request
import urllib.error

from shared.config import WorkerConfig
from shared.protocol import TaskResult, TaskStatus, TaskType
from .executor.shell import ShellExecutor
from .executor.file import FileExecutor
from .reporter import Reporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class WorkerDaemon:
    def __init__(self, config: WorkerConfig = None):
        self._config = config or WorkerConfig()
        self._shell = ShellExecutor(self._config.workspace, self._config.command_timeout)
        self._file = FileExecutor(self._config.workspace)
        self._reporter = Reporter(self._config.master_url, self._config.node_token)
        self._running = False

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._config.node_token}",
            "Accept": "text/event-stream",
        }

    def _register(self):
        url = self._config.master_url.rstrip("/") + "/api/nodes/register"
        data = json.dumps({
            "node_id": self._config.node_id,
            "hostname": platform.node(),
            "os": platform.system().lower(),
            "capabilities": ["shell", "file"],
            "workspace": self._config.workspace,
        }).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._config.node_token}"})
        ctx = ssl.create_default_context()
        resp = urllib.request.urlopen(req, context=ctx, timeout=15)
        logger.info("worker: registered as %s", self._config.node_id)
        return resp.status == 200

    async def _handle_task(self, task_data: dict):
        task_id = task_data.get("task_id", "")
        payload = task_data.get("payload", {})
        task_type = payload.get("task_type", "")
        params = payload.get("params", {})

        logger.info("worker: executing task %s (%s)", task_id, task_type)

        if task_type in (TaskType.shell, "shell"):
            result = await self._shell.execute(params)
        elif task_type in (TaskType.file_read, "file_read"):
            params["action"] = "read"
            result = await self._file.execute(params)
        elif task_type in (TaskType.file_write, "file_write"):
            params["action"] = "write"
            result = await self._file.execute(params)
        elif task_type in (TaskType.list_dir, "list_dir"):
            params["action"] = "list"
            result = await self._file.execute(params)
        else:
            result = type("R", (), {"success": False, "output": "", "error": f"unknown task type: {task_type}"})()

        task_result = TaskResult(
            task_id=task_id,
            node_id=self._config.node_id,
            status=TaskStatus.completed if result.success else TaskStatus.failed,
            output=result.output,
            error=result.error)
        self._reporter.report(task_result)

    async def _listen_sse(self):
        url = (self._config.master_url.rstrip("/") +
               f"/api/events?node_id={self._config.node_id}")
        req = urllib.request.Request(url, headers=self._headers())
        ctx = ssl.create_default_context()

        resp = urllib.request.urlopen(req, context=ctx, timeout=300)
        logger.info("worker: SSE connected to master")

        buffer = ""
        while self._running:
            chunk = resp.read(4096)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                await self._process_sse_event(event_str)

    async def _process_sse_event(self, raw: str):
        event_type = ""
        data_str = ""
        for line in raw.split("\n"):
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()

        if event_type == "ping" or not data_str:
            return

        try:
            data = json.loads(data_str)
            await self._handle_task(data)
        except json.JSONDecodeError:
            logger.error("worker: invalid SSE data: %s", data_str[:100])

    async def run(self):
        self._running = True
        self._register()

        while self._running:
            try:
                await self._listen_sse()
            except Exception as e:
                logger.error("worker: SSE connection lost: %s", e)
            if self._running:
                logger.info("worker: reconnecting in %ds...", self._config.reconnect_interval)
                await asyncio.sleep(self._config.reconnect_interval)

    def stop(self):
        self._running = False


if __name__ == "__main__":
    daemon = WorkerDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        daemon.stop()
