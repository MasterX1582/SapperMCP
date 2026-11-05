"""Shell command execution and interactive PTY sessions."""

from __future__ import annotations

import fcntl
import os
import pty
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from typing import Any, Optional

from ..util import run_proc, sudo_prefix, truncate

DEFAULT_SHELL = "/bin/bash"


def run_command(
    command: str,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout: float = 120.0,
    shell: str = DEFAULT_SHELL,
    login: bool = False,
    sudo: bool = False,
) -> dict[str, Any]:
    """Run a shell command synchronously, capturing stdout/stderr/exit code."""
    flag = "-lc" if login else "-c"
    result = run_proc([shell, flag, command], timeout=timeout, cwd=cwd, env=env, sudo=sudo)
    result["command"] = command
    return result


def run_argv(
    argv: list[str],
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout: float = 120.0,
    sudo: bool = False,
    input_text: Optional[str] = None,
) -> dict[str, Any]:
    """Run an argv list (no shell interpretation)."""
    return run_proc(argv, timeout=timeout, cwd=cwd, env=env, sudo=sudo, input_text=input_text)


class ShellSession:
    """A persistent pseudo-terminal session.

    Runs a shell (or arbitrary command) attached to a PTY so interactive
    programs (REPLs, gdb, top, ssh, password prompts) behave correctly.
    Output is buffered in a bounded deque; reads are incremental.
    """

    BUFFER_LIMIT = 512 * 1024  # bytes kept in memory

    def __init__(
        self,
        session_id: str,
        argv: list[str],
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ):
        self.id = session_id
        self.argv = argv
        self.created_at = time.time()
        self._lock = threading.Lock()
        self._buffer: deque[bytes] = deque()
        self._buffer_size = 0
        self._read_offset = 0  # bytes already returned to readers
        self._consumed_total = 0
        self._eof = False

        master_fd, slave_fd = pty.openpty()
        merged_env = os.environ.copy()
        merged_env.setdefault("TERM", "xterm-256color")
        if env:
            merged_env.update(env)
        self.process = subprocess.Popen(
            argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=merged_env,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)
        self.master_fd = master_fd
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()

    def _drain(self) -> None:
        while True:
            try:
                chunk = os.read(self.master_fd, 65536)
            except (BlockingIOError, InterruptedError):
                if self.process.poll() is not None:
                    break
                time.sleep(0.02)
                continue
            except OSError:
                break  # PTY closed
            if not chunk:
                break
            with self._lock:
                self._buffer.append(chunk)
                self._buffer_size += len(chunk)
                while self._buffer_size > self.BUFFER_LIMIT:
                    dropped = self._buffer.popleft()
                    self._buffer_size -= len(dropped)
                    self._consumed_total += len(dropped)
        self._eof = True
        try:
            os.close(self.master_fd)
        except OSError:
            pass

    @property
    def running(self) -> bool:
        return self.process.poll() is None

    @property
    def exit_code(self) -> Optional[int]:
        return self.process.poll()

    def _snapshot(self) -> tuple[bytes, int]:
        """Return (full buffer bytes, absolute offset of buffer start)."""
        with self._lock:
            return b"".join(self._buffer), self._consumed_total

    def read(self, all_output: bool = False) -> dict[str, Any]:
        data, base_offset = self._snapshot()
        dropped = max(0, base_offset - self._read_offset)
        if all_output:
            new = data
        else:
            abs_read = max(self._read_offset, base_offset)
            new = data[abs_read - base_offset:]
        self._read_offset = base_offset + len(data)
        text = new.decode(errors="replace")
        text, truncated = truncate(text)
        return {
            "session_id": self.id,
            "running": self.running,
            "exit_code": self.exit_code,
            "new_output": text,
            "output_truncated": truncated or dropped > 0,
        }

    def write(self, data: str) -> int:
        return os.write(self.master_fd, data.encode())

    def close(self) -> None:
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=3)
        except Exception:
            pass
        if self.running:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except Exception:
                pass


_sessions: dict[str, ShellSession] = {}
_sessions_lock = threading.Lock()


def start_session(
    command: Optional[str] = None,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    shell: str = DEFAULT_SHELL,
    sudo: bool = False,
) -> dict[str, Any]:
    """Start a persistent PTY session.

    With command=None an interactive shell is spawned. With a command,
    `shell -c <command>` runs inside the PTY (useful for apps you want to
    keep alive and interact with).
    """
    argv = [shell] if command is None else [shell, "-c", command]
    if sudo:
        prefix, pw = sudo_prefix()
        argv = prefix + argv
    session_id = "s" + uuid.uuid4().hex[:8]
    try:
        session = ShellSession(session_id, argv, cwd=cwd, env=env)
    except Exception as e:
        return {"ok": False, "error": f"Failed to start session: {e}"}
    if sudo and pw is not None:
        session.write(pw)
    with _sessions_lock:
        _sessions[session_id] = session
    time.sleep(0.15)  # let the prompt/first output arrive
    info = session.read()
    info.update({"ok": True, "command": command or shell, "pid": session.process.pid})
    return info


def get_session(session_id: str) -> Optional[ShellSession]:
    with _sessions_lock:
        return _sessions.get(session_id)


def list_sessions() -> list[dict[str, Any]]:
    with _sessions_lock:
        return [
            {
                "session_id": s.id,
                "command": " ".join(s.argv),
                "pid": s.process.pid,
                "running": s.running,
                "exit_code": s.exit_code,
                "created_at": s.created_at,
            }
            for s in _sessions.values()
        ]


def close_session(session_id: str) -> bool:
    with _sessions_lock:
        session = _sessions.pop(session_id, None)
    if session is None:
        return False
    session.close()
    return True
