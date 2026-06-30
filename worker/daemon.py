"""Worker daemon: connects to Master via SSE and executes tasks."""

import asyncio
import json
import logging
import platform

import httpx

from shared.config import WorkerConfig, load_worker_config
from shared.protocol import TaskResult, TaskStatus, TaskType
from .executor.shell import ShellExecutor
from .executor.file import FileExecutor
from .reporter import Reporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class WorkerDaemon:
    def __init__(self, config: WorkerConfig = None):
        self._config = config or load_worker_config()
        self._mode = self._config.mode
        self._shell = ShellExecutor(self._config.workspace, self._config.command_timeout)
        self._file = FileExecutor(self._config.workspace)
        self._reporter = Reporter(self._config.master_url, self._config.node_token)
        self._running = False

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._config.node_token}",
        }

    def _register(self):
        url = self._config.master_url.rstrip("/") + "/api/nodes/register"
        capabilities = ["shell", "file"]
        data = {
            "node_id": self._config.node_id,
            "hostname": platform.node(),
            "os": platform.system().lower(),
            "capabilities": capabilities,
            "workspace": self._config.workspace,
            "mode": self._mode,
        }
        resp = httpx.post(url, json=data, headers=self._headers(), timeout=15)
        logger.info("worker: registered as %s (mode=%s)", self._config.node_id, self._mode)
        return resp.status_code == 200

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
        headers = {**self._headers(), "Accept": "text/event-stream"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15)) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                logger.info("worker: SSE connected to master")

                buffer = ""
                async for chunk in resp.aiter_bytes():
                    if not self._running:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\r\n\r\n" in buffer:
                        event_str, buffer = buffer.split("\r\n\r\n", 1)
                        await self._process_sse_event(event_str)

    async def _process_sse_event(self, raw: str):
        event_type = ""
        data_str = ""
        for line in raw.split("\r\n"):
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
        logger.info("worker: starting daemon (mode=%s, node_id=%s)", self._mode, self._config.node_id)

        if self._mode == "host":
            logger.info("worker: host mode active - commands run on the host system")
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
