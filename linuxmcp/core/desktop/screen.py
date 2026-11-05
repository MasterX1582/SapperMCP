"""Screen capture with a fallback chain: mss -> gnome-screenshot -> grim ->
scrot -> ImageMagick import -> XDG portal -> gnome-shell D-Bus."""

from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from ...util import run_proc, which
from .session import session_type

_PORTAL_HELPER = Path(__file__).resolve().parent / "portal_screenshot.py"


def _portal_python() -> Optional[str]:
    """Find a Python with PyGObject for the portal helper."""
    candidates = []
    # system python first: venvs usually lack `gi`
    for p in ("/usr/bin/python3", "/usr/bin/python"):
        if os.path.exists(p):
            candidates.append(p)
    candidates.append(sys.executable)
    for py in candidates:
        r = run_proc([py, "-c", "import gi"], timeout=10)
        if r["ok"]:
            return py
    return None


def _png_via_portal(region: Optional[tuple[int, int, int, int]]) -> Optional[bytes]:
    """Screenshot via the XDG Screenshot portal (works on GNOME Wayland).

    The first call makes GNOME show a one-time permission prompt; the
    portal persists the grant, so later calls are silent.
    """
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return None
    py = _portal_python()
    if py is None or not _PORTAL_HELPER.exists():
        return None
    r = run_proc([py, str(_PORTAL_HELPER), "30"], timeout=45)
    line = r["stdout"].strip().splitlines()
    if not line or not line[-1].startswith("ok "):
        return None
    uri = line[-1][3:].strip()
    try:
        path = unquote(urlparse(uri).path)
        with open(path, "rb") as f:
            data = f.read()
        try:
            os.unlink(path)  # portal drops it in ~/Pictures; keep it tidy
        except OSError:
            pass
        if not data:
            return None
        if region:
            data = _crop_png(data, region) or data
        return data
    except Exception:
        return None


def _png_via_mss(region: Optional[tuple[int, int, int, int]]) -> Optional[bytes]:
    try:
        import mss
        import mss.tools
    except ImportError:
        return None
    if session_type() == "wayland":
        # On Wayland mss only sees the empty XWayland root -> black image.
        return None
    if session_type() != "x11" and not os.environ.get("DISPLAY"):
        return None
    try:
        with mss.mss() as sct:
            if region:
                x, y, w, h = region
                mon = {"left": x, "top": y, "width": w, "height": h}
            else:
                mon = sct.monitors[0]  # union of all monitors
            shot = sct.grab(mon)
            return mss.tools.to_png(shot.rgb, shot.size)
    except Exception:
        return None


def _png_via_gdbus(region: Optional[tuple[int, int, int, int]]) -> Optional[bytes]:
    """GNOME Shell screenshot via D-Bus (pre-GNOME-45 Wayland only; newer
    shells deny this call for arbitrary senders)."""
    if which("gdbus") is None:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        if region:
            x, y, w, h = region
            args = ["org.gnome.Shell.Screenshot.ScreenshotArea",
                    str(x), str(y), str(w), str(h),
                    "false", "false", tmp.name]
        else:
            args = ["org.gnome.Shell.Screenshot.Screenshot",
                    "false", "false", tmp.name]
        r = run_proc(["gdbus", "call", "--session",
                      "--dest", "org.gnome.Shell",
                      "--object-path", "/org/gnome/Shell/Screenshot",
                      "--method", *args], timeout=20)
        if not r["ok"] or "true" not in r["stdout"].lower():
            return None
        if os.path.getsize(tmp.name) == 0:
            return None
        with open(tmp.name, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _png_via_tool(tool: str, region: Optional[tuple[int, int, int, int]]) -> Optional[bytes]:
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    try:
        argv: list[str]
        if tool == "gnome-screenshot":
            argv = [tool, "-f", tmp.name]
        elif tool == "grim":
            argv = [tool, tmp.name]
        elif tool == "scrot":
            argv = [tool, "-o", tmp.name]
        elif tool == "import":
            argv = [tool, "-window", "root", tmp.name]
        else:
            return None
        r = run_proc(argv, timeout=20)
        if not r["ok"] or os.path.getsize(tmp.name) == 0:
            return None
        data = open(tmp.name, "rb").read()
        if region:
            data = _crop_png(data, region) or data
        return data
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _crop_png(data: bytes, region: tuple[int, int, int, int]) -> Optional[bytes]:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        x, y, w, h = region
        out = io.BytesIO()
        img.crop((x, y, x + w, y + h)).save(out, "PNG")
        return out.getvalue()
    except Exception:
        return None


def session_locked() -> Optional[bool]:
    """True if the logind session is locked (screenshots return black)."""
    if which("loginctl") is None:
        return None
    try:
        r = run_proc(["loginctl", "list-sessions", "--no-legend"], timeout=5)
        if not r["ok"]:
            return None
        for line in r["stdout"].splitlines():
            parts = line.split()
            if not parts:
                continue
            sid = parts[0]
            r2 = run_proc(["loginctl", "show-session", sid,
                           "-p", "LockedHint", "--value"], timeout=5)
            if r2["ok"] and r2["stdout"].strip() == "yes":
                return True
        return False
    except Exception:
        return None


def capture_screen(
    region: Optional[tuple[int, int, int, int]] = None,
) -> dict[str, Any]:
    """Capture the full screen (or region x,y,w,h). Returns PNG bytes."""
    st = session_type()
    png: Optional[bytes] = None
    backend = ""
    if st == "wayland":
        # XWayland (mss/scrot/import) sees an empty root on Wayland; use
        # compositor/portal-aware capture first.
        for tool in ("gnome-screenshot", "grim"):
            if which(tool):
                png = _png_via_tool(tool, region)
                backend = tool
                if png:
                    break
        if png is None:
            png = _png_via_portal(region)
            backend = "xdg-portal"
        if png is None:
            png = _png_via_gdbus(region)
            backend = "gnome-shell-dbus"
    else:
        png = _png_via_mss(region)
        backend = "mss"
        if png is None:
            for tool in ("scrot", "import", "gnome-screenshot", "grim"):
                if which(tool):
                    png = _png_via_tool(tool, region)
                    backend = tool
                    if png:
                        break
        if png is None:
            png = _png_via_portal(region)
            backend = "xdg-portal"
        if png is None:
            png = _png_via_gdbus(region)
            backend = "gnome-shell-dbus"
    if png is None:
        return {
            "ok": False,
            "error": "Screen capture failed on every backend. On Wayland "
                     "the XDG portal backend should work - check that the "
                     "user granted screenshot permission when the portal "
                     "prompted once. Otherwise ensure DISPLAY/XAUTHORITY "
                     "are set, or install mss (pip), gnome-screenshot, "
                     "grim, scrot or imagemagick.",
        }
    out: dict[str, Any] = {"ok": True, "backend": backend, "png": png,
                           "bytes": len(png), "region": region}
    locked = session_locked()
    if locked:
        out["session_locked"] = True
        out["note"] = ("Desktop session is locked; compositor serves "
                       "black frames. Unlock the screen for real pixels.")
    return out


def capture_to_file(
    path: str,
    region: Optional[tuple[int, int, int, int]] = None,
) -> dict[str, Any]:
    r = capture_screen(region)
    if not r["ok"]:
        return r
    path = os.path.expanduser(path)
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            f.write(r["png"])
    except OSError as e:
        return {"ok": False, "error": str(e)}
    out = {"ok": True, "path": path, "bytes": r["bytes"],
           "backend": r["backend"]}
    if r.get("session_locked"):
        out["session_locked"] = True
        out["note"] = r["note"]
    return out


def get_screen_dimensions() -> dict[str, Any]:
    try:
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[0]
            return {"ok": True, "backend": "mss",
                    "width": mon["width"], "height": mon["height"],
                    "monitors": sct.monitors[1:]}
    except Exception:
        pass
    if which("xrandr"):
        r = run_proc(["xrandr", "--current"], timeout=10)
        if r["ok"]:
            for line in r["stdout"].splitlines():
                if " connected" in line:
                    # e.g. "HDMI-1 connected 1920x1080+0+0 ..."
                    for tok in line.split():
                        if "x" in tok and "+" in tok:
                            res = tok.split("+")[0]
                            w, h = res.split("x")
                            return {"ok": True, "backend": "xrandr",
                                    "width": int(w), "height": int(h)}
    return {"ok": False, "error": "Could not determine screen dimensions"}
