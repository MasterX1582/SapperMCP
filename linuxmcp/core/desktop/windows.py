"""Window management via wmctrl/xdotool (X11 only)."""

from __future__ import annotations

from typing import Any, Optional

from ...util import run_proc, which
from .session import require_x11


def _check() -> Optional[dict[str, Any]]:
    if err := require_x11():
        return {"ok": False, "error": err}
    if which("wmctrl") is None:
        return {"ok": False,
                "error": "wmctrl not installed: sudo apt install wmctrl"}
    return None


def list_windows() -> dict[str, Any]:
    if e := _check():
        return e
    # -G geometry, -p pid, -x WM_CLASS
    r = run_proc(["wmctrl", "-l", "-G", "-p", "-x"], timeout=15)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"]}
    wins = []
    for line in r["stdout"].splitlines():
        # wmctrl -lpGx output: id desktop pid x y w h class host title
        parts = line.split(None, 9)
        if len(parts) < 9:
            parts = line.split(None, 8)
        try:
            wins.append({
                "id": parts[0],
                "desktop": int(parts[1]),
                "pid": int(parts[2]),
                "x": int(parts[3]), "y": int(parts[4]),
                "width": int(parts[5]), "height": int(parts[6]),
                "wm_class": parts[7],
                "host": parts[8] if len(parts) > 8 else "",
                "title": parts[9] if len(parts) > 9 else "",
            })
        except (ValueError, IndexError):
            continue
    return {"ok": True, "count": len(wins), "windows": wins}


def _resolve_window(window_id: Optional[str], title: Optional[str]) -> dict[str, Any]:
    """Resolve a window identifier. window_id like 0x03a00007; title matches
    (case-insensitive substring). Returns {"id": ...} or error dict."""
    if window_id:
        return {"id": window_id}
    if title:
        found = find_windows_by_title(title)
        if not found.get("windows"):
            return {"ok": False, "error": f"No window matching title '{title}'"}
        return {"id": found["windows"][0]["id"],
                "matched_title": found["windows"][0]["title"]}
    return {"ok": False, "error": "Provide window_id or title"}


def get_active_window() -> dict[str, Any]:
    if err := require_x11():
        return {"ok": False, "error": err}
    if which("xdotool") is None:
        return {"ok": False, "error": "xdotool not installed"}
    wid = run_proc(["xdotool", "getactivewindow"], timeout=10)
    if not wid["ok"]:
        return {"ok": False, "error": wid["stderr"] or wid["error"]}
    wid_s = wid["stdout"].strip()
    name = run_proc(["xdotool", "getwindowname", wid_s], timeout=10)
    geo = run_proc(["xdotool", "getwindowgeometry", wid_s], timeout=10)
    return {"ok": True, "id": wid_s,
            "title": name["stdout"].strip() if name["ok"] else None,
            "geometry": geo["stdout"].strip() if geo["ok"] else None}


def _wmctrl_action(*args: str) -> dict[str, Any]:
    r = run_proc(["wmctrl", *args], timeout=15)
    return {"ok": r["ok"], "error": None if r["ok"] else (r["stderr"] or r["error"])}


def focus_window(window_id: Optional[str] = None,
                 title: Optional[str] = None) -> dict[str, Any]:
    if e := _check():
        return e
    res = _resolve_window(window_id, title)
    if "id" not in res:
        return res
    r = _wmctrl_action("-i", "-a", res["id"])
    r["window_id"] = res["id"]
    return r


def close_window(window_id: Optional[str] = None,
                 title: Optional[str] = None) -> dict[str, Any]:
    if e := _check():
        return e
    res = _resolve_window(window_id, title)
    if "id" not in res:
        return res
    r = _wmctrl_action("-i", "-c", res["id"])
    r["window_id"] = res["id"]
    return r


def move_window(window_id: Optional[str] = None, title: Optional[str] = None,
                x: int = 0, y: int = 0,
                width: int = 800, height: int = 600) -> dict[str, Any]:
    if e := _check():
        return e
    res = _resolve_window(window_id, title)
    if "id" not in res:
        return res
    r = _wmctrl_action("-i", "-r", res["id"], "-e",
                       f"0,{x},{y},{width},{height}")
    r["window_id"] = res["id"]
    r["geometry"] = {"x": x, "y": y, "width": width, "height": height}
    return r


def _state_action(prop: str, add: bool,
                  window_id: Optional[str], title: Optional[str]) -> dict[str, Any]:
    if e := _check():
        return e
    res = _resolve_window(window_id, title)
    if "id" not in res:
        return res
    r = _wmctrl_action("-i", "-r", res["id"], "-b",
                       ("add" if add else "remove") + "," + prop)
    r["window_id"] = res["id"]
    return r


def maximize_window(window_id: Optional[str] = None,
                    title: Optional[str] = None) -> dict[str, Any]:
    return _state_action("maximized_vert,maximized_horz", True, window_id, title)


def restore_window(window_id: Optional[str] = None,
                   title: Optional[str] = None) -> dict[str, Any]:
    return _state_action("maximized_vert,maximized_horz", False, window_id, title)


def minimize_window(window_id: Optional[str] = None,
                    title: Optional[str] = None) -> dict[str, Any]:
    if e := _check():
        return e
    if which("xdotool") is None:
        return {"ok": False, "error": "xdotool not installed"}
    res = _resolve_window(window_id, title)
    if "id" not in res:
        return res
    r = run_proc(["xdotool", "windowminimize", res["id"]], timeout=10)
    return {"ok": r["ok"], "window_id": res["id"],
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def fullscreen_window(window_id: Optional[str] = None,
                      title: Optional[str] = None,
                      on: bool = True) -> dict[str, Any]:
    return _state_action("fullscreen", on, window_id, title)


def find_windows_by_title(title: str) -> dict[str, Any]:
    r = list_windows()
    if not r["ok"]:
        return r
    matches = [w for w in r["windows"] if title.lower() in w["title"].lower()]
    return {"ok": True, "count": len(matches), "windows": matches}


def find_windows_by_process(name_or_pid: str) -> dict[str, Any]:
    r = list_windows()
    if not r["ok"]:
        return r
    matches = []
    try:
        pid = int(name_or_pid)
        matches = [w for w in r["windows"] if w["pid"] == pid]
    except ValueError:
        import psutil
        pids = set()
        for p in psutil.process_iter(attrs=["name"]):
            try:
                if name_or_pid.lower() in (p.info["name"] or "").lower():
                    pids.add(p.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        matches = [w for w in r["windows"] if w["pid"] in pids]
    return {"ok": True, "count": len(matches), "windows": matches}
