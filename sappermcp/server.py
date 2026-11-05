"""SapperMCP server entry point: one FastMCP exposing the embedded LinuxMCP
system-control toolset plus the full sapper-v2 toolkit as sapper_* tools."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__, tools as sapper_tools
from .paths import sapper_root

INSTRUCTIONS = """\
SapperMCP merges two toolsets on one MCP server:

1. The sapper-v2 autonomous pentest toolkit (sapper_* tools): a fact-intent
   working memory (init/fact/intent/done/status/graph/recall/doc), a flag
   ledger, a TSecBench-style arena bridge, an offline knowledge base, agent
   dispatch/auto loops, tmux peer messaging, multi-challenge orchestrators
   (fleet/command/sweep/bench), and reporting (view/board/report). Use these
   for authorized security testing, app debugging, and hardening work.

2. The LinuxMCP system toolset: shell commands and PTY sessions, filesystem,
   processes, systemd services, journald, apt packages, GNOME settings, and
   desktop control (screenshots, windows, input, clipboard).

Results are JSON; always check "ok". Graph tools take `store` = path to a
.sapper/ dir (default .sapper). Long runs (auto/command/sweep/bench/dispatch):
pass background=True to get a PTY session_id, then poll read_session_output.
Privileged ops need passwordless sudo or LINUXMCP_SUDO_PASSWORD on the server.
"""

DEFAULT_PORT = 3940


def create_server(auth_token: Optional[str] = None,
                  include_linux: bool = True) -> FastMCP:
    auth = None
    if auth_token:
        from fastmcp.server.auth import StaticTokenVerifier
        auth = StaticTokenVerifier(
            tokens={auth_token: {"client_id": "sappermcp-client",
                                 "scopes": ["sappermcp"]}})

    mcp = FastMCP(
        name="SapperMCP",
        version=__version__,
        instructions=INSTRUCTIONS,
        auth=auth,
    )

    toolsets = ["sapper"]
    sapper_tools.register_all(mcp)
    if include_linux:
        import linuxmcp.tools
        linuxmcp.tools.register_all(mcp)
        toolsets.append("linuxmcp")

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy",
                             "server": "SapperMCP",
                             "version": __version__,
                             "sapper_root": str(sapper_root()),
                             "toolsets": toolsets})

    @mcp.custom_route("/", methods=["GET"])
    async def _info(_request: Request) -> JSONResponse:
        return JSONResponse({
            "server": "SapperMCP",
            "version": __version__,
            "protocol": "MCP",
            "transport": "streamable-http",
            "toolsets": toolsets,
            "sapper_root": str(sapper_root()),
            "endpoints": {"mcp": "/mcp", "health": "/health"},
        })

    return mcp


def _apply_display_env(args: argparse.Namespace) -> None:
    """Allow reaching the user's X session when started from SSH/systemd."""
    display = args.display or os.environ.get("SAPPERMCP_DISPLAY") \
        or os.environ.get("LINUXMCP_DISPLAY")
    xauthority = args.xauthority or os.environ.get("SAPPERMCP_XAUTHORITY") \
        or os.environ.get("LINUXMCP_XAUTHORITY")
    if display:
        os.environ["DISPLAY"] = display
    if xauthority:
        os.environ["XAUTHORITY"] = xauthority
    if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime and os.path.exists(os.path.join(runtime, "bus")):
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sappermcp",
        description="SapperMCP - sapper-v2 pentest toolkit + LinuxMCP system "
                    "control, on one MCP server.")
    transport = p.add_mutually_exclusive_group()
    transport.add_argument("--stdio", action="store_true",
                           help="serve over stdio (default)")
    transport.add_argument("--http", "--network", dest="http",
                           action="store_true",
                           help="serve over HTTP (streamable-http MCP)")
    p.add_argument("--host", default="0.0.0.0",
                   help="HTTP listen address (default 0.0.0.0)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"HTTP port (default {DEFAULT_PORT})")
    p.add_argument("--path", default="/mcp",
                   help="HTTP MCP endpoint path (default /mcp)")
    p.add_argument("--auth-token",
                   default=os.environ.get("SAPPERMCP_AUTH_TOKEN"),
                   help="require Bearer token for HTTP "
                        "(or set SAPPERMCP_AUTH_TOKEN)")
    p.add_argument("--no-linux", action="store_true",
                   help="expose only the sapper_* tools (skip the LinuxMCP "
                        "system/desktop toolset)")
    p.add_argument("--display",
                   help="X display for desktop tools, e.g. :0 "
                        "(or SAPPERMCP_DISPLAY)")
    p.add_argument("--xauthority",
                   help="X authority file for desktop tools "
                        "(or SAPPERMCP_XAUTHORITY)")
    p.add_argument("--log-level",
                   default=os.environ.get("SAPPERMCP_LOG_LEVEL", "info"),
                   help="uvicorn/mcp log level (default info)")
    p.add_argument("--list-tools", action="store_true",
                   help="print registered tools and exit")
    p.add_argument("--version", action="version",
                   version=f"sappermcp {__version__}")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    _apply_display_env(args)

    mcp = create_server(auth_token=args.auth_token,
                        include_linux=not args.no_linux)

    if args.list_tools:
        import asyncio
        names = sorted(t.name for t in asyncio.run(mcp.list_tools()))
        for name in names:
            print(name)
        print(f"{len(names)} tools", file=sys.stderr)
        return

    if args.http:
        if args.auth_token:
            print("HTTP auth: Bearer token required", file=sys.stderr)
        else:
            print("WARNING: HTTP transport without --auth-token is "
                  "unauthenticated. Use only on trusted networks.",
                  file=sys.stderr)
        mcp.run(transport="http", host=args.host, port=args.port,
                path=args.path, log_level=args.log_level)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
