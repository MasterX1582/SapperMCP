"""Shared control-plane for linuxmcpd: config paths, socket protocol, client.

Stdlib only - the GUI and CLI must not need fastmcp to talk to the daemon.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any, Optional

DEFAULT_PORT = 3940  # SapperMCP merged-server default (linuxmcp uses 3939)

DEFAULT_CONFIG: dict[str, Any] = {
    "port": DEFAULT_PORT,
    "remote": False,          # False = bind 127.0.0.1, True = bind 0.0.0.0
    "auth_token": None,       # Bearer token or None
    "autostart_server": False,  # start MCP server when daemon starts
}

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME",
                                 Path.home() / ".config")) / "linuxmcp"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME",
                                Path.home() / ".local" / "state")) / "linuxmcp"
LOG_PATH = STATE_DIR / "daemon.log"


def socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return os.path.join(runtime, "linuxmcp.sock")
    return f"/tmp/linuxmcp-{os.getuid()}.sock"


def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    try:
        os.chmod(CONFIG_PATH, 0o600)  # may hold auth token
    except OSError:
        pass


def host_for(cfg: dict[str, Any]) -> str:
    return "0.0.0.0" if cfg.get("remote") else "127.0.0.1"


def send_command(cmd: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    """Send one command to the daemon; returns its reply dict.

    Raises ConnectionError/OSError if the daemon is unreachable.
    """
    path = socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
        sock.sendall(json.dumps(cmd).encode() + b"\n")
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
            if b"\n" in data:
                break
    finally:
        sock.close()
    raw = b"".join(chunks).split(b"\n")[0]
    if not raw:
        return {"ok": False, "error": "Empty reply from daemon"}
    return json.loads(raw.decode())


def daemon_running() -> bool:
    try:
        r = send_command({"cmd": "status"}, timeout=2.0)
        return bool(r.get("ok"))
    except (OSError, ConnectionError):
        return False
