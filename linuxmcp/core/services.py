"""systemd services, journald logs, and classic log-file helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

from ..util import run_proc, truncate, which


def _systemd_available() -> bool:
    return which("systemctl") is not None and os.path.isdir("/run/systemd/system")


def _unit(name: str) -> str:
    """Normalize a unit name (append .service if no suffix given)."""
    return name if "." in name.rsplit("/", 1)[-1] else name + ".service"


def list_services(
    state: Optional[str] = None,
    pattern: Optional[str] = None,
    user: bool = False,
    limit: int = 300,
) -> dict[str, Any]:
    """List systemd units. state e.g. 'running','failed','active'."""
    if not _systemd_available():
        return {"ok": False, "error": "systemd not available on this system"}
    argv = ["systemctl", "list-units", "--type=service", "--all",
            "--no-pager", "--no-legend", "--plain"]
    if user:
        argv.insert(1, "--user")
    if state:
        argv += ["--state", state]
    if pattern:
        argv.append(pattern)
    r = run_proc(argv, timeout=20)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"]}
    units = []
    for line in r["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 4:
            units.append({
                "unit": parts[0], "load": parts[1], "active": parts[2],
                "sub": parts[3],
                "description": " ".join(parts[4:]) if len(parts) > 4 else "",
            })
    return {"ok": True, "count": len(units[:limit]), "total": len(units),
            "services": units[:limit]}


def get_service_status(name: str, user: bool = False) -> dict[str, Any]:
    if not _systemd_available():
        return {"ok": False, "error": "systemd not available on this system"}
    unit = _unit(name)
    argv = ["systemctl"]
    if user:
        argv.append("--user")
    argv += ["status", unit, "--no-pager", "--lines", "15"]
    r = run_proc(argv, timeout=15)
    # status exits non-zero for inactive/failed units; still useful output
    props = {}
    for key in ("Id", "LoadState", "ActiveState", "SubState",
                "MainPID", "ExecMainStatus", "MemoryCurrent", "UnitFileState"):
        pr = run_proc(["systemctl"] + (["--user"] if user else []) +
                      ["show", unit, "-p", key, "--value"], timeout=10)
        if pr["ok"]:
            props[key.lower()] = pr["stdout"].strip()
    return {"ok": True, "unit": unit,
            "running": props.get("activestate") == "active",
            "properties": props, "status_text": r["stdout"],
            "status_exit_code": r["exit_code"]}


def service_action(action: str, name: str, user: bool = False,
                   sudo: bool = True) -> dict[str, Any]:
    """start|stop|restart|reload|enable|disable|mask|unmask a unit."""
    allowed = {"start", "stop", "restart", "reload", "enable", "disable",
               "mask", "unmask", "reload-or-restart", "try-restart"}
    if action not in allowed:
        return {"ok": False, "error": f"Invalid action '{action}'",
                "allowed": sorted(allowed)}
    if not _systemd_available():
        return {"ok": False, "error": "systemd not available on this system"}
    unit = _unit(name)
    argv = ["systemctl"]
    if user:
        argv.append("--user")
        sudo = False
    argv += [action, unit]
    r = run_proc(argv, timeout=60, sudo=sudo)
    return {"ok": r["ok"], "unit": unit, "action": action,
            "stdout": r["stdout"], "stderr": r["stderr"],
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def get_service_logs(
    name: str,
    lines: int = 100,
    since: Optional[str] = None,
    priority: Optional[str] = None,
    user: bool = False,
) -> dict[str, Any]:
    return read_journal(unit=_unit(name), lines=lines, since=since,
                        priority=priority, user=user)


def read_journal(
    unit: Optional[str] = None,
    lines: int = 100,
    since: Optional[str] = None,
    priority: Optional[str] = None,
    grep: Optional[str] = None,
    identifier: Optional[str] = None,
    user: bool = False,
    reverse: bool = False,
    sudo: bool = False,
) -> dict[str, Any]:
    """Query journalctl. priority: emerg..debug. since: '1 hour ago', 'today',
    '2024-01-01 10:00'. grep: -g regex pattern."""
    if which("journalctl") is None:
        return {"ok": False, "error": "journalctl not available"}
    argv = ["journalctl", "--no-pager", "-o", "short-iso",
            "-n", str(lines)]
    if user:
        argv.append("--user")
    if unit:
        argv += ["-u", unit]
    if identifier:
        argv += ["-t", identifier]
    if since:
        argv += ["--since", since]
    if priority:
        argv += ["-p", priority]
    if grep:
        argv += ["-g", grep]
    if reverse:
        argv.append("-r")
    r = run_proc(argv, timeout=30, sudo=sudo)
    if not r["ok"] and "Permission denied" in (r["stderr"] or ""):
        r = run_proc(argv, timeout=30, sudo=True)
    out, truncated = truncate(r["stdout"])
    return {"ok": r["ok"], "lines_requested": lines,
            "log": out, "truncated": truncated,
            "stderr": r["stderr"] or None,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def read_log_file(
    path: str,
    lines: int = 100,
    offset: int = 0,
    tail: bool = True,
) -> dict[str, Any]:
    """Read a log file. tail=True returns the last `lines` lines; tail=False
    returns `lines` lines starting at `offset` (0-based)."""
    path = os.path.expanduser(path)
    try:
        with open(path, "r", errors="replace") as f:
            all_lines = f.readlines()
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    total = len(all_lines)
    if tail:
        sliced = all_lines[-lines:] if lines else all_lines
        start = total - len(sliced)
    else:
        sliced = all_lines[offset:offset + lines]
        start = offset
    content, truncated = truncate("".join(sliced))
    return {"ok": True, "path": path, "total_lines": total,
            "start_line": start, "lines_returned": len(sliced),
            "content": content, "truncated": truncated}


def list_log_files(directory: str = "/var/log",
                   pattern: Optional[str] = None,
                   max_entries: int = 300) -> dict[str, Any]:
    """List log files under a directory (default /var/log), sorted by mtime."""
    import fnmatch
    directory = os.path.expanduser(directory)
    entries = []
    try:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
            for name in files:
                if pattern and not fnmatch.fnmatch(name, pattern):
                    continue
                full = os.path.join(root, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                entries.append({"path": full, "size": st.st_size,
                                "modified": st.st_mtime})
            if len(entries) >= max_entries:
                break
    except OSError as e:
        return {"ok": False, "error": str(e)}
    entries.sort(key=lambda e: e["modified"], reverse=True)
    return {"ok": True, "directory": directory,
            "count": len(entries[:max_entries]),
            "files": entries[:max_entries]}
