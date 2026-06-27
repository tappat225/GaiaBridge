"""Result reporter: sends execution results back to Master."""

import json
import logging
import ssl
import urllib.request
import urllib.error

from shared.protocol import TaskResult

logger = logging.getLogger(__name__)


class Reporter:
    def __init__(self, master_url: str, node_token: str):
        self._url = master_url.rstrip("/") + "/api/tasks/result"
        self._token = node_token

    def report(self, result: TaskResult) -> bool:
        data = json.dumps(result.model_dump(mode="json")).encode()
        req = urllib.request.Request(
            self._url, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            })
        ctx = ssl.create_default_context()
        try:
            resp = urllib.request.urlopen(req, context=ctx, timeout=15)
            return resp.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.error("reporter: failed to send result for %s: %s", result.task_id, e)
            return False
