# SapperMCP - agent notes

Merged project: the **sapper-v2** autonomous pentest toolkit (top-level
`lib/`, `kb/`, `templates/`, `docker/`, `skill/`, `tests/`, `install.sh` —
kept verbatim) + a vendored **LinuxMCP** package (`linuxmcp/`, untouched
upstream code) + the **`sappermcp`** package that serves both on one FastMCP
server.

## Layout
- `lib/sapper.py` — the sapper CLI (~4.7k lines, pure stdlib, POSIX-only
  because of `fcntl`). ~30 subcommands; `Store` is the structured API.
- `lib/arena.py`, `lib/kb.py` — loaded by sapper via importlib from its own
  dir; keep them next to `sapper.py`.
- `sappermcp/paths.py` — finds the toolkit: `$SAPPER_ROOT`, else the repo
  root (the dir holding `lib/sapper.py`).
- `sappermcp/core/` — `sapperlib.py` (lazy importlib loaders — NEVER import
  `lib/sapper.py` at module top level; it breaks on Windows/macOS and at
  `--list-tools` time), `runner.py` (CLI subprocess + PTY background),
  `report.py` (markdown engagement report).
- `sappermcp/tools/` — `@mcp.tool` wrappers; each module has `register(mcp)`,
  wired in `tools/__init__.py:register_all`.
- `sappermcp/server.py` — FastMCP assembly, stdio/http, bearer auth,
  /health + /, `--no-linux` for sapper-only, `--list-tools`.
- `sappermcp/gui.py` — GTK control panel (`sappermcp-gui`). Subclasses
  `linuxmcp.gui.LinuxMcpWindow`, reparents its controls into a Notebook:
  page 1 "Sapper" = spec-driven builder for ALL sapper subcommands
  (`COMMANDS` table = every CLI option), page 2 "Server" = the original
  daemon/server panel. Stdlib + PyGObject only; its bootstrap re-execs
  `-m sappermcp.gui` BEFORE linuxmcp.gui is imported (order matters —
  linuxmcp's bootstrap would re-exec the wrong module).
- `linuxmcp/` — vendored system/desktop toolset; treat as upstream, don't
  edit casually (real upstream: the LinuxMCP repo). Deliberate local edits:
  `daemon.py::_child_argv` spawns `-m sappermcp` (merged server, not
  linuxmcp-only), `daemon.py::SUDOERS_FILE` is `99-sappermcp`, and
  `control.py` uses the `sappermcp` namespace (config dir, state dir,
  `sappermcp.sock`, port 3940) so it does NOT fight a stock LinuxMCP
  daemon over settings. `gui.py::refresh_all` guards control syncs with
  `_dirty`/`_syncing` so the 2s refresh stops reverting un-Applied
  user input (upstream bug: toggles flipped back before Apply).

## Conventions
- Same contract as LinuxMCP: tools return JSON strings, always `"ok"`.
- Errors returned, not raised: `{"ok": false, "error": ...}`.
- Every sapper tool takes `store` (path to `.sapper/`, default `.sapper`);
  long-running commands take `cwd` + `background` + `exec_timeout`.
- `background=True` launches the CLI inside a linuxmcp PTY session
  (`linuxmcp.core.shell.start_session`) — returns `session_id`.
- New sapper_* tools: prefer calling `Store`/render functions directly for
  CRUD; use `run_sapper(argv)` for anything that spawns agents/tmux or has
  non-trivial cmd_* orchestration. Never reimplement cmd_* logic.
- Tool names: `sapper_*` for the toolkit; linuxmcp names are unprefixed.

## Build & test (Windows dev box, WSL Ubuntu for running)
```bash
# deps live in a WSL venv (first time only)
wsl -d Ubuntu -- bash -c "python3 -m venv /tmp/sappermcp-venv && /tmp/sappermcp-venv/bin/pip install fastmcp mss pillow psutil"

# compile check
wsl -d Ubuntu -- bash -c "cd /mnt/c/Users/Davy/Documents/GitHub/SapperMCP && /tmp/sappermcp-venv/bin/python -m compileall -q sappermcp linuxmcp"

# tool registry check (~125 tools)
wsl -d Ubuntu -- bash -c "cd /mnt/c/Users/Davy/Documents/GitHub/SapperMCP && PYTHONPATH=. /tmp/sappermcp-venv/bin/python -m sappermcp --list-tools"

# end-to-end: start `python -m sappermcp --http --port 3940` then run
# tests/smoke_test_mcp.py with the venv python
```

## Gotchas
- `sappermcp.tools` imports `linuxmcp.util` only — safe everywhere.
  `linuxmcp.tools` (and `linuxmcp.core.shell`) need POSIX; only imported
  when linux toolset is enabled or a background session is requested.
- FastMCP 4.x: `mcp.list_tools()` is async; `custom_route` needs starlette
  Request/Response.
- `--store` is a GLOBAL arg: `sapper --store <path> <cmd>`, not after.
- `sapper` command/ sweep/ bench take `--root` relative to their `cwd` —
  the MCP wrappers require an explicit `cwd` for those.
