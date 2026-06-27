#!/usr/bin/env python3
"""WorkBridge client: dispatch tasks to a worker through the Master API."""

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request

try:
    from .config import load_client_config
except ImportError:
    from config import load_client_config


TOOLS = {
    "run_command": "Execute a shell command",
    "read_file": "Read a file",
    "write_file": "Write a file",
    "list_directory": "List directory contents",
    "system_info": "Show basic system information",
}


class WorkBridgeClient:
    def __init__(self, config):
        self.config = config

    def _post_json(self, path, payload):
        url = self.config.master_url.rstrip("/") + path
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.client_token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, context=ssl.create_default_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body}") from e

    def _get_json(self, path):
        url = self.config.master_url.rstrip("/") + path
        try:
            with urllib.request.urlopen(url, context=ssl.create_default_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body}") from e

    def list_nodes(self):
        return self._get_json("/api/nodes")

    def dispatch_sync(self, node_id, task_type, params):
        result = self._post_json(
            "/api/tasks/dispatch_sync",
            {
                "target_node": node_id,
                "timeout": self.config.timeout,
                "payload": {
                    "task_type": task_type,
                    "params": params,
                },
            },
        )
        error = result.get("error", "")
        if error:
            raise RuntimeError(error)
        return result


def build_task(action, args):
    if action == "run_command":
        return "shell", {"command": args.command}
    if action == "read_file":
        return "file_read", {"path": args.path}
    if action == "write_file":
        return "file_write", {"path": args.path, "content": args.content}
    if action == "list_directory":
        return "list_dir", {"path": args.path}
    if action == "system_info":
        return "shell", {"command": "pwd; uname -a; echo; df -h .; echo; id"}
    raise RuntimeError(f"unknown action: {action}")


def print_result(result):
    output = result.get("output", "")
    error = result.get("error", "")
    status = result.get("status", "")

    if output:
        print(output)
    if error:
        print(error, file=sys.stderr)
    if status and status != "completed":
        raise SystemExit(1)


def print_nodes(nodes):
    if not nodes:
        print("(no nodes)")
        return

    print("node_id\tstatus\thostname\tos\tworkspace\tcapabilities")
    for node in nodes:
        print(
            "\t".join([
                str(node.get("node_id", "")),
                str(node.get("status", "")),
                str(node.get("hostname", "")),
                str(node.get("os", "")),
                str(node.get("workspace", "")),
                ",".join(node.get("capabilities", [])),
            ])
        )


def main():
    parser = argparse.ArgumentParser(description="Dispatch WorkBridge tasks")
    parser.add_argument("--config", help="path to client INI config")

    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("list_nodes", help="List registered worker nodes")

    p = sub.add_parser("run_command", help=TOOLS["run_command"])
    p.add_argument("--node", required=True, help="target worker node id")
    p.add_argument("command")

    p = sub.add_parser("read_file", help=TOOLS["read_file"])
    p.add_argument("--node", required=True, help="target worker node id")
    p.add_argument("path")

    p = sub.add_parser("write_file", help=TOOLS["write_file"])
    p.add_argument("--node", required=True, help="target worker node id")
    p.add_argument("path")
    p.add_argument("content")

    p = sub.add_parser("list_directory", help=TOOLS["list_directory"])
    p.add_argument("--node", required=True, help="target worker node id")
    p.add_argument("path", nargs="?", default=".")

    p = sub.add_parser("system_info", help=TOOLS["system_info"])
    p.add_argument("--node", required=True, help="target worker node id")

    args = parser.parse_args()
    config = load_client_config(args.config)
    client = WorkBridgeClient(config)

    try:
        if args.action == "list_nodes":
            print_nodes(client.list_nodes())
            return

        task_type, params = build_task(args.action, args)
        print_result(client.dispatch_sync(args.node, task_type, params))
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
