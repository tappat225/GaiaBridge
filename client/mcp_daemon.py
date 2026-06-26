#!/usr/bin/env python3
"""
MCP Daemon — maintains a persistent MCP session to the remote server.

The daemon listens on a local Unix socket. CLI clients send JSON requests
to this socket and receive results instantly, without paying the cost of
TLS + MCP handshake on every invocation.

Usage:
    python3 mcp_daemon.py                # run in foreground
    python3 mcp_daemon.py --daemonize    # fork to background
    python3 mcp_daemon.py --stop         # stop a running daemon
"""

import json
import os
import sys
import time
import ssl
import signal
import socket
import argparse
import urllib.request
import urllib.error
import threading

# ============================================================
# Configuration (set via environment variables)
# ============================================================
MCP_URL = os.environ.get("MCP_URL", "https://<your-domain>/_mcp")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "<your-bearer-token>")
SOCKET_PATH = os.environ.get("MCP_SOCKET_PATH", "/tmp/mcp-daemon.sock")
PID_FILE = os.environ.get("MCP_PID_FILE", "/tmp/mcp-daemon.pid")
KEEPALIVE_INTERVAL = 180  # seconds between keep-alive pings
MAX_RECONNECT_DELAY = 60  # max seconds to wait before reconnect


# ============================================================
# MCP Session (managed persistent connection)
# ============================================================
class McpSession:
    def __init__(self, url=MCP_URL, token=AUTH_TOKEN):
        self.url = url
        self.token = token
        self.session_id = None
        self._req_id = 0
        self._lock = threading.Lock()

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
            raise ConnectionError(f"HTTP {e.code}: {body}")
        except Exception as e:
            raise ConnectionError(str(e))

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
        with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-daemon", "version": "1.0"},
                },
                "id": self._next_id(),
            }
            result = self._post(payload)
            self._post({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            })
            server = result.get("result", {}).get("serverInfo", {})
            print(f"daemon: connected to {server.get('name', 'server')} "
                  f"v{server.get('version', '?')} "
                  f"(session: {self.session_id[:8]}...)")
            return True

    def call_tool(self, name, arguments):
        with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
                "id": self._next_id(),
            }
            result = self._post(payload)
            if result is None:
                return {"error": "no response from server"}
            if "error" in result:
                return {"error": result["error"].get("message", str(result["error"]))}
            content = result.get("result", {}).get("content", [])
            if content and len(content) > 0:
                return {"result": content[0].get("text", str(content))}
            return {"result": str(result)}

    def ping(self):
        try:
            self.call_tool("system_info", {})
            return True
        except Exception:
            return False

    def close(self):
        self.session_id = None
        self._req_id = 0


# ============================================================
# Local Unix Socket Server
# ============================================================
class LocalServer:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.sock = None
        self.running = False

    def start(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        self.sock.listen(16)
        self.sock.settimeout(1.0)
        self.running = True

    def accept(self):
        try:
            conn, _ = self.sock.accept()
            return conn
        except socket.timeout:
            return None

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)


def handle_client(conn, session):
    """Process a single CLI request."""
    try:
        conn.settimeout(10)
        raw = b""
        while True:
            try:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                raw += chunk
                if b"\n" in chunk:
                    break
            except socket.timeout:
                break

        if not raw.strip():
            conn.sendall(json.dumps({"error": "empty request"}).encode() + b"\n")
            return

        request = json.loads(raw.decode("utf-8"))
        tool = request.get("tool", "")
        args = request.get("args", {})

        if not tool:
            conn.sendall(json.dumps({"error": "missing 'tool' field"}).encode() + b"\n")
            return

        result = session.call_tool(tool, args)
        conn.sendall(json.dumps(result).encode() + b"\n")
    except json.JSONDecodeError:
        conn.sendall(json.dumps({"error": "invalid JSON"}).encode() + b"\n")
    except Exception as e:
        conn.sendall(json.dumps({"error": str(e)}).encode() + b"\n")
    finally:
        conn.close()


# ============================================================
# Daemon lifecycle
# ============================================================
def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    if os.path.exists(PID_FILE):
        os.unlink(PID_FILE)


def daemonize():
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    os.setsid()
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    os.chdir("/")
    os.umask(0)
    # Redirect stdio
    for fd in (0, 1, 2):
        try:
            os.close(fd)
        except OSError:
            pass
    os.open("/dev/null", os.O_RDWR)
    os.dup2(0, 1)
    os.dup2(0, 2)


def stop_daemon():
    if not os.path.exists(PID_FILE):
        print("daemon is not running (no pid file)")
        return
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"daemon (pid={pid}) stopped")
    except ProcessLookupError:
        print("daemon is not running (stale pid file)")
    remove_pid()


def run_foreground():
    write_pid()

    local = LocalServer(SOCKET_PATH)
    local.start()
    print(f"daemon: listening on {SOCKET_PATH}")

    session = McpSession()
    reconnect_delay = 1
    last_keepalive = 0

    def ensure_connected():
        nonlocal reconnect_delay, last_keepalive
        while local.running:
            try:
                session.close()
                session.connect()
                reconnect_delay = 1
                last_keepalive = time.time()
                print("daemon: session ready")
                return True
            except Exception as e:
                print(f"daemon: connect failed ({e}), retrying in {reconnect_delay}s...")
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)

    if not ensure_connected():
        return

    def cleanup():
        local.stop()
        session.close()
        remove_pid()

    signal.signal(signal.SIGTERM, lambda *_: cleanup() or sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: cleanup() or sys.exit(0))

    while local.running:
        # Accept and handle client requests
        conn = local.accept()
        if conn:
            t = threading.Thread(target=handle_client, args=(conn, session), daemon=True)
            t.start()

        # Keep-alive
        if time.time() - last_keepalive > KEEPALIVE_INTERVAL:
            try:
                if session.ping():
                    last_keepalive = time.time()
                else:
                    print("daemon: session expired, reconnecting...")
                    if not ensure_connected():
                        break
            except Exception:
                print("daemon: keepalive failed, reconnecting...")
                if not ensure_connected():
                    break

        # Check for stale pid removal requests
        if not os.path.exists(SOCKET_PATH):
            time.sleep(0.1)

    cleanup()


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Daemon")
    parser.add_argument("--daemonize", action="store_true", help="run in background")
    parser.add_argument("--stop", action="store_true", help="stop running daemon")
    args = parser.parse_args()

    if args.stop:
        stop_daemon()
        sys.exit(0)

    if args.daemonize:
        daemonize()

    run_foreground()
