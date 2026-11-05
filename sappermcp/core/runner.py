"""Run the bundled sapper CLI in a subprocess - synchronously or as a
background PTY session so long autonomous runs never block the MCP call."""

from __future__ import annotations

import shlex
import sys
from typing import Optional

from linuxmcp.util import run_proc

from ..paths import sapper_cli


def argv_for(args: list[str]) -> list[str]:
    return [sys.executable, str(sapper_cli()), *args]


def run_sapper(
    args: list[str],
    *,
    cwd: Optional[str] = None,
    timeout: float = 120.0,
    env: Optional[dict] = None,
) -> dict:
    """`python lib/sapper.py <args>` capturing stdout/stderr/exit code."""
    return run_proc(argv_for(args), timeout=timeout, cwd=cwd, env=env)


def run_sapper_background(args: list[str], *, cwd: Optional[str] = None) -> dict:
    """Launch `sapper <args>` inside a persistent PTY session (the vendored
    linuxmcp session manager) and return a session_id. Follow progress with
    read_session_output / write_to_session / close_shell_session."""
    from linuxmcp.core import shell as sh

    cmdline = " ".join(shlex.quote(a) for a in argv_for(args))
    return sh.start_session(command=cmdline, cwd=cwd)


def store_flag(store: Optional[str]) -> list[str]:
    return ["--store", store] if store else []
