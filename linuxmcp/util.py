"""Shared helpers for LinuxMCP core modules and tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Optional

MAX_OUTPUT_CHARS = 100_000


def which(name: str) -> Optional[str]:
    """Return the absolute path of an executable, or None."""
    return shutil.which(name)


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    """Truncate text to limit characters. Returns (text, was_truncated)."""
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]", True


def json_out(payload: Any) -> str:
    """Serialize a result payload to a JSON string for tool responses."""
    return json.dumps(payload, indent=2, default=str)


def ok(**fields: Any) -> str:
    return json_out({"ok": True, **fields})


def err(message: str, **fields: Any) -> str:
    return json_out({"ok": False, "error": message, **fields})


def sudo_prefix() -> tuple[list[str], Optional[str]]:
    """Return (argv_prefix, stdin_password_or_None) for running a command as root.

    If LINUXMCP_SUDO_PASSWORD is set, uses `sudo -S` and feeds the password on
    stdin. Otherwise uses `sudo -n` which requires passwordless sudo.
    """
    password = os.environ.get("LINUXMCP_SUDO_PASSWORD")
    if password is not None:
        return ["sudo", "-S", "-p", ""], password + "\n"
    return ["sudo", "-n"], None


def run_proc(
    argv: list[str],
    timeout: float = 60.0,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    input_text: Optional[str] = None,
    sudo: bool = False,
) -> dict[str, Any]:
    """Run a subprocess and return a result dict.

    Never raises for command-level failures; returns ok=False with details.
    Raises only for programming errors (bad argv type etc.).
    """
    if sudo:
        prefix, pw = sudo_prefix()
        argv = prefix + argv
        if pw is not None:
            input_text = pw if input_text is None else pw + input_text
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=merged_env,
            input=input_text,
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace")
        errout = e.stderr if isinstance(e.stderr, str) else (e.stderr or b"").decode(errors="replace")
        return {
            "ok": False,
            "timed_out": True,
            "timeout": timeout,
            "exit_code": None,
            "stdout": out,
            "stderr": errout,
            "error": f"Command timed out after {timeout}s",
        }
    except FileNotFoundError as e:
        return {
            "ok": False,
            "timed_out": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": f"Executable not found: {e.filename}",
        }
    except Exception as e:  # PermissionError, OSError, ...
        return {
            "ok": False,
            "timed_out": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": f"{type(e).__name__}: {e}",
        }

    stdout, out_trunc = truncate(proc.stdout or "")
    stderr, err_trunc = truncate(proc.stderr or "")
    return {
        "ok": proc.returncode == 0,
        "timed_out": False,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": out_trunc,
        "stderr_truncated": err_trunc,
    }
