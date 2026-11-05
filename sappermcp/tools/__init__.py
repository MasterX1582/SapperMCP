"""Sapper MCP tool registration. Each module exposes register(mcp)."""

from fastmcp import FastMCP

from . import (
    agent_tools,
    arena_tools,
    graph_tools,
    kb_tools,
    ops_tools,
    report_tools,
)

_MODULES = (
    graph_tools,
    arena_tools,
    kb_tools,
    agent_tools,
    ops_tools,
    report_tools,
)


def register_all(mcp: FastMCP) -> None:
    for mod in _MODULES:
        mod.register(mcp)
