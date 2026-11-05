#!/usr/bin/env bash
# install.sh — SapperMCP installer: `sapper` CLI + project skill + the merged
# MCP server (sappermcp / sappermcp-gui) in a repo-local .venv.
#
# This installer does NOT touch ~/.claude/settings.json and does NOT register
# any global hooks. The fact-graph is strictly per-project opt-in: you opt a
# project in by running `sapper setup` (or the /sapper-setup skill) inside that
# project, which writes ./.claude/settings.json + .sapper/ there.
#
# Usage:
#   bash install.sh              # install CLI + skill + MCP server (recommended)
#   bash install.sh --cli-only   # just the sapper CLI + skill, skip the MCP parts
#   bash install.sh --uninstall  # remove everything this script installed
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${SCRIPT_DIR}/lib/sapper.py"
VENV="${SCRIPT_DIR}/.venv"
BIN_DIR="${HOME}/.local/bin"
mode="${1:-install}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "install: python3 is required (stdlib only, no pip)." >&2
  exit 1
fi

path_hint() {
  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "install: NOTE — $BIN_DIR is not on your PATH. Add:" >&2
       echo "    export PATH=\"$BIN_DIR:\$PATH\"" >&2 ;;
  esac
}

# --- uninstall -------------------------------------------------------------
if [[ "$mode" == "--uninstall" ]]; then
  for link in sapper sappermcp sappermcp-gui; do
    if [[ -L "$BIN_DIR/$link" || -e "$BIN_DIR/$link" ]]; then
      rm -f "$BIN_DIR/$link"
      echo "removed $BIN_DIR/$link"
    fi
  done
  if [[ -e "${HOME}/.claude/skills/sapper-setup" || -L "${HOME}/.claude/skills/sapper-setup" ]]; then
    rm -f "${HOME}/.claude/skills/sapper-setup"
    echo "removed ~/.claude/skills/sapper-setup"
  fi
  DESK="${HOME}/.local/share/applications/sappermcp.desktop"
  if [[ -e "$DESK" ]]; then
    rm -f "$DESK"
    echo "removed $DESK"
  fi
  if [[ -d "$VENV" ]]; then
    rm -rf "$VENV"
    echo "removed $VENV"
  fi
  echo "uninstalled."
  echo "(Project-level .sapper/ graphs and ./.claude/settings.json in your projects are untouched."
  echo " Remove them per-project with: cd <project> && sapper teardown --purge)"
  exit 0
fi

# --- install the sapper CLI -------------------------------------------------
if [[ ! -f "$SRC" ]]; then
  echo "install: sapper.py not found at $SRC" >&2; exit 1
fi

mkdir -p "$BIN_DIR"
if [[ -e "$BIN_DIR/sapper" || -L "$BIN_DIR/sapper" ]]; then
  rm -f "$BIN_DIR/sapper"
fi
ln -s "$SRC" "$BIN_DIR/sapper"
chmod +x "$SRC"
echo "installed: sapper -> $BIN_DIR/sapper"

if [[ "$mode" == "--cli-only" ]]; then
  path_hint
  "$BIN_DIR/sapper" --version >/dev/null && echo "  (sapper works)"
  echo "(--cli-only: skipping the /sapper-setup skill and the MCP server)"
  exit 0
fi

# --- install the project skill ---------------------------------------------
SKILLS_DIR="${HOME}/.claude/skills"
mkdir -p "$SKILLS_DIR"
SKILL_LINK="$SKILLS_DIR/sapper-setup"
if [[ -e "$SKILL_LINK" || -L "$SKILL_LINK" ]]; then
  rm -f "$SKILL_LINK"
fi
ln -s "${SCRIPT_DIR}/skill" "$SKILL_LINK"
echo "installed: /sapper-setup skill -> $SKILL_LINK"

# --- install the MCP server (venv + package) --------------------------------
mcp_ok=1
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "creating venv at $VENV ..."
  if ! python3 -m venv "$VENV"; then
    mcp_ok=0
    echo "install: WARNING — could not create a venv. On Debian/Ubuntu:" >&2
    echo "    sudo apt install python3-venv" >&2
    echo "  then re-run: bash install.sh" >&2
  fi
fi

if [[ "$mcp_ok" == 1 ]]; then
  echo "installing sappermcp (editable) into the venv ..."
  # env -u PYTHONPATH: a foreign PYTHONPATH (e.g. another tool's venv) leaks
  # its site-packages into the venv's pip and breaks the install.
  if env -u PYTHONPATH "$VENV/bin/python" -m pip install -q --upgrade pip && \
     env -u PYTHONPATH "$VENV/bin/python" -m pip install -q -e "$SCRIPT_DIR"; then
    for entry in sappermcp sappermcp-gui; do
      if [[ -e "$BIN_DIR/$entry" || -L "$BIN_DIR/$entry" ]]; then
        rm -f "$BIN_DIR/$entry"
      fi
      ln -s "$VENV/bin/$entry" "$BIN_DIR/$entry"
      echo "installed: $entry -> $BIN_DIR/$entry"
    done
  else
    mcp_ok=0
    echo "install: WARNING — pip install failed (offline?). Retry manually:" >&2
    echo "    $VENV/bin/pip install -e $SCRIPT_DIR" >&2
  fi
fi

# --- GTK check for the GUI ---------------------------------------------------
if [[ "$mcp_ok" == 1 ]]; then
  if /usr/bin/python3 -c 'import gi; gi.require_version("Gtk","3.0")' \
      >/dev/null 2>&1; then
    echo "gtk3: ok (sappermcp-gui will run)"
  else
    echo "install: NOTE — sappermcp-gui needs PyGObject + GTK3:" >&2
    echo "    sudo apt install python3-gi gir1.2-gtk-3.0" >&2
    echo "  (the CLI and MCP server work without it)" >&2
  fi

  # --- desktop launcher -----------------------------------------------------
  APPS_DIR="${HOME}/.local/share/applications"
  mkdir -p "$APPS_DIR"
  cat > "${APPS_DIR}/sappermcp.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=SapperMCP Control
Comment=Control panel for the merged Sapper + LinuxMCP server and the sapper CLI
Exec=${VENV}/bin/sappermcp-gui
Path=${SCRIPT_DIR}
Icon=utilities-terminal
Terminal=false
Categories=Development;Network;Utility;
Keywords=mcp;ai;debug;server;security;
StartupNotify=true
DESK
  echo "installed: desktop launcher -> ${APPS_DIR}/sappermcp.desktop"
  command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

path_hint
"$BIN_DIR/sapper" --version >/dev/null && echo "  (sapper works)"

cat <<'NOTE'

Done. Nothing global was configured — the fact-graph is per-project opt-in.

To opt a project IN (run inside the project dir):
  sapper setup --goal "your one-line goal" --agents
  #  ↑ creates ./.sapper/  +  registers hooks in ./.claude/settings.json  +  AGENTS.md

Or just invoke the skill from inside Claude Code:
  /sapper-setup <your goal>

After that, every turn in that project auto-injects the current graph state,
and you can drive it with `sapper dispatch reason` / `sapper auto`.

To opt a project OUT:
  cd <project> && sapper teardown           # removes hooks + AGENTS.md (keeps .sapper/)
  cd <project> && sapper teardown --purge   # also deletes the graph data

MCP server (installed into .venv in this repo):
  sappermcp --http --port 3940   # merged server: all sapper_* + linuxmcp tools
  sappermcp --stdio              # stdio transport for local clients
  sappermcp-gui                  # control panel: Sapper builder + server tabs
See the "SapperMCP" section of README.md for client configs and workflows.
NOTE
