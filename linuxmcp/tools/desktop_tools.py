"""Desktop tools: screenshots, window management, input, clipboard."""

from typing import Optional, Union

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from ..core.desktop import clipboard, input as inp, screen, session, windows
from ..util import json_out


def register(mcp: FastMCP) -> None:

    # ----- session diagnostics -----

    @mcp.tool
    def get_desktop_status() -> str:
        """Desktop session diagnostics: X11 vs Wayland vs headless, which
        helper tools are installed (xdotool/wmctrl/xclip/...), and what
        capabilities are available. Call this first if desktop tools fail."""
        return json_out(session.desktop_status())

    # ----- screenshots -----

    @mcp.tool
    def capture_screen() -> Union[Image, str]:
        """Capture the whole screen; returns a PNG image."""
        r = screen.capture_screen()
        if not r["ok"]:
            return json_out(r)
        return Image(data=r["png"], format="png")

    @mcp.tool
    def capture_screen_region(
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> Union[Image, str]:
        """Capture a screen region (x,y top-left, width/height px);
        returns a PNG image."""
        r = screen.capture_screen(region=(x, y, width, height))
        if not r["ok"]:
            return json_out(r)
        return Image(data=r["png"], format="png")

    @mcp.tool
    def capture_screen_to_file(
        path: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> str:
        """Save a screenshot to a PNG file. Region optional (all four of
        x/y/width/height required to be used)."""
        region = None
        if None not in (x, y, width, height):
            region = (x, y, width, height)  # type: ignore[misc]
        return json_out(screen.capture_to_file(path, region=region))

    @mcp.tool
    def get_screen_dimensions() -> str:
        """Screen pixel dimensions and per-monitor geometry."""
        return json_out(screen.get_screen_dimensions())

    # ----- windows (X11) -----

    @mcp.tool
    def list_windows() -> str:
        """List all windows: id, desktop, pid, geometry, wm_class, title.
        X11 only (wmctrl)."""
        return json_out(windows.list_windows())

    @mcp.tool
    def get_active_window() -> str:
        """The currently focused window (id, title, geometry). X11 only."""
        return json_out(windows.get_active_window())

    @mcp.tool
    def focus_window(
        window_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """Raise and focus a window by id (0x...) or title substring."""
        return json_out(windows.focus_window(window_id=window_id,
                                             title=title))

    @mcp.tool
    def close_window(
        window_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """Close a window gracefully by id or title substring."""
        return json_out(windows.close_window(window_id=window_id,
                                             title=title))

    @mcp.tool
    def move_window(
        x: int,
        y: int,
        width: int,
        height: int,
        window_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """Move/resize a window by id or title substring."""
        return json_out(windows.move_window(window_id=window_id, title=title,
                                            x=x, y=y,
                                            width=width, height=height))

    @mcp.tool
    def maximize_window(
        window_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """Maximize a window by id or title substring."""
        return json_out(windows.maximize_window(window_id=window_id,
                                                title=title))

    @mcp.tool
    def minimize_window(
        window_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """Minimize (iconify) a window by id or title substring."""
        return json_out(windows.minimize_window(window_id=window_id,
                                                title=title))

    @mcp.tool
    def restore_window(
        window_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """Unmaximize/restore a window to normal state."""
        return json_out(windows.restore_window(window_id=window_id,
                                               title=title))

    @mcp.tool
    def fullscreen_window(
        window_id: Optional[str] = None,
        title: Optional[str] = None,
        on: bool = True,
    ) -> str:
        """Toggle fullscreen state of a window."""
        return json_out(windows.fullscreen_window(window_id=window_id,
                                                  title=title, on=on))

    @mcp.tool
    def find_windows_by_title(title: str) -> str:
        """Find windows whose title contains the substring (case-insensitive)."""
        return json_out(windows.find_windows_by_title(title))

    @mcp.tool
    def find_windows_by_process(name_or_pid: str) -> str:
        """Find windows owned by a pid or process-name substring."""
        return json_out(windows.find_windows_by_process(name_or_pid))

    # ----- input -----

    @mcp.tool
    def type_text(text: str, delay_ms: int = 12) -> str:
        """Type text as keyboard input (xdotool/wtype). Focus the target
        window first if needed."""
        return json_out(inp.type_text(text, delay_ms=delay_ms))

    @mcp.tool
    def press_key(key: str) -> str:
        """Press a key or combo (xdotool names: Return, Tab, Escape, F5,
        'ctrl+c', 'alt+F4'). See key_reference for valid names."""
        return json_out(inp.press_key(key))

    @mcp.tool
    def send_key_combo(combo: str) -> str:
        """Send a key combination like 'ctrl+alt+t' or 'alt+F4'."""
        return json_out(inp.send_key_combo(combo))

    @mcp.tool
    def key_reference() -> str:
        """List valid key names and combo examples for press_key."""
        return json_out(inp.key_reference())

    @mcp.tool
    def move_mouse(x: int, y: int) -> str:
        """Move the mouse pointer to absolute screen coordinates."""
        return json_out(inp.move_mouse(x, y))

    @mcp.tool
    def get_mouse_position() -> str:
        """Current mouse position (X11 only)."""
        return json_out(inp.get_mouse_position())

    @mcp.tool
    def click(
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
    ) -> str:
        """Click a mouse button, optionally at coordinates (moves first).
        button: left | middle | right"""
        return json_out(inp.click(button=button, x=x, y=y))

    @mcp.tool
    def double_click(
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
    ) -> str:
        """Double-click, optionally at coordinates."""
        return json_out(inp.click(button=button, x=x, y=y, double=True))

    @mcp.tool
    def drag_mouse(
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        button: str = "left",
    ) -> str:
        """Drag with a button held from (x1,y1) to (x2,y2). X11 only."""
        return json_out(inp.drag(x1, y1, x2, y2, button=button))

    @mcp.tool
    def scroll_mouse(
        direction: str = "down",
        clicks: int = 3,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> str:
        """Scroll the mouse wheel up/down, optionally at coordinates.
        X11 only."""
        return json_out(inp.scroll(direction=direction, clicks=clicks,
                                   x=x, y=y))

    # ----- clipboard -----

    @mcp.tool
    def get_clipboard() -> str:
        """Read clipboard text (wl-paste/xclip/xsel)."""
        return json_out(clipboard.get_clipboard())

    @mcp.tool
    def set_clipboard(text: str) -> str:
        """Write text to the clipboard."""
        return json_out(clipboard.set_clipboard(text))
