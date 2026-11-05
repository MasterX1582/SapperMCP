"""MCP tool registration. Each module exposes register(mcp)."""

from fastmcp import FastMCP

from . import (
    desktop_tools,
    file_tools,
    package_tools,
    process_tools,
    service_tools,
    settings_tools,
    shell_tools,
    system_tools,
)

_MODULES = (
    shell_tools,
    file_tools,
    process_tools,
    system_tools,
    service_tools,
    package_tools,
    settings_tools,
    desktop_tools,
)


def register_all(mcp: FastMCP) -> None:
    for mod in _MODULES:
        mod.register(mcp)
