"""linuxmcp-gui - GTK control panel for linuxmcpd.

Pure stdlib + PyGObject: deliberately free of fastmcp/mcp imports so that
when the package is installed in a venv without `gi`, the app can re-exec
itself under the system Python (/usr/bin/python3, which has python3-gi on
Ubuntu/Zorin) with the venv's site-packages on PYTHONPATH.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def _bootstrap_gi() -> None:
    try:
        import gi  # noqa: F401
        return
    except ImportError:
        pass
    # Re-exec under the system interpreter with the package importable.
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_parent + os.pathsep + env.get("PYTHONPATH", "")
    for py in ("/usr/bin/python3", "/usr/bin/python"):
        if os.path.exists(py):
            os.execve(py, [py, "-m", "linuxmcp.gui"], env)
    raise SystemExit(
        "PyGObject (python3-gi) not found.\n"
        "Install it with: sudo apt install python3-gi gir1.2-gtk-3.0")


_bootstrap_gi()

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .control import daemon_running, send_command  # noqa: E402
from .ctl import ensure_daemon  # noqa: E402


def _local_ips() -> list[str]:
    import socket
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if "." in ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


CSS = b"""
#linuxmcp-status { font-size: 16px; font-weight: bold; }
#linuxmcp-url { font-size: 12px; }
#logview text { background: #0a0f0a; color: #39d353; }
#logview { font-family: Monospace; font-size: 11px; }
#warn { color: #e0a030; }
"""


class LinuxMcpWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="LinuxMCP Control")
        self.set_default_size(560, 620)
        self.set_border_width(12)
        self._log_since = 0
        self._daemon_up = False
        self._server_up = False
        self._tray = None
        self._dirty = False  # user edited controls not yet Applied

        style = Gtk.CssProvider()
        style.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), style,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(root)

        # ---- status header ----
        self.status_label = Gtk.Label(name="linuxmcp-status",
                                      label="Daemon: …", xalign=0)
        self.url_label = Gtk.Label(name="linuxmcp-url",
                                   label="", xalign=0, selectable=True)
        self.net_label = Gtk.Label(label="", xalign=0, selectable=True)
        self.net_label.set_line_wrap(True)
        root.pack_start(self.status_label, False, False, 0)
        root.pack_start(self.url_label, False, False, 0)
        root.pack_start(self.net_label, False, False, 0)
        root.pack_start(Gtk.Separator(), False, False, 4)

        # ---- settings grid ----
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        grid.set_column_homogeneous(False)
        root.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label="Port", xalign=0), 0, 0, 1, 1)
        self.port_spin = Gtk.SpinButton.new_with_range(1024, 65535, 1)
        self.port_spin.set_value(3939)
        self.port_spin.connect("value-changed", self._mark_dirty)
        grid.attach(self.port_spin, 1, 0, 2, 1)

        grid.attach(Gtk.Label(label="Allow remote (LAN) connections",
                              xalign=0), 0, 1, 1, 1)
        self.remote_switch = Gtk.Switch(halign=Gtk.Align.START)
        self.remote_switch.connect("notify::active", self._on_remote_toggled)
        self.remote_switch.connect("notify::active", self._mark_dirty)
        grid.attach(self.remote_switch, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Auth token", xalign=0), 0, 2, 1, 1)
        tok_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.token_entry = Gtk.Entry()
        self.token_entry.set_placeholder_text("empty = no auth")
        self.token_entry.set_visibility(True)
        self.token_entry.connect("changed", self._mark_dirty)
        tok_box.pack_start(self.token_entry, True, True, 0)
        gen = Gtk.Button(label="Generate")
        gen.connect("clicked", lambda *_:
                    self.token_entry.set_text(secrets.token_hex(24)))
        tok_box.pack_start(gen, False, False, 0)
        grid.attach(tok_box, 1, 2, 2, 1)

        grid.attach(Gtk.Label(label="Start server with daemon",
                              xalign=0), 0, 3, 1, 1)
        self.autostart_switch = Gtk.Switch(halign=Gtk.Align.START)
        self.autostart_switch.connect("notify::active", self._mark_dirty)
        grid.attach(self.autostart_switch, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label="Passwordless sudo for this user",
                              xalign=0), 0, 4, 1, 1)
        self._pls = False
        self.sudo_btn = Gtk.Button(label="…", halign=Gtk.Align.START)
        self.sudo_btn.connect("clicked", self._on_sudo_clicked)
        grid.attach(self.sudo_btn, 1, 4, 1, 1)

        self.warn_label = Gtk.Label(name="warn", label="", xalign=0)
        root.pack_start(self.warn_label, False, False, 0)

        apply_btn = Gtk.Button(label="Apply settings")
        apply_btn.connect("clicked", self._on_apply)
        root.pack_start(apply_btn, False, False, 0)
        root.pack_start(Gtk.Separator(), False, False, 4)

        # ---- server controls ----
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.start_btn = Gtk.Button(label="Start Server")
        self.start_btn.connect("clicked",
                               lambda *_: self._cmd({"cmd": "start_server"}))
        self.stop_btn = Gtk.Button(label="Stop Server")
        self.stop_btn.connect("clicked",
                              lambda *_: self._cmd({"cmd": "stop_server"}))
        self.daemon_btn = Gtk.Button(label="Start Daemon")
        self.daemon_btn.connect("clicked", self._on_start_daemon)
        self.quit_btn = Gtk.Button(label="Quit Daemon")
        self.quit_btn.connect("clicked", self._on_quit_daemon)
        btns.pack_start(self.start_btn, True, True, 0)
        btns.pack_start(self.stop_btn, True, True, 0)
        btns.pack_start(self.daemon_btn, True, True, 0)
        btns.pack_start(self.quit_btn, True, True, 0)
        root.pack_start(btns, False, False, 0)

        # ---- log view ----
        frame = Gtk.Frame(label="Activity log")
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.log_view = Gtk.TextView(name="logview")
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.log_buf = self.log_view.get_buffer()
        scroll.add(self.log_view)
        frame.add(scroll)
        root.pack_start(frame, True, True, 0)

        self.connect("delete-event", self._on_close)
        self._try_tray()
        self.refresh_all()
        GLib.timeout_add(2000, self._tick)

    # ----- tray (optional) -----

    def _try_tray(self) -> None:
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AI
        except (ImportError, ValueError):
            try:
                gi.require_version("AppIndicator3", "0.1")
                from gi.repository import AppIndicator3 as AI
            except (ImportError, ValueError):
                return
        ind = AI.Indicator.new(
            "linuxmcp", "utilities-terminal",
            AI.IndicatorCategory.APPLICATION_STATUS)
        ind.set_status(AI.IndicatorStatus.ACTIVE)
        menu = Gtk.Menu()
        for label, cb in (("Show", lambda *_: self.present()),
                          ("Start Server",
                           lambda *_: self._cmd({"cmd": "start_server"})),
                          ("Stop Server",
                           lambda *_: self._cmd({"cmd": "stop_server"})),
                          ("Quit Window", lambda *_: self.destroy())):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb)
            item.show()
            menu.append(item)
        ind.set_menu(menu)
        self._tray = ind

    # ----- daemon communication -----

    def _cmd(self, payload: dict) -> dict:
        try:
            return send_command(payload, timeout=5.0)
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def _on_start_daemon(self, *_a) -> None:
        try:
            ensure_daemon()
        except Exception as e:
            self._append_log(f"error starting daemon: {e}")
        self.refresh_all()

    def _on_quit_daemon(self, *_a) -> None:
        self._cmd({"cmd": "shutdown"})
        self.refresh_all()

    def _mark_dirty(self, *_a) -> None:
        # programmatic syncs from refresh_all must not count as user edits
        if not getattr(self, "_syncing", False):
            self._dirty = True

    def _on_apply(self, *_a) -> None:
        self._dirty = False
        token = self.token_entry.get_text().strip()
        self._cmd({"cmd": "set_config", "config": {
            "port": int(self.port_spin.get_value()),
            "remote": self.remote_switch.get_active(),
            "auth_token": token if token else None,
            "autostart_server": self.autostart_switch.get_active(),
        }})
        self.refresh_all()

    def _on_sudo_clicked(self, *_a) -> None:
        want = not self._pls
        r = self._cmd({"cmd": "set_config",
                       "config": {"passwordless_sudo": want}})
        if not r.get("ok"):
            self._append_log(f"sudo toggle failed: {r.get('error')}")
        self.refresh_all()

    def _on_remote_toggled(self, *_a) -> None:
        self._update_warning()

    def _update_warning(self) -> None:
        remote = self.remote_switch.get_active()
        token = self.token_entry.get_text().strip()
        if remote and not token and self._pls:
            self.warn_label.set_text(
                "Warning: unauthenticated LAN access WITH passwordless "
                "sudo = remote root for anyone on the network.")
        elif remote and not token:
            self.warn_label.set_text(
                "Warning: remote connections without an auth token are "
                "unauthenticated. Anyone on the network can control this "
                "machine.")
        elif remote:
            self.warn_label.set_text(
                "Remote enabled: only LAN clients with the bearer token "
                "can connect.")
        else:
            self.warn_label.set_text("")

    # ----- refresh -----

    def refresh_all(self) -> None:
        if not daemon_running():
            self._daemon_up = self._server_up = False
            self.status_label.set_text("Daemon: not running")
            self.url_label.set_text("Start the daemon to control LinuxMCP")
            self.net_label.set_text("")
            self._sync_buttons()
            return
        try:
            st = send_command({"cmd": "status"}, timeout=3.0)
        except OSError:
            return
        srv = st.get("server", {})
        cfg = st.get("config", {})
        self._daemon_up = True
        self._server_up = bool(srv.get("running"))
        self.status_label.set_text(
            "Server: RUNNING" if self._server_up
            else "Server: stopped (daemon running)")
        port = cfg.get("port", 3939)
        remote = cfg.get("remote")
        if self._server_up:
            url = f"http://127.0.0.1:{port}/mcp"
            ips = _local_ips()
            lines = [f"local:   {url}   (health: /health)"]
            for ip in ips:
                if remote:
                    lines.append(f"remote:  http://{ip}:{port}/mcp")
            if remote and not ips:
                lines.append("remote: no LAN address found")
            self.net_label.set_text("\n".join(lines))
            self.url_label.set_text(
                f"bound to {'0.0.0.0 (LAN-visible)' if remote else '127.0.0.1 (local only)'}"
                + ("  •  bearer token required" if srv.get("auth_required") else ""))
        else:
            self.url_label.set_text("server is stopped")
            self.net_label.set_text("")
        # reflect config into controls (without clobbering user input that
        # hasn't been Applied yet - SapperMCP: _dirty guard)
        if not getattr(self, "_dirty", False):
            self._syncing = True
            try:
                self.port_spin.set_value(port)
                self.remote_switch.set_active(bool(remote))
                self.autostart_switch.set_active(
                    bool(cfg.get("autostart_server")))
            finally:
                self._syncing = False
        if cfg.get("auth_token") and not self.token_entry.has_focus():
            if not self.token_entry.get_text():
                self.token_entry.set_placeholder_text(
                    "token set (hidden) - type to replace")
        elif not cfg.get("auth_token"):
            self.token_entry.set_placeholder_text("empty = no auth")
        self._pls = bool(st.get("passwordless_sudo"))
        self.sudo_btn.set_label(
            "Enabled - click to disable" if self._pls
            else "Disabled - click to enable")
        self._update_warning()
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.start_btn.set_sensitive(self._daemon_up and not self._server_up)
        self.stop_btn.set_sensitive(self._daemon_up and self._server_up)
        self.daemon_btn.set_sensitive(not self._daemon_up)
        self.quit_btn.set_sensitive(self._daemon_up)

    def _append_log(self, text: str) -> None:
        end = self.log_buf.get_end_iter()
        self.log_buf.insert(end, text + "\n")
        # keep buffer bounded
        if self.log_buf.get_line_count() > 3000:
            start = self.log_buf.get_start_iter()
            cut = self.log_buf.get_iter_at_line(500)
            self.log_buf.delete(start, cut)
        self.log_view.scroll_to_iter(self.log_buf.get_end_iter(),
                                   0.0, False, 0, 0)

    def _tick(self) -> bool:
        self.refresh_all()
        if self._daemon_up:
            r = self._cmd({"cmd": "logs", "since": self._log_since})
            if r.get("ok"):
                for line in r.get("lines", []):
                    self._append_log(line)
                self._log_since = r.get("next", self._log_since)
        return True

    def _on_close(self, *_a) -> bool:
        if self._tray is not None:
            self.hide()
            return True  # keep running in tray
        return False


def main() -> None:
    win = LinuxMcpWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
