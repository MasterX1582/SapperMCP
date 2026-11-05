"""LinuxMCP server entry point: transports, auth, diagnostics."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__, tools

INSTRUCTIONS = """\
LinuxMCP gives you full control of this Linux machine for debugging and
administration: run shell commands (one-shot or interactive PTY sessions),
read/write the filesystem, manage processes, systemd services, journald
logs, apt packages, GNOME settings, and the desktop (screenshots, windows,
mouse/keyboard input, clipboard).

Results are JSON. Always check "ok" before assuming success. Commands that
need root use sudo: passwordless sudo or the LINUXMCP_SUDO_PASSWORD env var
must be configured on the server. Desktop tools need a display; call
get_desktop_status first if they fail.
"""


def create_server(auth_token: Optional[str] = None) -> FastMCP:
    auth = None
    if auth_token:
        from fastmcp.server.auth import StaticTokenVerifier
        auth = StaticTokenVerifier(
            tokens={auth_token: {"client_id": "linuxmcp-client",
                                 "scopes": ["linuxmcp"]}})

    mcp = FastMCP(
        name="LinuxMCP",
        version=__version__,
        instructions=INSTRUCTIONS,
        auth=auth,
    )
    tools.register_all(mcp)

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy",
                             "server": "LinuxMCP",
                             "version": __version__})

    @mcp.custom_route("/", methods=["GET"])
    async def _info(_request: Request) -> JSONResponse:
        return JSONResponse({
            "server": "LinuxMCP",
            "version": __version__,
            "protocol": "MCP",
            "transport": "streamable-http",
            "endpoints": {"mcp": "/mcp", "health": "/health"},
        })

    return mcp


def _apply_display_env(args: argparse.Namespace) -> None:
    """Allow reaching the user's X session when started from SSH/systemd."""
    display = args.display or os.environ.get("LINUXMCP_DISPLAY")
    xauthority = args.xauthority or os.environ.get("LINUXMCP_XAUTHORITY")
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
        prog="linuxmcp",
        description="LinuxMCP - MCP server for full Linux system "
                    "and desktop control.")
    transport = p.add_mutually_exclusive_group()
    transport.add_argument("--stdio", action="store_true",
                           help="serve over stdio (default)")
    transport.add_argument("--http", "--network", dest="http",
                           action="store_true",
                           help="serve over HTTP (streamable-http MCP)")
    p.add_argument("--host", default="0.0.0.0",
                   help="HTTP listen address (default 0.0.0.0)")
    p.add_argument("--port", type=int, default=3939,
                   help="HTTP port (default 3939)")
    p.add_argument("--path", default="/mcp",
                   help="HTTP MCP endpoint path (default /mcp)")
    p.add_argument("--auth-token", default=os.environ.get("LINUXMCP_AUTH_TOKEN"),
                   help="require Bearer token for HTTP "
                        "(or set LINUXMCP_AUTH_TOKEN)")
    p.add_argument("--display",
                   help="X display to use for desktop tools, e.g. :0 "
                        "(or LINUXMCP_DISPLAY)")
    p.add_argument("--xauthority",
                   help="X authority file for desktop tools "
                        "(or LINUXMCP_XAUTHORITY)")
    p.add_argument("--log-level", default=os.environ.get("LINUXMCP_LOG_LEVEL",
                                                       "info"),
                   help="uvicorn/mcp log level (default info)")
    p.add_argument("--list-tools", action="store_true",
                   help="print registered tools and exit")
    p.add_argument("--version", action="version",
                   version=f"linuxmcp {__version__}")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    _apply_display_env(args)

    token = args.auth_token
    mcp = create_server(auth_token=token)

    if args.list_tools:
        import asyncio
        names = sorted(t.name for t in asyncio.run(mcp.list_tools()))
        for name in names:
            print(name)
        print(f"{len(names)} tools", file=sys.stderr)
        return

    if args.http:
        if token:
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
