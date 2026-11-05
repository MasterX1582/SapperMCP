"""sappermcp-gui - GTK control panel for SapperMCP.

Page 1 ("Sapper") is a spec-driven builder for the whole `sapper` CLI: pick a
project dir + store, choose a subcommand, fill in its options, run it, and
watch streamed output. Page 2 ("Server") is the LinuxMCP daemon/server panel
from linuxmcp.gui, reparented unchanged - the daemon it controls supervises
the merged `python -m sappermcp` server (all 127 tools).

Pure stdlib + PyGObject: no fastmcp imports, so the app can re-exec itself
under the system Python (/usr/bin/python3, which has python3-gi on
Ubuntu/Zorin) with the repo root on PYTHONPATH. The bootstrap below must run
BEFORE linuxmcp.gui is imported - its own bootstrap would re-exec into the
wrong module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_gi() -> None:
    try:
        import gi  # noqa: F401
        return
    except ImportError:
        pass
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_parent + os.pathsep + env.get("PYTHONPATH", "")
    for py in ("/usr/bin/python3", "/usr/bin/python"):
        if os.path.exists(py):
            os.execve(py, [py, "-m", "sappermcp.gui"], env)
    raise SystemExit(
        "PyGObject (python3-gi) not found.\n"
        "Install it with: sudo apt install python3-gi gir1.2-gtk-3.0")


_bootstrap_gi()

import gi  # noqa: E402

try:
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
except ValueError:
    raise SystemExit(
        "GTK 3 typelibs not found.\n"
        "Install them with: sudo apt install gir1.2-gtk-3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from linuxmcp.gui import LinuxMcpWindow  # noqa: E402

from .paths import sapper_cli  # noqa: E402


# --------------------------------------------------------------------------- #
# command spec - every `sapper` subcommand with all its CLI options
#
# arg dict keys:
#   pos=<name>    positional argument (req=True -> must be non-empty)
#   flag=<--opt>  optional flag
#   kind: text (default) | int | switch | combo | poscombo | multi | file | dir
#   default       for int/text widgets (matches the CLI default; unchanged
#                 int fields are not emitted)
#   choices       for combo/poscombo ("" in a combo = omit the flag)
# --------------------------------------------------------------------------- #

def _pos(name, req=False, ph=""):
    return {"pos": name, "req": req, "help": ph}


def _posc(name, choices):
    return {"pos": name, "req": True, "kind": "poscombo", "choices": choices}


def _f(flag, label, kind="text", **kw):
    return {"flag": flag, "label": label, "kind": kind, **kw}


def _sw(flag, label):
    return _f(flag, label, "switch")


def _int(flag, label, default=0, lo=0, hi=999999):
    return _f(flag, label, "int", default=default, lo=lo, hi=hi)


def _multi(flag, label):
    return _f(flag, label, "multi", ph="comma-separated, emitted per item")


def _file(flag, label, save=False):
    return _f(flag, label, "file", save=save)


def _dir(flag, label):
    return _f(flag, label, "dir")


_FACT_KINDS = ["", "host", "service", "cred", "vuln", "loot", "flag", "note"]


def _kind_arg():
    return _f("--kind", "kind", "combo", choices=list(_FACT_KINDS))


COMMANDS: dict[str, dict] = {
    "init": {"desc": "create a fact graph in the store", "args": [
        _f("--goal", "goal", ph="one-line terminal goal", req=True),
        _f("--origin", "origin"),
        _sw("--force", "overwrite existing graph"),
    ]},
    "status": {"desc": "project + frontier summary", "args": []},
    "graph": {"desc": "dump the graph", "args": [
        _f("--format", "format", "combo", choices=["text", "json"]),
    ]},
    "validate": {"desc": "integrity-check the graph", "args": []},
    "frontier": {"desc": "open intents ready to work", "args": []},
    "pick": {"desc": "pick the next intent to work (prints id)", "args": [
        _sw("--claim", "claim it for this agent"),
        _sw("--any", "include unconfirmed/blocked open intents"),
        _f("--worker", "worker"),
    ]},
    "fact": {"desc": "record a confirmed fact", "args": [
        _pos("description", req=True, ph="one-sentence gist"),
        _f("--title", "title"),
        _kind_arg(),
        _multi("--data", "data KEY=VALUE"),
        _f("--doc", "doc (markdown)"),
        _file("--doc-file", "doc file"),
        _f("--creator", "creator", default="gui"),
        _f("--from-intent", "from intent id"),
        _sw("--json", "json output"),
    ]},
    "intent": {"desc": "add an intent (a unit of work)", "args": [
        _f("--from", "from fact ids", req=True, ph="f001,f002"),
        _pos("description", req=True),
        _f("--title", "title"),
        _f("--doc", "doc (markdown)"),
        _file("--doc-file", "doc file"),
        _f("--creator", "creator", default="gui"),
        _sw("--confirm", "requires confirmation"),
        _sw("--json", "json output"),
    ]},
    "hint": {"desc": "add or list human hints", "args": [
        _pos("content", ph="hint text (empty with --list)"),
        _f("--creator", "creator", default="gui"),
        _sw("--list", "list hints"),
    ]},
    "peers": {"desc": "discover tmux panes / manage authorized AI peers",
              "args": [
        _sw("--discover", "list all tmux panes"),
        _f("--add", "authorize peer NAME"),
        _f("--remove", "remove peer NAME"),
        _f("--target", "tmux target for --add", ph="api-6:0.0"),
        _f("--sender", "sender label"),
        _f("--channel", "shared log path"),
        _f("--note", "note about the peer"),
        _sw("--json", "json output"),
    ]},
    "send": {"desc": "send a message to an authorized tmux peer", "args": [
        _pos("peer", req=True),
        _pos("message", req=True),
        _f("--sender", "override sender label"),
        _f("--channel", "override log path"),
        _sw("--no-log", "do not append to the shared log"),
        _sw("--raw", "no timestamp/sender prefix"),
    ]},
    "capture": {"desc": "read recent output from an authorized peer", "args": [
        _pos("peer", req=True),
        _int("--lines", "lines", default=120, lo=1, hi=2000),
        _f("--channel", "override log path (with --log)"),
        _sw("--log", "append captured output to the log"),
    ]},
    "show": {"desc": "show project | fact <id> | intent <id>", "args": [
        _posc("entity", ["project", "fact", "intent"]),
        _pos("id", ph="f001 / i003"),
    ]},
    "doc": {"desc": "read or write a node's detailed doc", "args": [
        _pos("id", req=True, ph="f001 / i003 / goal"),
        _f("--set", "set doc body to text"),
        _file("--set-file", "set doc from file"),
        _sw("--edit", "open doc in $EDITOR"),
    ]},
    "recall": {"desc": "find prior facts/intents similar to a query", "args": [
        _pos("query", req=True, ph="free-text task gist"),
        _int("--limit", "limit", default=5, lo=1, hi=100),
        _f("--kind", "kind", "combo", choices=["any", "fact", "intent"]),
        _sw("--json", "json output"),
    ]},
    "claim": {"desc": "claim an open intent", "args": [
        _pos("id", req=True),
        _f("--worker", "worker", req=True),
    ]},
    "release": {"desc": "release a claimed intent", "args": [
        _pos("id", req=True),
        _f("--worker", "worker"),
    ]},
    "done": {"desc": "conclude an intent with the fact it produced", "args": [
        _pos("id", req=True),
        _f("--fact", "confirmed result", req=True),
        _f("--title", "title"),
        _kind_arg(),
        _multi("--data", "data KEY=VALUE"),
        _f("--doc", "doc (markdown)"),
        _file("--doc-file", "doc file"),
        _f("--worker", "worker", default="gui"),
    ]},
    "complete": {"desc": "mark the project goal satisfied", "args": [
        _f("--from", "justifying fact ids", req=True, ph="f001,f005"),
        _f("--note", "note"),
        _f("--worker", "worker", default="gui"),
    ]},
    "confirm": {"desc": "confirm an intent that required it", "args": [
        _pos("id", req=True),
    ]},
    "dispatch": {"desc": "run a commander/executor step via the agent CLI",
                 "args": [
        _pos("target", req=True,
             ph="reason | verify | blindspot | brainstorm | <intent-id>"),
        _f("--model", "model", ph="$SAPPER_MODEL or 'sonnet'"),
        _int("--timeout", "timeout s", default=600, lo=1),
        _dir("--templates", "templates dir"),
        _sw("--skip-permissions", "skip permissions"),
        _sw("--dry-run", "print prompt and exit"),
        _sw("--claim", "(explore) claim the intent first"),
        _f("--intent", "(verify) intent id"),
        _int("--max-options", "max options (brainstorm)", default=4, lo=1, hi=20),
    ]},
    "brainstorm-pick": {"desc": "pick one brainstorm option, abandon the rest",
                        "args": [_pos("id", req=True, ph="i003")]},
    "setup": {"desc": "opt THIS project in: graph + hooks + AGENTS.md "
                      "(runs in project dir)", "args": [
        _f("--goal", "goal", ph="required if no .sapper/ yet"),
        _f("--origin", "origin"),
        _sw("--agents", "also write AGENTS.md"),
        _sw("--force", "force overwrite AGENTS.md"),
    ]},
    "teardown": {"desc": "remove hooks + AGENTS.md (runs in project dir)",
                 "args": [
        _sw("--purge", "also delete the .sapper/ graph data"),
    ]},
    "view": {"desc": "write/open the interactive HTML graph", "args": [
        _file("--out", "output html", save=True),
        _sw("--serve", "serve a live auto-refreshing page"),
        _f("--host", "host", default="127.0.0.1"),
        _int("--port", "port", default=8765, lo=1, hi=65535),
        _sw("--print", "print html to stdout"),
    ]},
    "flag": {"desc": "record a captured flag (dedupe; optional submit)",
             "args": [
        _pos("value", req=True, ph="flag{...}"),
        _f("--challenge", "challenge id"),
        _sw("--submit", "also submit via the arena API"),
        _f("--title", "title"),
        _f("--creator", "creator", default="gui"),
    ]},
    "arena": {"desc": "competition platform bridge (TSecBench-style API)",
              "args": [
        _posc("action", ["init", "challenges", "start", "stop", "submit",
                         "hint"]),
        _pos("challenge_id", ph="challenge id"),
        _f("--flag", "flag value (submit)"),
    ]},
    "kb": {"desc": "shared offline knowledge base", "args": [
        _posc("action", ["add", "search", "show", "list", "import", "root"]),
        _pos("target", ph="title | kb id | query | import path"),
        _f("--description", "description"),
        _f("--detail", "detail (markdown)"),
        _file("--detail-file", "detail file"),
        _multi("--tag", "tags"),
        _multi("--command", "example commands"),
        _f("--source", "source"),
        _file("--path", "import path"),
        _f("--root", "kb root dir"),
        _int("--limit", "limit", default=5, lo=1, hi=100),
    ]},
    "bench": {"desc": "TSecBench end-to-end driver "
                      "(list->start->solve->submit->close)", "args": [
        _f("--root", "per-challenge root", default="runs"),
        _int("--minutes", "global budget (min)"),
        _f("--deadline", "deadline (ISO 8601)"),
        _int("--minutes-per-challenge", "min / challenge", default=25, lo=1),
        _int("--max-steps", "max steps", default=10, lo=1),
        _int("--round-gap-seconds", "round gap s", default=20),
        _int("--parallel", "parallel workers", default=1, lo=1, hi=64),
        _int("--poll-seconds", "poll s", default=5, lo=1),
        _f("--model", "model"),
        _dir("--templates", "templates dir"),
        _sw("--skip-permissions", "skip permissions"),
        _sw("--verify", "verify each result"),
    ]},
    "command": {"desc": "field commander: LLM allocates work slices across "
                        "challenge graphs", "args": [
        _f("--root", "challenges root", default="runs"),
        _int("--minutes", "global budget (min)"),
        _f("--deadline", "deadline (ISO 8601)"),
        _int("--minutes-default", "min / slice", default=20, lo=1),
        _int("--minutes-max", "max slice (min)", default=40, lo=1),
        _f("--fleet-file", "fleet.json path"),
        _int("--poll-seconds", "poll s", default=30, lo=1),
        _f("--model", "model"),
        _int("--timeout", "agent timeout s", default=600, lo=1),
        _dir("--templates", "templates dir"),
        _sw("--skip-permissions", "skip permissions"),
        _sw("--verify", "verify each result"),
        _int("--max-steps", "max steps", default=8, lo=1),
    ]},
    "fleet": {"desc": "manage the tmux worker fleet", "args": [
        _posc("action", ["init", "up", "down", "status", "hire", "fire",
                         "workers"]),
        _f("--file", "fleet config path"),
        _f("--target", "challenge name (hire/fire)"),
        _int("--minutes", "worker budget (min)"),
        _int("--max-steps", "worker max steps"),
        _f("--extra-args", "extra args for hired auto"),
    ]},
    "sweep": {"desc": "round-robin driver: auto on every challenge graph "
                      "until deadline", "args": [
        _f("--root", "challenges root", default="runs"),
        _int("--minutes", "global budget (min)"),
        _f("--deadline", "deadline (ISO 8601)"),
        _int("--minutes-per", "min per challenge", default=20, lo=1),
        _f("--model", "model"),
        _dir("--templates", "templates dir"),
        _sw("--skip-permissions", "skip permissions"),
        _sw("--verify", "verify each result"),
        _int("--max-steps", "max steps", default=8, lo=1),
    ]},
    "auto": {"desc": "drive a graph toward its goal autonomously "
                     "(reason -> explore -> verify loop)", "args": [
        _f("--model", "model"),
        _int("--timeout", "agent timeout s", default=600, lo=1),
        _dir("--templates", "templates dir"),
        _sw("--skip-permissions", "skip permissions"),
        _sw("--dry-run", "reason only, no explore"),
        _sw("--verify", "verify each explore result"),
        _int("--max-steps", "max reason steps", default=8, lo=1),
        _int("--max-explore", "max explore dispatches", default=6, lo=1),
        _int("--minutes", "budget (min)"),
        _f("--deadline", "deadline (ISO 8601)"),
    ]},
}

COMMAND_ORDER = [
    "status", "init", "setup", "fact", "intent", "done", "frontier", "pick",
    "claim", "release", "confirm", "complete", "hint", "show", "doc",
    "recall", "graph", "validate", "flag", "arena", "kb", "dispatch",
    "brainstorm-pick", "auto", "view", "peers", "send", "capture",
    "fleet", "command", "sweep", "bench", "teardown",
]

CSS = b"""
#sapper-out text { background: #0d1017; color: #d6e2ff; }
#sapper-out { font-family: Monospace; font-size: 11px; }
"""


class SapperMcpWindow(LinuxMcpWindow):
    """The merged control panel: Sapper tab first, LinuxMCP server tab second."""

    def __init__(self) -> None:
        super().__init__()
        self.set_title("SapperMCP Control")
        self.set_default_size(820, 740)

        style = Gtk.CssProvider()
        style.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), style,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # reparent the existing controls into a notebook's second page
        server_page = self.get_children()[0]
        self.remove(server_page)

        self._proc = None
        nb = Gtk.Notebook()
        nb.append_page(self._build_sapper_page(),
                       Gtk.Label(label="Sapper"))
        nb.append_page(server_page, Gtk.Label(label="Server"))
        self.add(nb)

    # ------------------------------------------------------------------ #
    # Sapper page
    # ------------------------------------------------------------------ #

    def _build_sapper_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_border_width(10)

        loc = Gtk.Grid(column_spacing=8, row_spacing=6)
        loc.attach(Gtk.Label(label="Project dir", xalign=0), 0, 0, 1, 1)
        cwd_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.sap_cwd = Gtk.Entry()
        self.sap_cwd.set_text(os.getcwd())
        self.sap_cwd.set_tooltip_text(
            "working directory for the command (setup/teardown/command/"
            "sweep/bench run relative to this)")
        cwd_box.pack_start(self.sap_cwd, True, True, 0)
        browse = Gtk.Button(label="…")
        browse.connect("clicked", self._browse_dir, self.sap_cwd)
        cwd_box.pack_start(browse, False, False, 0)
        loc.attach(cwd_box, 1, 0, 1, 1)

        loc.attach(Gtk.Label(label="Store (.sapper dir)", xalign=0), 0, 1, 1, 1)
        self.sap_store = Gtk.Entry()
        self.sap_store.set_text(".sapper")
        self.sap_store.set_tooltip_text(
            "graph dir passed as --store (relative to project dir)")
        loc.attach(self.sap_store, 1, 1, 1, 1)
        page.pack_start(loc, False, False, 0)

        cmd_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cmd_row.pack_start(Gtk.Label(label="Command"), False, False, 0)
        self.cmd_combo = Gtk.ComboBoxText()
        for name in COMMAND_ORDER:
            self.cmd_combo.append(name, name)
        self.cmd_combo.set_active_id("status")
        self.cmd_combo.connect("changed", self._on_cmd_changed)
        cmd_row.pack_start(self.cmd_combo, False, False, 0)
        self.cmd_desc = Gtk.Label(xalign=0)
        self.cmd_desc.set_line_wrap(True)
        cmd_row.pack_start(self.cmd_desc, True, True, 0)
        page.pack_start(cmd_row, False, False, 0)

        opt_scroll = Gtk.ScrolledWindow()
        opt_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        opt_scroll.set_min_content_height(170)
        self.opt_grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        self.opt_grid.set_border_width(4)
        opt_scroll.add(self.opt_grid)
        page.pack_start(opt_scroll, False, False, 0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.run_btn = Gtk.Button(label="Run")
        self.run_btn.connect("clicked", self._on_run)
        self.kill_btn = Gtk.Button(label="Kill")
        self.kill_btn.set_sensitive(False)
        self.kill_btn.connect("clicked", self._on_kill)
        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", lambda *_:
                          self.sap_buf.set_text(""))
        btn_row.pack_start(self.run_btn, False, False, 0)
        btn_row.pack_start(self.kill_btn, False, False, 0)
        btn_row.pack_start(clear_btn, False, False, 0)
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        btn_row.pack_start(sep, False, False, 4)
        for label, cb in (("Status", "status"), ("Graph", "graph"),
                          ("Frontier", "frontier"), ("Validate", "validate")):
            b = Gtk.Button(label=label)
            b.connect("clicked", self._on_quick, cb)
            btn_row.pack_start(b, False, False, 0)
        for label, cb in (("Board", self._quick_board),
                          ("View", "view"), ("Report", self._quick_report)):
            b = Gtk.Button(label=label)
            b.connect("clicked",
                      cb if callable(cb) else self._on_quick,
                      None if callable(cb) else cb)
            btn_row.pack_start(b, False, False, 0)
        page.pack_start(btn_row, False, False, 0)

        frame = Gtk.Frame(label="Output")
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.sap_view = Gtk.TextView(name="sapper-out")
        self.sap_view.set_editable(False)
        self.sap_view.set_monospace(True)
        self.sap_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.sap_buf = self.sap_view.get_buffer()
        scroll.add(self.sap_view)
        frame.add(scroll)
        page.pack_start(frame, True, True, 0)

        self._opt_fields: list[tuple[dict, Gtk.Widget]] = []
        self._on_cmd_changed(self.cmd_combo)
        return page

    # ----- option form -----

    def _on_cmd_changed(self, combo) -> None:
        name = combo.get_active_text()
        self.cmd_desc.set_text(COMMANDS.get(name, {}).get("desc", ""))
        self._rebuild_options()

    def _rebuild_options(self) -> None:
        for child in list(self.opt_grid.get_children()):
            self.opt_grid.remove(child)
        self._opt_fields = []
        name = self.cmd_combo.get_active_text()
        args = COMMANDS.get(name, {}).get("args", [])
        if not args:
            lbl = Gtk.Label(label="(no options)", xalign=0)
            self.opt_grid.attach(lbl, 0, 0, 2, 1)
        for row, spec in enumerate(args):
            title = spec.get("pos") or spec.get("label") or spec.get("flag")
            if spec.get("req"):
                title += " *"
            lbl = Gtk.Label(label=title, xalign=0)
            if spec.get("help"):
                lbl.set_tooltip_text(spec["help"])
            widget = self._make_widget(spec)
            self.opt_grid.attach(lbl, 0, row, 1, 1)
            self.opt_grid.attach(widget, 1, row, 1, 1)
            self._opt_fields.append((spec, widget))
        self.opt_grid.show_all()

    def _make_widget(self, spec: dict) -> Gtk.Widget:
        kind = spec.get("kind", "text")
        if kind == "switch":
            w = Gtk.Switch(halign=Gtk.Align.START)
        elif kind == "int":
            w = Gtk.SpinButton.new_with_range(spec.get("lo", 0),
                                              spec.get("hi", 999999), 1)
            w.set_value(spec.get("default", 0))
        elif kind in ("combo", "poscombo"):
            w = Gtk.ComboBoxText()
            for c in spec["choices"]:
                w.append(c, c or "(none)")
            w.set_active(0)
        elif kind in ("file", "dir"):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            e = Gtk.Entry()
            box.pack_start(e, True, True, 0)
            b = Gtk.Button(label="…")
            if kind == "dir":
                b.connect("clicked", self._browse_dir, e)
            else:
                b.connect("clicked", self._browse_file, e,
                          bool(spec.get("save")))
            box.pack_start(b, False, False, 0)
            return box
        else:  # text / pos / multi
            w = Gtk.Entry()
            ph = spec.get("help") or spec.get("pos") or ""
            if spec.get("req"):
                ph = (ph + " (required)").strip()
            w.set_placeholder_text(ph)
            if spec.get("default"):
                w.set_text(str(spec["default"]))
        if spec.get("help"):
            w.set_tooltip_text(spec["help"])
        return w

    def _entry_of(self, widget) -> Gtk.Entry:
        return widget if isinstance(widget, Gtk.Entry) \
            else widget.get_children()[0]

    def _collect_argv(self) -> tuple[list[str] | None, str | None]:
        """-> (extra argv, error). Positionals first, then flags."""
        pos, flags = [], []
        for spec, w in self._opt_fields:
            kind = spec.get("kind", "text")
            flag = spec.get("flag")
            if kind == "switch":
                if w.get_active():
                    flags.append(flag)
                continue
            if kind == "int":
                v = int(w.get_value())
                if spec.get("req") or v != spec.get("default", 0):
                    flags += [flag, str(v)]
                continue
            if kind == "poscombo":
                pos.append(w.get_active_id())
                continue
            if kind == "combo":
                v = w.get_active_id()
                if v:
                    flags += [flag, v]
                continue
            # entry-backed kinds: text / pos / multi / file / dir
            v = self._entry_of(w).get_text().strip()
            if spec.get("pos"):
                if spec.get("req") and not v:
                    return None, f"{spec['pos']} is required"
                if v:
                    pos.append(v)
                continue
            if not v:
                if spec.get("req"):
                    return None, f"{spec.get('label') or flag} is required"
                continue
            if kind == "multi":
                for item in v.split(","):
                    item = item.strip()
                    if item:
                        flags += [flag, item]
            else:
                flags += [flag, v]
        return pos + flags, None

    # ----- run / output -----

    def _argv_prefix(self) -> list[str]:
        store = self.sap_store.get_text().strip() or ".sapper"
        return [sys.executable, str(sapper_cli()), "--store", store]

    def _cwd(self) -> str:
        return self.sap_cwd.get_text().strip() or "."

    def _sap_out(self, text: str) -> None:
        end = self.sap_buf.get_end_iter()
        self.sap_buf.insert(end, text)
        if self.sap_buf.get_line_count() > 5000:
            self.sap_buf.delete(self.sap_buf.get_start_iter(),
                                self.sap_buf.get_iter_at_line(1000))
        self.sap_view.scroll_to_iter(self.sap_buf.get_end_iter(),
                                     0.0, False, 0, 0)

    def _start_proc(self, argv: list[str], cwd: str) -> None:
        import shlex
        import subprocess
        import threading
        if self._proc is not None:
            self._sap_out("[still running - Kill it first]\n")
            return
        if not Path(cwd).is_dir():
            self._sap_out(f"[error] project dir not found: {cwd}\n")
            return
        shown = " ".join(shlex.quote(a) for a in argv[1:])
        self._sap_out(f"$ {shown}\n")
        try:
            self._proc = subprocess.Popen(
                argv, cwd=cwd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                start_new_session=True,  # own pgid -> Kill takes children too
            )
        except Exception as exc:
            self._proc = None
            self._sap_out(f"[error] {exc}\n")
            return
        self.run_btn.set_sensitive(False)
        self.kill_btn.set_sensitive(True)

        def pump():
            try:
                for line in self._proc.stdout:
                    GLib.idle_add(self._sap_out, line)
            finally:
                rc = self._proc.wait()
                GLib.idle_add(self._proc_done, rc)

        threading.Thread(target=pump, daemon=True).start()

    def _proc_done(self, rc: int) -> None:
        self._proc = None
        self.run_btn.set_sensitive(True)
        self.kill_btn.set_sensitive(False)
        self._sap_out(f"[exit {rc}]\n\n")

    def _on_run(self, *_a) -> None:
        cmd = self.cmd_combo.get_active_text()
        extra, error = self._collect_argv()
        if error:
            self._sap_out(f"[error] {error}\n")
            return
        self._start_proc(self._argv_prefix() + [cmd] + extra, self._cwd())

    def _on_quick(self, _btn, cmd: str) -> None:
        self._start_proc(self._argv_prefix() + [cmd], self._cwd())

    def _on_kill(self, *_a) -> None:
        import signal
        if self._proc is None:
            return
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                self._proc.kill()
            except Exception:
                pass
        self._sap_out("[killed]\n")

    # ----- quick actions that have no CLI equivalent -----

    def _quick_board(self, *_a) -> None:
        """Commander's board over the project dir (one row per */.sapper)."""
        try:
            from .core.sapperlib import sapper
            mod = sapper()
            rows = mod._board_summary(Path(self._cwd()))
            self._sap_out(mod.render_board(rows) + "\n\n")
        except Exception as exc:
            self._sap_out(f"[board error] {exc}\n")

    def _quick_report(self, *_a) -> None:
        """Generate the markdown engagement report next to the store."""
        try:
            from .core.report import build_report
            from .core.sapperlib import sapper
            mod = sapper()
            store = Path(self._cwd()) / self.sap_store.get_text().strip()
            st = mod.Store(store)
            st.require()
            md = build_report(mod.build_graph_view(st))
            out = store.parent / "sapper-report.md"
            out.write_text(md, encoding="utf-8")
            self._sap_out(f"wrote {out}\n")
            self._try_show_uri(out)
        except Exception as exc:
            self._sap_out(f"[report error] {exc}\n")

    def _try_show_uri(self, path: Path) -> None:
        try:
            Gtk.show_uri_on_window(
                self, path.resolve().as_uri(),
                Gdk.CURRENT_TIME)
        except Exception:
            pass

    # ----- choosers -----

    def _browse_dir(self, _btn, entry: Gtk.Entry) -> None:
        self._choose(entry, Gtk.FileChooserAction.SELECT_FOLDER,
                     "Choose directory")

    def _browse_file(self, _btn, entry: Gtk.Entry, save: bool) -> None:
        action = (Gtk.FileChooserAction.SAVE if save
                  else Gtk.FileChooserAction.OPEN)
        self._choose(entry, action, "Choose file")

    def _choose(self, entry: Gtk.Entry, action, title: str) -> None:
        dlg = Gtk.FileChooserDialog(
            title=title, parent=self, action=action)
        dlg.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                        "_Select", Gtk.ResponseType.OK)
        if action == Gtk.FileChooserAction.SAVE:
            dlg.set_do_overwrite_confirmation(True)
        cur = entry.get_text().strip()
        if cur and Path(cur).expanduser().exists():
            p = Path(cur).expanduser()
            dlg.set_current_folder(str(p if p.is_dir() else p.parent))
        if dlg.run() == Gtk.ResponseType.OK:
            entry.set_text(dlg.get_filename())
        dlg.destroy()


def main() -> None:
    win = SapperMcpWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
