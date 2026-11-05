"""Clipboard read/write via wl-clipboard (Wayland) or xclip/xsel (X11)."""

from __future__ import annotations

from typing import Any

from ...util import run_proc, which
from .session import session_type


def get_clipboard() -> dict[str, Any]:
    st = session_type()
    if st == "wayland" and which("wl-paste"):
        r = run_proc(["wl-paste", "--no-newline"], timeout=10)
        if r["ok"]:
            return {"ok": True, "backend": "wl-paste", "text": r["stdout"]}
    for tool, argv in (("xclip", ["xclip", "-selection", "clipboard", "-o"]),
                       ("xsel", ["xsel", "-b", "-o"])):
        if which(tool):
            r = run_proc(argv, timeout=10)
            if r["ok"]:
                return {"ok": True, "backend": tool, "text": r["stdout"]}
    if st == "none":
        return {"ok": False, "error": "No display session; clipboard "
                                      "unavailable. Set DISPLAY/XAUTHORITY."}
    return {"ok": False, "error": "No clipboard tool found. Install "
                                  "xclip/xsel (X11) or wl-clipboard (Wayland)."}


def set_clipboard(text: str) -> dict[str, Any]:
    st = session_type()
    if st == "wayland" and which("wl-copy"):
        r = run_proc(["wl-copy"], timeout=10, input_text=text)
        if r["ok"]:
            return {"ok": True, "backend": "wl-copy", "chars": len(text)}
    for tool, argv in (("xclip", ["xclip", "-selection", "clipboard", "-i"]),
                       ("xsel", ["xsel", "-b", "-i"])):
        if which(tool):
            r = run_proc(argv, timeout=10, input_text=text)
            if r["ok"]:
                return {"ok": True, "backend": tool, "chars": len(text)}
            if r["error"] is None and not r["stderr"]:
                # xclip forks and keeps stdin; run_proc still completes
                return {"ok": True, "backend": tool, "chars": len(text)}
    if st == "none":
        return {"ok": False, "error": "No display session; clipboard "
                                      "unavailable. Set DISPLAY/XAUTHORITY."}
    return {"ok": False, "error": "No clipboard tool found. Install "
                                  "xclip/xsel (X11) or wl-clipboard (Wayland)."}
