"""Desktop session detection: X11 vs Wayland vs headless, and which helper
tools are installed."""

from __future__ import annotations

import os
from typing import Any

from ...util import run_proc, which

_HELPER_TOOLS = [
    "xdotool", "wmctrl", "xclip", "xsel", "scrot", "import",
    "gnome-screenshot", "grim", "slurp", "ydotool", "wl-copy", "wl-paste",
    "xrandr", "swaymsg", "wtype", "gdbus", "spectacle",
]


def session_type() -> str:
    """'x11' | 'wayland' | 'none'"""
    xdg = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if xdg in ("x11", "wayland"):
        return xdg
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "none"


def display_env() -> dict[str, str]:
    """Environment variables needed to reach the display server."""
    return {k: os.environ[k] for k in
            ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
             "XDG_SESSION_TYPE", "XDG_RUNTIME_DIR",
             "DBUS_SESSION_BUS_ADDRESS")
            if k in os.environ}


def available_tools() -> dict[str, str]:
    return {t: p for t in _HELPER_TOOLS if (p := which(t))}


def desktop_status() -> dict[str, Any]:
    st = session_type()
    tools = available_tools()
    mss_ok = False
    try:
        import mss  # noqa: F401
        mss_ok = os.environ.get("DISPLAY") is not None
    except ImportError:
        pass
    caps = {
        "screenshot": mss_ok or any(t in tools for t in
                                    ("gnome-screenshot", "grim", "scrot",
                                     "import", "gdbus", "spectacle")),
        "window_management": st == "x11" and "wmctrl" in tools,
        "input": ("xdotool" in tools and st == "x11")
        or ("ydotool" in tools and st == "wayland")
        or "wtype" in tools,
        "clipboard": any(t in tools for t in ("xclip", "xsel", "wl-copy")),
    }
    missing_hints = []
    if st == "x11":
        for t in ("xdotool", "wmctrl", "xclip"):
            if t not in tools:
                missing_hints.append(t)
    if st == "wayland" and "ydotool" not in tools:
        missing_hints.append("ydotool (needs ydotoold running for input)")
    return {
        "ok": True,
        "session_type": st,
        "display_env": display_env(),
        "tools": tools,
        "capabilities": caps,
        "missing_recommended": missing_hints,
        "notes": _notes(st, tools),
    }


def _notes(st: str, tools: dict) -> list[str]:
    notes = []
    if st == "none":
        notes.append(
            "No display detected. If linuxmcp runs under systemd/SSH, set "
            "LINUXMCP_DISPLAY (e.g. :0) and LINUXMCP_XAUTHORITY "
            "(e.g. /run/user/1000/.mutter-Xwaylandauth.*) or pass --display.")
    if st == "wayland":
        notes.append(
            "Wayland: window management (list/focus/move) is not supported by "
            "wmctrl/xdotool. Screenshots via gnome-screenshot/grim; input via "
            "ydotool. For full desktop control use an Xorg session.")
    if st == "x11" and "xdotool" not in tools:
        notes.append("Install xdotool, wmctrl, xclip for full control: "
                     "sudo apt install xdotool wmctrl xclip")
    return notes


def require_x11() -> str | None:
    """Return an error string if X11 is not usable, else None."""
    if session_type() == "none":
        return ("No display session (DISPLAY unset). Set LINUXMCP_DISPLAY/"
                "LINUXMCP_XAUTHORITY or pass --display.")
    if session_type() == "wayland":
        return ("This tool requires X11; the session is Wayland. "
                "Log into an 'on Xorg' session for window/input control.")
    return None
