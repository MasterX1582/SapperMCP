"""linuxmcpd - supervisor daemon for LinuxMCP.

Runs a unix-domain-socket control service (no network exposure) that starts
and stops the MCP HTTP server as a child process. Controlled by linuxmcp-gui
or linuxmcpctl.

The daemon itself does nothing heavy: it only brokers the MCP server
lifecycle and buffers the child's log lines.
"""

from __future__ import annotations

import getpass
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

from . import __version__
from .control import (LOG_PATH, STATE_DIR, daemon_running, host_for,
                      load_config, save_config, socket_path)
from .util import run_proc

MAX_LOG_LINES = 2000
_MASK = "***"
# SapperMCP: own sudoers file so a stock LinuxMCP install's sudo toggle
# can't remove ours (and vice versa).
SUDOERS_FILE = "/etc/sudoers.d/99-sappermcp"


class LinuxMcpDaemon:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.child: Optional[subprocess.Popen] = None
        self._buf: deque[tuple[int, str]] = deque(maxlen=MAX_LOG_LINES)
        self._seq = 0
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._sock_path = socket_path()
        self._server_sock: Optional[socket.socket] = None
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    # ----- logging -----

    def log(self, line: str) -> None:
        line = line.rstrip("\n")
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {line}"
        with self._lock:
            self._seq += 1
            self._buf.append((self._seq, entry))
        try:
            with open(LOG_PATH, "a") as f:
                f.write(entry + "\n")
        except OSError:
            pass
        print(entry, file=sys.stderr, flush=True)

    # ----- MCP server child process -----

    @property
    def server_running(self) -> bool:
        return self.child is not None and self.child.poll() is None

    def _child_argv(self) -> list[str]:
        cfg = self.cfg
        # SapperMCP: the daemon supervises the merged server (all 127 tools;
        # the linuxmcp-only variant is `python -m linuxmcp`).
        argv = [sys.executable, "-m", "sappermcp", "--http",
                "--host", host_for(cfg), "--port", str(cfg["port"])]
        if cfg.get("auth_token"):
            argv += ["--auth-token", str(cfg["auth_token"])]
        return argv

    def _pkg_parent(self) -> str:
        return str(Path(__file__).resolve().parent.parent)

    def _child_env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Replace (don't extend) PYTHONPATH: an inherited dev checkout can
        # otherwise shadow the installed package with stale code. cwd is
        # also set to the package parent in start_server for the same
        # reason (sys.path[0] of `python -m` is the cwd).
        env["PYTHONPATH"] = self._pkg_parent()
        return env

    def start_server(self) -> dict[str, Any]:
        if self.server_running:
            return {"ok": True, "already_running": True,
                    "pid": self.child.pid}
        argv = self._child_argv()
        try:
            self.child = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=self._child_env(),
                cwd=self._pkg_parent(),
                start_new_session=True,
                text=True,
            )
        except Exception as e:
            self.log(f"failed to start server: {e}")
            return {"ok": False, "error": str(e)}
        threading.Thread(target=self._pump_stderr,
                         args=(self.child,), daemon=True).start()
        self.log(f"MCP server started (pid {self.child.pid}) on "
                 f"{host_for(self.cfg)}:{self.cfg['port']}"
                 f"{' remote' if self.cfg['remote'] else ' local-only'}"
                 f"{' +auth' if self.cfg.get('auth_token') else ''}")
        return {"ok": True, "pid": self.child.pid}

    def _pump_stderr(self, child: subprocess.Popen) -> None:
        try:
            for line in child.stderr or []:
                self.log(f"srv| {line}")
        except (ValueError, OSError):
            pass
        code = child.wait()
        if child is self.child:
            self.log(f"MCP server exited (code {code})")

    def stop_server(self) -> dict[str, Any]:
        child = self.child
        if child is None or child.poll() is not None:
            self.child = None
            return {"ok": True, "already_stopped": True}
        self.log(f"stopping MCP server (pid {child.pid})")
        try:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        except (ProcessLookupError, PermissionError) as e:
            self.log(f"stop error: {e}")
        self.child = None
        return {"ok": True}

    def restart_server(self) -> dict[str, Any]:
        self.stop_server()
        return self.start_server()

    # ----- sudo management ------

    def _passwordless_sudo(self) -> bool:
        """True when `sudo -n` works for this user (NOPASSWD granted)."""
        r = run_proc(["sudo", "-n", "true"], timeout=5)
        return r["ok"]

    def _set_passwordless_sudo(self, enable: bool) -> tuple[bool, str]:
        """Create/remove the sudoers drop-in for this daemon's user.

        Uses `sudo -n` when already privileged, else `pkexec` which pops a
        polkit auth dialog on the desktop (that's the grant moment).
        """
        user = getpass.getuser()
        if enable:
            if self._passwordless_sudo():
                return True, "already enabled"
            line = f"{user} ALL=(ALL:ALL) NOPASSWD: ALL"
            script = (
                f"echo {shlex.quote(line)} > /tmp/lmcp.sudoers && "
                f"visudo -cf /tmp/lmcp.sudoers >/dev/null 2>&1 && "
                f"install -m 440 /tmp/lmcp.sudoers {SUDOERS_FILE} && "
                f"rm -f /tmp/lmcp.sudoers")
        else:
            if not os.path.exists(SUDOERS_FILE):
                return True, "already disabled"
            script = f"rm -f {SUDOERS_FILE}"

        r = run_proc(["sudo", "-n", "sh", "-c", script], timeout=10)
        if r["ok"]:
            return True, ""
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return False, ("root required; no pkexec and sudo -n failed. "
                           f"Run as root: sh -c {shlex.quote(script)}")
        r = run_proc([pkexec, "sh", "-c", script], timeout=120)
        if not r["ok"]:
            return False, (r["stderr"].strip() or
                           "pkexec failed or authentication was cancelled")
        if enable and not self._passwordless_sudo():
            return False, "sudoers file written but sudo -n still fails"
        return True, ""

    # ----- status / config -----

    def status(self) -> dict[str, Any]:
        cfg = dict(self.cfg)
        cfg["auth_token"] = _MASK if cfg.get("auth_token") else None
        return {
            "ok": True,
            "daemon_pid": os.getpid(),
            "version": __version__,
            "passwordless_sudo": self._passwordless_sudo(),
            "server": {
                "running": self.server_running,
                "pid": self.child.pid if self.server_running else None,
                "exit_code": (self.child.poll() if self.child else None),
                "url": f"http://{host_for(self.cfg)}:{self.cfg['port']}/mcp",
                "remote_enabled": bool(self.cfg["remote"]),
                "auth_required": bool(self.cfg.get("auth_token")),
            },
            "config": cfg,
            "config_path": str(self._config_path()),
        }

    def _config_path(self):
        from .control import CONFIG_PATH
        return CONFIG_PATH

    def set_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        cfg = self.cfg
        restart_needed = False
        if "port" in updates:
            port = int(updates["port"])
            if not (1 <= port <= 65535):
                return {"ok": False, "error": f"Invalid port {port}"}
            if port != cfg["port"]:
                cfg["port"] = port
                restart_needed = True
        if "remote" in updates:
            remote = bool(updates["remote"])
            if remote != cfg["remote"]:
                cfg["remote"] = remote
                restart_needed = True
        if "auth_token" in updates:
            tok = updates["auth_token"]
            if tok == _MASK:
                pass  # keep existing
            elif tok in (None, ""):
                if cfg.get("auth_token"):
                    cfg["auth_token"] = None
                    restart_needed = True
            elif tok != cfg.get("auth_token"):
                cfg["auth_token"] = str(tok)
                restart_needed = True
        if "autostart_server" in updates:
            cfg["autostart_server"] = bool(updates["autostart_server"])
        if "passwordless_sudo" in updates:
            want = bool(updates["passwordless_sudo"])
            ok, err = self._set_passwordless_sudo(want)
            if not ok:
                return {"ok": False, "error": err}
            self.log(f"passwordless sudo {'enabled' if want else 'disabled'}"
                     + (f" ({err})" if err else ""))
        save_config(cfg)
        self.log(f"config updated: port={cfg['port']} remote={cfg['remote']} "
                 f"auth={'set' if cfg['auth_token'] else 'none'} "
                 f"autostart={cfg['autostart_server']}")
        if restart_needed and self.server_running:
            self.log("restarting server to apply config")
            self.restart_server()
        return {"ok": True, **self.status()}

    # ----- command dispatch -----

    def dispatch(self, cmd: dict[str, Any]) -> dict[str, Any]:
        name = cmd.get("cmd")
        if name == "status":
            return self.status()
        if name in ("start_server", "stop_server", "restart_server"):
            action = getattr(self, name)
            r = action()
            st = self.status()
            st.update(r)  # action result fields win (ok/error/pid)
            return st
        if name == "get_config":
            return self.status()
        if name == "set_config":
            return self.set_config(cmd.get("config") or {})
        if name == "logs":
            since = int(cmd.get("since") or 0)
            with self._lock:
                lines = [(s, l) for s, l in self._buf if s > since]
                nxt = self._seq
            return {"ok": True, "next": nxt,
                    "lines": [l for _, l in lines]}
        if name == "shutdown":
            threading.Thread(target=self._shutdown_soon,
                             daemon=True).start()
            return {"ok": True, "note": "daemon shutting down"}
        return {"ok": False, "error": f"Unknown command: {name}"}

    def _shutdown_soon(self) -> None:
        time.sleep(0.3)  # let the reply flush
        self.stop_server()
        self._shutdown.set()

    # ----- socket loop -----

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            data = b""
            while b"\n" not in data and len(data) < 65536:
                chunk = conn.recv(8192)
                if not chunk:
                    break
                data += chunk
            request = json.loads(data.split(b"\n")[0].decode() or "{}")
            reply = self.dispatch(request)
        except Exception as e:
            reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            conn.sendall(json.dumps(reply).encode() + b"\n")
        except OSError:
            pass
        finally:
            conn.close()

    def serve(self) -> int:
        if daemon_running():
            print("linuxmcpd already running", file=sys.stderr)
            return 1
        path = self._sock_path
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        os.makedirs(os.path.dirname(path) or "/tmp", exist_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(path)
        os.chmod(path, 0o600)
        sock.listen(16)
        sock.settimeout(0.5)
        self._server_sock = sock

        def _term(*_a):
            self._shutdown.set()
        signal.signal(signal.SIGTERM, _term)
        signal.signal(signal.SIGINT, _term)

        self.log(f"linuxmcpd {__version__} listening on {path}")
        if self.cfg.get("autostart_server"):
            self.start_server()

        try:
            while not self._shutdown.is_set():
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle_conn, args=(conn,),
                                 daemon=True).start()
        finally:
            self.stop_server()
            sock.close()
            try:
                os.unlink(path)
            except OSError:
                pass
            self.log("linuxmcpd stopped")
        return 0


def main() -> None:
    sys.exit(LinuxMcpDaemon().serve())


if __name__ == "__main__":
    main()
