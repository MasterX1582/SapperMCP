"""GNOME desktop settings via gsettings/dconf — the Linux 'registry'."""

from __future__ import annotations

from typing import Any, Optional

from ..util import run_proc, which


def _check() -> Optional[dict[str, Any]]:
    if which("gsettings") is None:
        return {"ok": False,
                "error": "gsettings not available (no GNOME/GLib desktop?)"}
    return None


def gsettings_get(schema: str, key: str) -> dict[str, Any]:
    if e := _check():
        return e
    r = run_proc(["gsettings", "get", schema, key], timeout=10)
    return {"ok": r["ok"], "schema": schema, "key": key,
            "value": r["stdout"].strip() if r["ok"] else None,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def gsettings_set(schema: str, key: str, value: str) -> dict[str, Any]:
    """value is passed raw in GVariant syntax, e.g. 'true', '42', "'text'",
    "['a','b']". Booleans/numbers unquoted; strings need single quotes."""
    if e := _check():
        return e
    r = run_proc(["gsettings", "set", schema, key, value], timeout=10)
    return {"ok": r["ok"], "schema": schema, "key": key, "value": value,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def gsettings_reset(schema: str, key: str) -> dict[str, Any]:
    if e := _check():
        return e
    r = run_proc(["gsettings", "reset", schema, key], timeout=10)
    return {"ok": r["ok"], "schema": schema, "key": key,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def gsettings_list_schemas(filter: Optional[str] = None,
                           limit: int = 300) -> dict[str, Any]:
    if e := _check():
        return e
    r = run_proc(["gsettings", "list-schemas"], timeout=15)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"]}
    schemas = [s.strip() for s in r["stdout"].splitlines() if s.strip()]
    if filter:
        schemas = [s for s in schemas if filter.lower() in s.lower()]
    return {"ok": True, "count": len(schemas[:limit]),
            "total": len(schemas), "schemas": schemas[:limit]}


def gsettings_list_keys(schema: str) -> dict[str, Any]:
    if e := _check():
        return e
    r = run_proc(["gsettings", "list-keys", schema], timeout=10)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"], "schema": schema}
    keys = [k.strip() for k in r["stdout"].splitlines() if k.strip()]
    return {"ok": True, "schema": schema, "count": len(keys), "keys": keys}


def gsettings_describe(schema: str, key: str) -> dict[str, Any]:
    if e := _check():
        return e
    desc = run_proc(["gsettings", "describe", schema, key], timeout=10)
    rng = run_proc(["gsettings", "range", schema, key], timeout=10)
    return {"ok": desc["ok"], "schema": schema, "key": key,
            "description": desc["stdout"].strip() if desc["ok"] else None,
            "range": rng["stdout"].strip() if rng["ok"] else None,
            "error": None if desc["ok"] else (desc["stderr"] or desc["error"])}


def dconf_read(path: str) -> dict[str, Any]:
    if which("dconf") is None:
        return {"ok": False, "error": "dconf not available"}
    r = run_proc(["dconf", "read", path], timeout=10)
    return {"ok": r["ok"], "path": path,
            "value": r["stdout"].strip() if r["ok"] else None,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def dconf_write(path: str, value: str) -> dict[str, Any]:
    if which("dconf") is None:
        return {"ok": False, "error": "dconf not available"}
    r = run_proc(["dconf", "write", path, value], timeout=10)
    return {"ok": r["ok"], "path": path, "value": value,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def dconf_list(path: str) -> dict[str, Any]:
    """List keys/dirs under a dconf path, e.g. /org/gnome/desktop/."""
    if which("dconf") is None:
        return {"ok": False, "error": "dconf not available"}
    r = run_proc(["dconf", "list", path], timeout=10)
    return {"ok": r["ok"], "path": path,
            "entries": r["stdout"].splitlines() if r["ok"] else [],
            "error": None if r["ok"] else (r["stderr"] or r["error"])}
