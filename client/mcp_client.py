#!/usr/bin/env python3
"""
MCP Client — send commands to a remote MCP server.

If the local daemon (mcp_daemon.py) is running, requests go through it
for instant response. Otherwise a direct connection is made.

Usage:
    python3 mcp_client.py run_command "ls -la"
    python3 mcp_client.py list_directory .
    python3 mcp_client.py read_file some/file.txt
    python3 mcp_client.py write_file some/file.txt "content"
    python3 mcp_client.py system_info
    python3 mcp_client.py shell
"""

import json
import os
import sys
import ssl
import socket
import urllib.request
import urllib.error

# ============================================================
# Configuration (set via environment variables)
# ============================================================
MCP_URL = os.environ.get("MCP_URL", "https://<your-domain>/_mcp")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "<your-bearer-token>")
SOCKET_PATH = os.environ.get("MCP_SOCKET_PATH", "/tmp/mcp-daemon.sock")

TOOLS = {
    "run_command":    {"args": ["command"],          "desc": "Execute a shell command"},
    "read_file":      {"args": ["path"],             "desc": "Read a file"},
    "write_file":     {"args": ["path", "content"],  "desc": "Write a file"},
    "list_directory": {"args": ["path?"],            "desc": "List directory contents"},
    "system_info":    {"args": [],                   "desc": "Show system info"},
}


# ============================================================
# Daemon client (fast path)
# ============================================================
def call_via_daemon(tool, args):
    """Send a request through the local daemon socket. Raises on connection failure."""
    request = json.dumps({"tool": tool, "args": args})
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    try:
        sock.connect(SOCKET_PATH)
        sock.sendall(request.encode() + b"\n")
        response = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            response += chunk
            if b"\n" in chunk:
                break
    finally:
        sock.close()

    if not response:
        raise ConnectionError("daemon returned empty response")

    data = json.loads(response.decode("utf-8"))
    if "error" in data:
        print(f"error: {data['error']}", file=sys.stderr)
        return None
    return data.get("result", str(data))


def daemon_is_running():
    return os.path.exists(SOCKET_PATH)


# ============================================================
# Direct connection (fallback)
# ============================================================
class DirectClient:
    def __init__(self, url=MCP_URL, token=AUTH_TOKEN):
        self.url = url
        self.token = token
        self.session_id = None
        self._req_id = 0

    def _next_id(self):
        self._req_id += 1
        return self._req_id

    def _headers(self):
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session_id:
            h["mcp-session-id"] = self.session_id
        return h

    def _post(self, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, headers=self._headers(), method="POST"
        )
        ctx = ssl.create_default_context()
        try:
            resp = urllib.request.urlopen(req, context=ctx)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print(f"error: HTTP {e.code} - {body}", file=sys.stderr)
            return None
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        body = resp.read().decode("utf-8", errors="replace")
        return self._parse_sse(body)

    def _parse_sse(self, raw):
        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    return {"_raw": data_str}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}

    def connect(self):
        payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-client", "version": "1.0"},
            },
            "id": self._next_id(),
        }
        result = self._post(payload)
        if result is None:
            return False
        self._post({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        return True

    def call_tool(self, name, arguments):
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
            "id": self._next_id(),
        }
        result = self._post(payload)
        if result is None:
            return None
        if "error" in result:
            print(f"error: {result['error']}", file=sys.stderr)
            return None
        content = result.get("result", {}).get("content", [])
        if content and len(content) > 0:
            return content[0].get("text", str(content))
        return str(result)


# ============================================================
# Shell (interactive mode)
# ============================================================
def shell_mode():
    print("MCP shell - type 'help' for available tools, 'exit' to quit")
    use_daemon = daemon_is_running()
    if use_daemon:
        print("(using daemon)")
    else:
        print("(direct mode - daemon not running)")
        client = DirectClient()
        if not client.connect():
            print("error: failed to connect", file=sys.stderr)
            return

    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not cmd:
            continue
        if cmd == "exit":
            break
        if cmd == "help":
            _print_help()
            continue

        parts = cmd.split(maxsplit=2)
        tool = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        extra = parts[2] if len(parts) > 2 else ""

        args = _parse_args(tool, rest, extra)
        if args is None:
            continue

        if use_daemon:
            result = call_via_daemon(tool, args)
        else:
            result = client.call_tool(tool, args)

        if result:
            print(result)


def _parse_args(tool, first, second):
    if tool == "run_command":
        return {"command": first} if first else _usage(tool)
    elif tool == "read_file":
        return {"path": first} if first else _usage(tool)
    elif tool == "write_file":
        if not first or not second:
            return _usage("write_file <path> <content>")
        return {"path": first, "content": second}
    elif tool == "list_directory":
        return {"path": first or "."}
    elif tool == "system_info":
        return {}
    else:
        print(f"unknown tool: {tool}", file=sys.stderr)
        return None


def _usage(msg):
    print(f"usage: {msg}", file=sys.stderr)
    return None


def _print_help():
    print("Available tools:")
    for name, info in TOOLS.items():
        args_str = " ".join(info["args"])
        print(f"  {name} {args_str}".ljust(36) + info["desc"])
    print(f"  {'shell':36} enter interactive mode")
    print(f"\nexample: python3 mcp_client.py run_command 'ls -la /workspace'")


# ============================================================
# CLI dispatcher
# ============================================================
def main():
    if len(sys.argv) < 2:
        _print_help()
        sys.exit(1)

    action = sys.argv[1]

    if action == "shell":
        shell_mode()
        return

    if action not in TOOLS:
        print(f"unknown action: {action}", file=sys.stderr)
        _print_help()
        sys.exit(1)

    # Build args dict
    if action == "run_command":
        if len(sys.argv) < 3:
            _usage("run_command <command>")
            sys.exit(1)
        args = {"command": sys.argv[2]}
    elif action == "read_file":
        if len(sys.argv) < 3:
            _usage("read_file <path>")
            sys.exit(1)
        args = {"path": sys.argv[2]}
    elif action == "write_file":
        if len(sys.argv) < 4:
            _usage("write_file <path> <content>")
            sys.exit(1)
        args = {"path": sys.argv[2], "content": sys.argv[3]}
    elif action == "list_directory":
        args = {"path": sys.argv[2] if len(sys.argv) > 2 else "."}
    elif action == "system_info":
        args = {}
    else:
        args = {}

    # Try daemon first, fall back to direct
    result = None
    if daemon_is_running():
        try:
            result = call_via_daemon(action, args)
        except (ConnectionError, TimeoutError, OSError) as e:
            print(f"(daemon unavailable: {e}, falling back to direct)", file=sys.stderr)

    if result is None:
        client = DirectClient()
        if not client.connect():
            print("error: failed to connect", file=sys.stderr)
            sys.exit(1)
        result = client.call_tool(action, args)

    if result:
        print(result)


if __name__ == "__main__":
    main()
