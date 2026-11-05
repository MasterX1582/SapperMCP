"""System information: OS, CPU, memory, disk, network, environment."""

from __future__ import annotations

import os
import platform
import socket
import time
from datetime import datetime, timezone
from typing import Any, Optional

import psutil

from ..util import run_proc


def _os_release() -> dict[str, str]:
    info = {}
    try:
        info = platform.freedesktop_os_release()
    except Exception:
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        info[k] = v.strip('"')
        except OSError:
            pass
    return info


def get_system_info() -> dict[str, Any]:
    rel = _os_release()
    boot = psutil.boot_time()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu_freq = psutil.cpu_freq()
    info: dict[str, Any] = {
        "ok": True,
        "hostname": socket.gethostname(),
        "fqdn": socket.getfqdn(),
        "os": {
            "name": rel.get("PRETTY_NAME", platform.system()),
            "id": rel.get("ID"),
            "version": rel.get("VERSION"),
            "version_id": rel.get("VERSION_ID"),
            "kernel": platform.release(),
            "arch": platform.machine(),
        },
        "uptime_seconds": int(time.time() - boot),
        "boot_time": datetime.fromtimestamp(boot, tz=timezone.utc).isoformat(),
        "cpu": {
            "model": _cpu_model(),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "frequency_mhz": round(cpu_freq.current, 1) if cpu_freq else None,
            "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
            "usage_percent": psutil.cpu_percent(interval=0.2),
        },
        "memory": {
            "total": mem.total, "available": mem.available,
            "used": mem.used, "percent": mem.percent,
        },
        "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent},
        "users": [
            {"name": u.name, "terminal": u.terminal, "host": u.host,
             "started": u.started}
            for u in psutil.users()
        ],
        "python": platform.python_version(),
        "pid": os.getpid(),
        "current_user": _current_user(),
    }
    try:
        disk = psutil.disk_usage("/")
        info["root_disk"] = {"total": disk.total, "used": disk.used,
                             "free": disk.free, "percent": disk.percent}
    except Exception:
        pass
    return info


def _cpu_model() -> Optional[str]:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def _current_user() -> Optional[str]:
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return os.environ.get("USER")


def get_cpu_usage(interval: float = 1.0, per_core: bool = False) -> dict[str, Any]:
    pct = psutil.cpu_percent(interval=interval, percpu=per_core)
    return {"ok": True, "interval": interval, "per_core": per_core,
            "usage_percent": pct,
            "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None}


def get_memory_info() -> dict[str, Any]:
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "ok": True,
        "memory": {k: getattr(mem, k) for k in
                   ("total", "available", "used", "free", "percent",
                    "buffers", "cached", "shared") if hasattr(mem, k)},
        "swap": {"total": swap.total, "used": swap.used,
                 "free": swap.free, "percent": swap.percent},
    }


def get_disk_usage(path: str = "/") -> dict[str, Any]:
    try:
        d = psutil.disk_usage(os.path.expanduser(path))
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    return {"ok": True, "path": path, "total": d.total, "used": d.used,
            "free": d.free, "percent": d.percent}


def list_disks() -> dict[str, Any]:
    parts = []
    for p in psutil.disk_partitions(all=False):
        entry: dict[str, Any] = {
            "device": p.device, "mountpoint": p.mountpoint,
            "fstype": p.fstype, "opts": p.opts,
        }
        try:
            u = psutil.disk_usage(p.mountpoint)
            entry.update({"total": u.total, "used": u.used,
                          "free": u.free, "percent": u.percent})
        except OSError:
            pass
        parts.append(entry)
    io = psutil.disk_io_counters()
    return {"ok": True, "partitions": parts,
            "io_counters": io._asdict() if io else None}


def get_network_info() -> dict[str, Any]:
    interfaces = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io_per = psutil.net_io_counters(pernic=True)
    for name, addr_list in addrs.items():
        st = stats.get(name)
        entry: dict[str, Any] = {
            "name": name,
            "is_up": st.isup if st else None,
            "speed_mbps": st.speed if st else None,
            "mtu": st.mtu if st else None,
            "addresses": [
                {"family": str(a.family), "address": a.address,
                 "netmask": a.netmask, "broadcast": a.broadcast}
                for a in addr_list
            ],
        }
        if name in io_per:
            c = io_per[name]
            entry["io"] = {"bytes_sent": c.bytes_sent,
                           "bytes_recv": c.bytes_recv,
                           "packets_sent": c.packets_sent,
                           "packets_recv": c.packets_recv}
        interfaces.append(entry)
    routes = run_proc(["ip", "route", "show", "default"], timeout=10)
    dns = []
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.startswith("nameserver"):
                    dns.append(line.split()[1])
    except OSError:
        pass
    return {"ok": True, "hostname": socket.gethostname(),
            "interfaces": interfaces,
            "default_route": routes["stdout"].strip() if routes["ok"] else None,
            "dns_servers": dns}


def list_listening_ports(protocol: str = "all") -> dict[str, Any]:
    """protocol: all|tcp|udp|tcp4|tcp6|udp4|udp6"""
    kinds = {
        "all": ["tcp", "udp"], "tcp": ["tcp"], "udp": ["udp"],
        "tcp4": ["tcp4"], "tcp6": ["tcp6"],
        "udp4": ["udp4"], "udp6": ["udp6"],
    }.get(protocol, ["tcp", "udp"])
    seen = set()
    ports = []
    for kind in kinds:
        try:
            conns = psutil.net_connections(kind=kind)
        except (psutil.AccessDenied, PermissionError):
            return {"ok": False,
                    "error": "Access denied reading connections; run with sudo"}
        for c in conns:
            if kind.startswith("tcp") and c.status != "LISTEN":
                continue
            if not c.laddr:
                continue
            key = (c.laddr.ip, c.laddr.port, kind, c.pid)
            if key in seen:
                continue
            seen.add(key)
            pname = None
            if c.pid:
                try:
                    pname = psutil.Process(c.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            ports.append({
                "protocol": kind, "address": c.laddr.ip, "port": c.laddr.port,
                "pid": c.pid, "process": pname,
                "status": c.status if kind.startswith("tcp") else None,
            })
    ports.sort(key=lambda x: x["port"])
    return {"ok": True, "count": len(ports), "ports": ports}


def get_environment(mask_secrets: bool = True) -> dict[str, Any]:
    """Environment variables of the linuxmcp process.

    mask_secrets redacts values of variables whose name contains
    KEY/TOKEN/SECRET/PASSWORD/PWD.
    """
    env = dict(os.environ)
    if mask_secrets:
        needles = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PWD")
        for k in list(env):
            if any(n in k.upper() for n in needles):
                env[k] = "***"
    return {"ok": True, "count": len(env), "masked": mask_secrets,
            "environment": env}


def get_hardware_info() -> dict[str, Any]:
    """Extra hardware details via lscpu/lsusb/lspci when available."""
    info: dict[str, Any] = {"ok": True}
    for name, argv in (
        ("lscpu", ["lscpu"]),
        ("lsusb", ["lsusb"]),
        ("lspci", ["lspci"]),
        ("lsblk", ["lsblk", "-J", "-o",
                   "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL"]),
        ("dmidecode", ["dmidecode", "-t", "memory"]),
    ):
        r = run_proc(argv, timeout=15)
        if r["ok"] and name == "lsblk":
            import json
            try:
                info[name] = json.loads(r["stdout"])
                continue
            except Exception:
                pass
        info[name] = r["stdout"] if r["ok"] else None
    return info
