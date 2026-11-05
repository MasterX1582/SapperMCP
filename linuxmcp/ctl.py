"""linuxmcpctl - command-line control for linuxmcpd.

Usage:
    linuxmcpctl status
    linuxmcpctl start | stop | restart
    linuxmcpctl set port 8080 | remote on|off | token <tok>|none |
                      autostart on|off | sudo on|off
    linuxmcpctl logs [since_seq]
    linuxmcpctl daemon-start          # spawn daemon detached
    linuxmcpctl shutdown              # stop server + exit daemon

    'set sudo on' installs a NOPASSWD sudoers rule for this user (one
    polkit auth prompt); 'set sudo off' removes it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from .control import (LOG_PATH, daemon_running, send_command)


def ensure_daemon() -> None:
    """Spawn the daemon detached if it isn't running."""
    if daemon_running():
        return
    env = os.environ.copy()
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = (pkg_parent + os.pathsep +
                       env.get("PYTHONPATH", ""))
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "ab")
    subprocess.Popen(
        [sys.executable, "-m", "linuxmcp.daemon"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        env=env, start_new_session=True,
    )
    import time
    for _ in range(50):
        if daemon_running():
            return
        time.sleep(0.1)
    raise SystemExit("daemon failed to start; check " + str(LOG_PATH))


def _print(reply: dict[str, Any]) -> None:
    print(json.dumps(reply, indent=2, default=str))


def _onoff(v: str) -> Optional[bool]:
    v = v.lower()
    if v in ("on", "true", "1", "yes", "enable", "enabled"):
        return True
    if v in ("off", "false", "0", "no", "disable", "disabled"):
        return False
    return None


USAGE = __doc__


def main(argv: Optional[list[str]] = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return
    cmd = args[0]

    if cmd == "daemon-start":
        ensure_daemon()
        print("daemon running")
        return

    if not daemon_running():
        raise SystemExit(
            "linuxmcpd is not running (start it with 'linuxmcpctl "
            "daemon-start', linuxmcp-gui, or a systemd unit)")

    if cmd == "status":
        _print(send_command({"cmd": "status"}))
    elif cmd in ("start", "stop", "restart"):
        _print(send_command({"cmd": f"{cmd}_server"}))
    elif cmd == "logs":
        since = int(args[1]) if len(args) > 1 else 0
        r = send_command({"cmd": "logs", "since": since})
        for line in r.get("lines", []):
            print(line)
        if not r.get("ok"):
            _print(r)
    elif cmd == "shutdown":
        _print(send_command({"cmd": "shutdown"}))
    elif cmd == "set" and len(args) >= 3:
        key, value = args[1], " ".join(args[2:])
        updates: dict[str, Any] = {}
        if key == "port":
            updates["port"] = int(value)
        elif key == "remote":
            b = _onoff(value)
            if b is None:
                raise SystemExit("remote expects on/off")
            updates["remote"] = b
        elif key in ("token", "auth_token"):
            updates["auth_token"] = None if value.lower() in ("none", "off", "") else value
        elif key in ("autostart", "autostart_server"):
            b = _onoff(value)
            if b is None:
                raise SystemExit("autostart expects on/off")
            updates["autostart_server"] = b
        elif key in ("sudo", "passwordless", "passwordless_sudo"):
            b = _onoff(value)
            if b is None:
                raise SystemExit("sudo expects on/off")
            updates["passwordless_sudo"] = b
        else:
            raise SystemExit(f"unknown setting '{key}' "
                             "(port|remote|token|autostart)")
        _print(send_command({"cmd": "set_config", "config": updates}))
    elif cmd == "get-config":
        _print(send_command({"cmd": "get_config"}))
    else:
        print(USAGE)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
