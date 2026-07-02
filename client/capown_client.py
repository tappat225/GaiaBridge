#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""CapOwn client: dispatch tasks to a worker through the Master API.

Usage:
  capown nodes                              List registered workers
  capown run <node> <command>               Run a shell command on a worker
  capown read <node> <path>                 Read a file on a worker
  capown write <node> <path> <content>      Write content to a file on a worker
  capown ls <node> [path]                   List directory contents on a worker
  capown info <node>                        Show system information for a worker

Legacy aliases (still supported):
  list_nodes, run_command, read_file, write_file, list_directory, system_info
"""

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

# New command names and their legacy/old-style equivalents
COMMAND_ALIASES = {
    # new -> (legacy_action, tool_help)
    "nodes":   ("list_nodes", "List registered worker nodes"),
    "run":     ("run_command", "Execute a shell command on a worker"),
    "read":    ("read_file", "Read a file from a worker"),
    "write":   ("write_file", "Write content to a file on a worker"),
    "ls":      ("list_directory", "List directory contents on a worker"),
    "info":    ("system_info", "Show system information for a worker"),
}


class CapOwnClient:
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
        return self._post_json(
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
        return "system_info", {}
    raise RuntimeError(f"unknown action: {action}")


def print_result(result):
    output = result.get("output", "")
    error = result.get("error", "")
    status = result.get("status", "")
    error_code = result.get("error_code", "")
    truncated = result.get("truncated", False)

    if error_code:
        prefix = f"[{error_code}]"
        if truncated:
            prefix += " [truncated]"
        print(prefix, file=sys.stderr)

    if output:
        print(output)
    if error:
        if error_code:
            print(f"  {error}", file=sys.stderr)
        else:
            print(error, file=sys.stderr)
    if status and status != "completed":
        raise SystemExit(1)


def print_nodes(nodes):
    if not nodes:
        print("(no nodes)")
        return

    # header
    print("node_id  status    hostname  os  mode       capabilities  workspace")
    for node in nodes:
        nid = str(node.get("node_id", ""))
        st = str(node.get("status", ""))
        hn = str(node.get("hostname", ""))
        os = str(node.get("os", ""))
        mode = str(node.get("mode", ""))
        caps = ",".join(node.get("capabilities", []))
        ws = str(node.get("workspace", ""))
        print(f"{nid:8s} {st:8s} {hn:8s} {os:3s} {mode:10s} {caps:12s} {ws}")


def main():
    parser = argparse.ArgumentParser(
        description="CapOwn CLI - dispatch tasks to remote workers")

    parser.add_argument("--config", help="path to client INI config")

    sub = parser.add_subparsers(dest="action", required=True)

    # -- Legacy commands (keep compatibility) --
    sub.add_parser("list_nodes", help=TOOLS["run_command"])

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

    # -- New user-facing commands --
    p = sub.add_parser("nodes", help=COMMAND_ALIASES["nodes"][1])
    p.add_argument("--node", nargs="?", help="filter by node id (optional)")

    p = sub.add_parser("run", help=COMMAND_ALIASES["run"][1])
    p.add_argument("node", help="target worker node id")
    p.add_argument("command", help="shell command to execute")

    p = sub.add_parser("read", help=COMMAND_ALIASES["read"][1])
    p.add_argument("node", help="target worker node id")
    p.add_argument("path", help="file path to read")

    p = sub.add_parser("write", help=COMMAND_ALIASES["write"][1])
    p.add_argument("node", help="target worker node id")
    p.add_argument("path", help="file path to write")
    p.add_argument("content", help="content to write")

    p = sub.add_parser("ls", help=COMMAND_ALIASES["ls"][1])
    p.add_argument("node", help="target worker node id")
    p.add_argument("path", nargs="?", default=".", help="directory path (default: .)")

    p = sub.add_parser("info", help=COMMAND_ALIASES["info"][1])
    p.add_argument("node", help="target worker node id")

    args = parser.parse_args()
    config = load_client_config(args.config)
    client = CapOwnClient(config)

    try:
        # Map new commands to legacy actions
        action = args.action
        if action in COMMAND_ALIASES:
            legacy_action, _ = COMMAND_ALIASES[action]

            if action == "nodes":
                nodes = client.list_nodes()
                if args.node:
                    nodes = [n for n in nodes if n.get("node_id") == args.node]
                print_nodes(nodes)
                return

            # All other new commands need the node arg passed positionally
            if action == "run":
                task_type, params = build_task(legacy_action, args)
                print_result(client.dispatch_sync(args.node, task_type, params))
            elif action == "read":
                task_type, params = build_task(legacy_action, args)
                print_result(client.dispatch_sync(args.node, task_type, params))
            elif action == "write":
                task_type, params = build_task(legacy_action, args)
                print_result(client.dispatch_sync(args.node, task_type, params))
            elif action == "ls":
                task_type, params = build_task(legacy_action, args)
                print_result(client.dispatch_sync(args.node, task_type, params))
            elif action == "info":
                task_type, params = build_task(legacy_action, args)
                print_result(client.dispatch_sync(args.node, task_type, params))
            return

        # Legacy command handling
        if action == "list_nodes":
            print_nodes(client.list_nodes())
            return

        task_type, params = build_task(action, args)
        print_result(client.dispatch_sync(args.node, task_type, params))
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
