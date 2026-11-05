"""Process inspection and control, built on psutil."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any, Optional

import psutil


def _proc_summary(p: psutil.Process, attrs: dict) -> dict[str, Any]:
    return {
        "pid": p.pid,
        "name": attrs.get("name"),
        "exe": attrs.get("exe"),
        "cmdline": attrs.get("cmdline"),
        "username": attrs.get("username"),
        "status": attrs.get("status"),
        "cpu_percent": attrs.get("cpu_percent"),
        "memory_percent": round(attrs.get("memory_percent") or 0.0, 2),
        "memory_rss": (attrs.get("memory_info") or [0])[0]
        if attrs.get("memory_info") else None,
        "created": attrs.get("create_time"),
        "ppid": attrs.get("ppid"),
    }


def list_processes(
    name_filter: Optional[str] = None,
    username: Optional[str] = None,
    sort_by: str = "cpu",
    limit: int = 200,
) -> dict[str, Any]:
    """List processes. sort_by: cpu|mem|pid|name."""
    attrs = ["name", "exe", "cmdline", "username", "status", "cpu_percent",
             "memory_percent", "memory_info", "create_time", "ppid"]
    procs: list[dict[str, Any]] = []
    for p in psutil.process_iter(attrs=attrs, ad_value=None):
        info = _proc_summary(p, p.info)
        if name_filter and name_filter.lower() not in (info["name"] or "").lower() \
                and not any(name_filter.lower() in (a or "").lower()
                            for a in (info["cmdline"] or [])):
            continue
        if username and (info["username"] or "").split("\\")[-1] != username:
            continue
        procs.append(info)
    key = {
        "cpu": lambda x: x["cpu_percent"] or 0,
        "mem": lambda x: x["memory_percent"] or 0,
        "pid": lambda x: x["pid"],
        "name": lambda x: (x["name"] or "").lower(),
    }.get(sort_by, lambda x: x["cpu_percent"] or 0)
    procs.sort(key=key, reverse=sort_by in ("cpu", "mem", "pid"))
    return {"ok": True, "count": len(procs[:limit]), "total": len(procs),
            "processes": procs[:limit]}


def get_process_info(pid: int, include_env: bool = False) -> dict[str, Any]:
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return {"ok": False, "error": f"No process with pid {pid}"}
    try:
        with p.oneshot():
            info: dict[str, Any] = {
                "ok": True,
                "pid": pid,
                "name": p.name(),
                "exe": p.exe(),
                "cmdline": p.cmdline(),
                "cwd": _safe(p.cwd),
                "username": p.username(),
                "status": p.status(),
                "created": p.create_time(),
                "ppid": p.ppid(),
                "children": [c.pid for c in p.children()],
                "num_threads": p.num_threads(),
                "cpu_percent": p.cpu_percent(),
                "cpu_times": p.cpu_times()._asdict(),
                "memory_percent": round(p.memory_percent(), 2),
                "memory_info": p.memory_info()._asdict(),
                "nice": p.nice(),
                "open_files": [f.path for f in _safe(p.open_files) or []][:50],
                "connections": [
                    {"fd": c.fd, "type": str(c.type), "local": str(c.laddr),
                     "remote": str(c.raddr), "status": c.status}
                    for c in (_safe(p.net_connections) or [])[:50]
                ],
            }
            if include_env:
                info["environment"] = _safe(p.environ) or {}
            return info
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        return {"ok": False, "error": str(e), "pid": pid}


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def find_processes_by_name(name: str, exact: bool = False) -> dict[str, Any]:
    matches = []
    for p in psutil.process_iter(attrs=["name", "exe", "cmdline"], ad_value=None):
        pname = p.info.get("name") or ""
        hit = pname == name if exact else name.lower() in pname.lower()
        if not hit:
            hit = any(name.lower() in (a or "").lower()
                      for a in (p.info.get("cmdline") or []))
        if hit:
            matches.append({"pid": p.pid, "name": pname,
                            "exe": p.info.get("exe"),
                            "cmdline": p.info.get("cmdline")})
    return {"ok": True, "count": len(matches), "processes": matches}


def start_process(
    command: str,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    shell: bool = True,
) -> dict[str, Any]:
    """Start a detached background process. Use shell sessions for interaction."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.Popen(
            command if shell else command.split(),
            shell=shell,
            cwd=cwd,
            env=merged_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "command": command}
    return {"ok": True, "pid": proc.pid, "command": command}


def kill_process(pid: int, force: bool = False, timeout: float = 5.0) -> dict[str, Any]:
    """SIGTERM (or SIGKILL with force=True); after timeout escalates to SIGKILL."""
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return {"ok": False, "error": f"No process with pid {pid}"}
    try:
        p.kill() if force else p.terminate()
    except psutil.NoSuchProcess:
        return {"ok": True, "pid": pid, "note": "already exited"}
    except psutil.AccessDenied as e:
        return {"ok": False, "error": f"Access denied: {e}", "pid": pid}
    try:
        p.wait(timeout=timeout)
        return {"ok": True, "pid": pid, "forced": force}
    except psutil.TimeoutExpired:
        if not force:
            try:
                p.kill()
                p.wait(timeout=2)
                return {"ok": True, "pid": pid,
                        "note": "escalated to SIGKILL after timeout"}
            except Exception as e:
                return {"ok": False, "error": str(e), "pid": pid}
        return {"ok": False, "error": "Process did not exit", "pid": pid}


def kill_processes_by_name(name: str, exact: bool = False,
                           force: bool = False) -> dict[str, Any]:
    found = find_processes_by_name(name, exact=exact)
    results = []
    for m in found["processes"]:
        results.append({"pid": m["pid"], **kill_process(m["pid"], force=force)})
    killed = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "matched": len(results), "killed": killed,
            "results": results}


_SIGNAL_NAMES = {
    "TERM": signal.SIGTERM, "KILL": signal.SIGKILL, "INT": signal.SIGINT,
    "HUP": signal.SIGHUP, "QUIT": signal.SIGQUIT, "USR1": signal.SIGUSR1,
    "USR2": signal.SIGUSR2, "STOP": signal.SIGSTOP, "CONT": signal.SIGCONT,
    "ABRT": signal.SIGABRT, "SEGV": signal.SIGSEGV, "PIPE": signal.SIGPIPE,
    "ALRM": signal.SIGALRM, "CHLD": signal.SIGCHLD,
}


def send_signal(pid: int, signal_name: str) -> dict[str, Any]:
    name = signal_name.upper().removeprefix("SIG")
    sig = _SIGNAL_NAMES.get(name)
    if sig is None:
        try:
            sig = getattr(signal, "SIG" + name)
        except AttributeError:
            return {"ok": False, "error": f"Unknown signal: {signal_name}",
                    "known": sorted(_SIGNAL_NAMES)}
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return {"ok": False, "error": f"No process with pid {pid}"}
    except PermissionError as e:
        return {"ok": False, "error": str(e), "pid": pid}
    return {"ok": True, "pid": pid, "signal": "SIG" + name}


def wait_for_exit(pid: int, timeout: float = 30.0) -> dict[str, Any]:
    """Block until a process exits or timeout. Returns exit status if known."""
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return {"ok": True, "pid": pid, "exited": True, "exit_code": None}
    try:
        code = p.wait(timeout=timeout)
        return {"ok": True, "pid": pid, "exited": True, "exit_code": code}
    except psutil.TimeoutExpired:
        return {"ok": True, "pid": pid, "exited": False}


def process_tree(pid: int) -> dict[str, Any]:
    """Return the process plus its descendants."""
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return {"ok": False, "error": f"No process with pid {pid}"}
    nodes = []

    def _node(p: psutil.Process) -> dict[str, Any]:
        with p.oneshot():
            return {"pid": p.pid, "name": _safe(p.name),
                    "cmdline": _safe(p.cmdline), "status": _safe(p.status)}

    nodes.append(_node(root))
    for child in root.children(recursive=True):
        try:
            nodes.append(_node(child))
        except psutil.NoSuchProcess:
            continue
    return {"ok": True, "root": pid, "count": len(nodes), "processes": nodes}
