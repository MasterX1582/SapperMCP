"""Keyboard/mouse input via xdotool (X11) or ydotool/wtype (Wayland)."""

from __future__ import annotations

from typing import Any, Optional

from ...util import run_proc, which
from .session import session_type

_BUTTONS = {"left": 1, "middle": 2, "right": 3,
            "scroll_up": 4, "scroll_down": 5}


def _backend() -> tuple[Optional[str], Optional[str]]:
    """Return (backend, error)."""
    st = session_type()
    if st == "x11":
        if which("xdotool"):
            return "xdotool", None
        return None, "xdotool not installed: sudo apt install xdotool"
    if st == "wayland":
        if which("ydotool"):
            return "ydotool", None
        if which("wtype"):
            return "wtype", None
        return None, ("No Wayland input tool. Install ydotool (+ ydotoold "
                      "running) or wtype.")
    return None, ("No display session. Set LINUXMCP_DISPLAY/LINUXMCP_XAUTHORITY "
                  "or pass --display.")


def _xd(*args: str) -> dict[str, Any]:
    r = run_proc(["xdotool", *args], timeout=15)
    return {"ok": r["ok"], "stderr": r["stderr"] or None,
            "error": None if r["ok"] else (r["stderr"] or r["error"])}


def type_text(text: str, delay_ms: int = 12) -> dict[str, Any]:
    backend, err = _backend()
    if err:
        return {"ok": False, "error": err}
    if backend == "xdotool":
        r = _xd("type", "--clearmodifiers", "--delay", str(delay_ms),
                "--", text)
    elif backend == "ydotool":
        r_raw = run_proc(["ydotool", "type", "--", text], timeout=30)
        r = {"ok": r_raw["ok"], "error": None if r_raw["ok"] else r_raw["stderr"]}
    else:  # wtype
        r_raw = run_proc(["wtype", "--", text], timeout=30)
        r = {"ok": r_raw["ok"], "error": None if r_raw["ok"] else r_raw["stderr"]}
    r.update({"backend": backend, "chars": len(text)})
    return r


def press_key(key: str) -> dict[str, Any]:
    """Press a key by name (xdotool syntax: Return, Tab, Escape, F5,
    ctrl+c combos supported too — see send_key_combo)."""
    backend, err = _backend()
    if err:
        return {"ok": False, "error": err}
    if backend != "xdotool":
        mapped = _YDOTOOL_KEYCODES.get(key.lower())
        if mapped is None:
            return {"ok": False,
                    "error": f"Key '{key}' unsupported on Wayland backend; "
                             f"supported: {sorted(_YDOTOOL_KEYCODES)}"}
        codes = " ".join(f"{c}:1 {c}:0" for c in mapped).split()
        r_raw = run_proc(["ydotool", "key", *codes], timeout=10)
        return {"ok": r_raw["ok"], "backend": backend, "key": key,
                "error": None if r_raw["ok"] else r_raw["stderr"]}
    r = _xd("key", "--clearmodifiers", key)
    r.update({"backend": backend, "key": key})
    return r


def send_key_combo(combo: str) -> dict[str, Any]:
    """Key combo like 'ctrl+c', 'ctrl+alt+t', 'alt+F4' (xdotool syntax)."""
    return press_key(combo)


_YDOTOOL_KEYCODES = {  # name -> evdev keycode
    "enter": [28], "return": [28], "tab": [15], "escape": [1], "esc": [1],
    "backspace": [14], "delete": [111], "space": [57],
    "up": [103], "down": [108], "left": [105], "right": [106],
    "home": [102], "end": [107], "pageup": [104], "pagedown": [109],
    "ctrl+c": [29, 46], "ctrl+v": [29, 47], "ctrl+x": [29, 45],
    "ctrl+z": [29, 44], "ctrl+a": [29, 30], "ctrl+s": [29, 31],
    "alt+f4": [56, 62], "ctrl+alt+t": [29, 56, 20],
    "f1": [59], "f2": [60], "f3": [61], "f4": [62], "f5": [63],
    "f6": [64], "f7": [65], "f8": [66], "f9": [67], "f10": [68],
    "f11": [87], "f12": [88],
}

_KEY_REFERENCE = {
    "special": ["Return", "Enter", "Tab", "Escape", "BackSpace", "Delete",
                "space", "Home", "End", "Page_Up", "Page_Down",
                "Up", "Down", "Left", "Right", "Insert", "Menu",
                "Caps_Lock", "Num_Lock", "Print", "Scroll_Lock", "Pause"],
    "function": [f"F{i}" for i in range(1, 25)],
    "modifiers": ["ctrl", "alt", "shift", "super (windows/logo key)"],
    "combo_examples": ["ctrl+c", "ctrl+alt+t", "alt+F4", "super+l",
                       "ctrl+shift+v", "alt+Tab"],
    "note": "Use xdotool key names; combos are '+'-joined.",
}


def key_reference() -> dict[str, Any]:
    return {"ok": True, **_KEY_REFERENCE}


def move_mouse(x: int, y: int) -> dict[str, Any]:
    backend, err = _backend()
    if err:
        return {"ok": False, "error": err}
    if backend == "xdotool":
        r = _xd("mousemove", str(x), str(y))
    elif backend == "ydotool":
        r_raw = run_proc(["ydotool", "mousemove", "--absolute",
                          "-x", str(x), "-y", str(y)], timeout=10)
        r = {"ok": r_raw["ok"], "error": None if r_raw["ok"] else r_raw["stderr"]}
    else:
        return {"ok": False,
                "error": "wtype cannot move the pointer; install ydotool"}
    r.update({"backend": backend, "x": x, "y": y})
    return r


def get_mouse_position() -> dict[str, Any]:
    backend, err = _backend()
    if err:
        return {"ok": False, "error": err}
    if backend != "xdotool":
        return {"ok": False,
                "error": "Pointer position query not supported on Wayland"}
    r = run_proc(["xdotool", "getmouselocation", "--shell"], timeout=10)
    if not r["ok"]:
        return {"ok": False, "error": r["stderr"] or r["error"]}
    pos = {}
    for line in r["stdout"].splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                pos[k.lower()] = int(v)
            except ValueError:
                pos[k.lower()] = v
    return {"ok": True, **pos}


def click(button: str = "left", x: Optional[int] = None,
          y: Optional[int] = None, double: bool = False) -> dict[str, Any]:
    backend, err = _backend()
    if err:
        return {"ok": False, "error": err}
    if button not in _BUTTONS:
        return {"ok": False, "error": f"Unknown button '{button}'",
                "buttons": list(_BUTTONS)}
    if backend == "xdotool":
        args = []
        if x is not None and y is not None:
            args += ["mousemove", str(x), str(y)]
        args += ["click"]
        if double:
            args += ["--repeat", "2", "--delay", "80"]
        args += [str(_BUTTONS[button])]
        r = _xd(*args)
    elif backend == "ydotool":
        code = {"left": "0x110", "right": "0x111", "middle": "0x112"}[button]
        cmds = []
        if x is not None and y is not None:
            cmds.append(["ydotool", "mousemove", "--absolute",
                         "-x", str(x), "-y", str(y)])
        clicks = 2 if double else 1
        for _ in range(clicks):
            cmds.append(["ydotool", "click", code])
        ok_all, err_out = True, None
        for c in cmds:
            rr = run_proc(c, timeout=10)
            if not rr["ok"]:
                ok_all, err_out = False, rr["stderr"]
                break
        r = {"ok": ok_all, "error": err_out}
    else:
        return {"ok": False, "error": "wtype cannot click; install ydotool"}
    r.update({"backend": backend, "button": button,
              "x": x, "y": y, "double": double})
    return r


def drag(x1: int, y1: int, x2: int, y2: int,
         button: str = "left", steps: int = 15) -> dict[str, Any]:
    backend, err = _backend()
    if err:
        return {"ok": False, "error": err}
    if backend != "xdotool":
        return {"ok": False,
                "error": "Drag not implemented for Wayland backend"}
    b = str(_BUTTONS.get(button, 1))
    args = ["mousemove", str(x1), str(y1), "mousedown", b]
    dx, dy = (x2 - x1) / steps, (y2 - y1) / steps
    for i in range(1, steps + 1):
        args += ["mousemove", str(int(x1 + dx * i)), str(int(y1 + dy * i)),
                 "sleep", "0.01"]
    args += ["mouseup", b]
    r = _xd(*args)
    r.update({"backend": backend, "from": [x1, y1], "to": [x2, y2]})
    return r


def scroll(direction: str = "down", clicks: int = 3,
           x: Optional[int] = None, y: Optional[int] = None) -> dict[str, Any]:
    btn = {"up": "scroll_up", "down": "scroll_down"}.get(direction)
    if btn is None:
        return {"ok": False, "error": "direction must be 'up' or 'down'"}
    backend, err = _backend()
    if err:
        return {"ok": False, "error": err}
    if backend != "xdotool":
        return {"ok": False,
                "error": "Scroll not implemented for Wayland backend"}
    args = []
    if x is not None and y is not None:
        args += ["mousemove", str(x), str(y)]
    args += ["click", "--repeat", str(clicks), "--delay", "60",
             str(_BUTTONS[btn])]
    r = _xd(*args)
    r.update({"backend": backend, "direction": direction, "clicks": clicks})
    return r
