"""Debian/Ubuntu package management via apt/dpkg."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..util import run_proc, truncate, which

_APT_ENV = {"DEBIAN_FRONTEND": "noninteractive"}


def _apt_available() -> bool:
    return which("apt-get") is not None or which("dpkg-query") is not None


def package_search(query: str, limit: int = 50) -> dict[str, Any]:
    r = run_proc(["apt-cache", "search", "--names-only", query], timeout=30)
    if not r["ok"]:
        r = run_proc(["apt-cache", "search", query], timeout=30)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"]}
    pkgs = []
    for line in r["stdout"].splitlines():
        if " - " in line:
            name, _, desc = line.partition(" - ")
            pkgs.append({"name": name.strip(), "description": desc.strip()})
    return {"ok": True, "query": query, "count": len(pkgs[:limit]),
            "packages": pkgs[:limit]}


def package_info(name: str) -> dict[str, Any]:
    r = run_proc(["apt-cache", "show", name], timeout=15)
    show = r["stdout"] if r["ok"] else ""
    pol = run_proc(["apt-cache", "policy", name], timeout=15)
    fields: dict[str, Any] = {"ok": bool(show or pol["ok"]), "name": name}
    for line in show.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            if k in ("Package", "Version", "Section", "Maintainer",
                     "Installed-Size", "Depends", "Homepage", "Description",
                     "Description-en", "Priority"):
                fields[k.lower().replace("-", "_")] = v.strip()
    fields["policy"] = pol["stdout"].strip() if pol["ok"] else None
    inst = run_proc(["dpkg-query", "-W", "-f=${Status} ${Version}",
                     name], timeout=10)
    fields["installed"] = inst["ok"] and "install ok installed" in inst["stdout"]
    if inst["ok"] and fields["installed"]:
        fields["installed_version"] = inst["stdout"].split()[-1]
    return fields


def package_list_installed(
    filter: Optional[str] = None,
    limit: int = 500,
) -> dict[str, Any]:
    argv = ["dpkg-query", "-W",
            "-f=${Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n"]
    r = run_proc(argv, timeout=30)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"]}
    pkgs = []
    for line in r["stdout"].splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            name = parts[0]
            if filter and filter.lower() not in name.lower():
                continue
            pkgs.append({"name": name, "version": parts[1],
                         "arch": parts[2],
                         "status": parts[3] if len(parts) > 3 else "installed"})
    return {"ok": True, "count": len(pkgs[:limit]), "total": len(pkgs),
            "packages": pkgs[:limit]}


def package_install(
    names: list[str],
    update_first: bool = False,
    timeout: float = 300.0,
) -> dict[str, Any]:
    if not names:
        return {"ok": False, "error": "No package names given"}
    if update_first:
        u = run_proc(["apt-get", "update"], timeout=timeout, sudo=True,
                     env=_APT_ENV)
        if not u["ok"]:
            return {"ok": False, "error": "apt-get update failed",
                    "stdout": u["stdout"], "stderr": u["stderr"]}
    r = run_proc(["apt-get", "install", "-y", "--no-install-recommends",
                  *names], timeout=timeout, sudo=True, env=_APT_ENV)
    out, trunc = truncate(r["stdout"])
    return {"ok": r["ok"], "packages": names, "stdout": out,
            "stderr": r["stderr"], "truncated": trunc,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def package_remove(
    names: list[str],
    purge: bool = False,
    timeout: float = 300.0,
) -> dict[str, Any]:
    if not names:
        return {"ok": False, "error": "No package names given"}
    cmd = "purge" if purge else "remove"
    r = run_proc(["apt-get", cmd, "-y", *names], timeout=timeout, sudo=True,
                 env=_APT_ENV)
    out, trunc = truncate(r["stdout"])
    return {"ok": r["ok"], "packages": names, "action": cmd, "stdout": out,
            "stderr": r["stderr"], "truncated": trunc,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def package_update(timeout: float = 300.0) -> dict[str, Any]:
    """apt-get update (refresh package lists)."""
    r = run_proc(["apt-get", "update"], timeout=timeout, sudo=True,
                 env=_APT_ENV)
    out, trunc = truncate(r["stdout"])
    return {"ok": r["ok"], "stdout": out, "stderr": r["stderr"],
            "truncated": trunc,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def package_upgrade(timeout: float = 600.0,
                    full: bool = False) -> dict[str, Any]:
    """apt-get upgrade (-y). full=True runs dist-upgrade."""
    cmd = "dist-upgrade" if full else "upgrade"
    r = run_proc(["apt-get", cmd, "-y"], timeout=timeout, sudo=True,
                 env=_APT_ENV)
    out, trunc = truncate(r["stdout"])
    return {"ok": r["ok"], "action": cmd, "stdout": out,
            "stderr": r["stderr"], "truncated": trunc,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def package_files(name: str, limit: int = 300) -> dict[str, Any]:
    """List files installed by a package (dpkg -L)."""
    r = run_proc(["dpkg-query", "-L", name], timeout=15)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"]}
    files = [l for l in r["stdout"].splitlines() if l and l != "/."]
    return {"ok": True, "package": name, "count": len(files[:limit]),
            "files": files[:limit]}


def package_owner(path: str) -> dict[str, Any]:
    """Which package owns a file (dpkg -S)."""
    r = run_proc(["dpkg-query", "-S", path], timeout=15)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"], "path": path}
    owners = []
    for line in r["stdout"].splitlines():
        if ": " in line:
            pkg, _, p = line.partition(": ")
            owners.append({"package": pkg.strip(), "path": p.strip()})
    return {"ok": True, "path": path, "owners": owners}
