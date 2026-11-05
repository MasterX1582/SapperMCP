"""GNOME settings tools (gsettings/dconf) - the Linux desktop 'registry'."""

from typing import Optional

from fastmcp import FastMCP

from ..core import gsettings as gs
from ..util import json_out


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def gsettings_get(schema: str, key: str) -> str:
        """Read a gsettings value, e.g. schema org.gnome.desktop.interface,
        key gtk-theme."""
        return json_out(gs.gsettings_get(schema, key))

    @mcp.tool
    def gsettings_set(schema: str, key: str, value: str) -> str:
        """Write a gsettings value. value uses GVariant syntax:
        true/false, 42, 'quoted-string', ['a','b']."""
        return json_out(gs.gsettings_set(schema, key, value))

    @mcp.tool
    def gsettings_reset(schema: str, key: str) -> str:
        """Reset a gsettings key to its default."""
        return json_out(gs.gsettings_reset(schema, key))

    @mcp.tool
    def gsettings_list_schemas(
        filter: Optional[str] = None,
        limit: int = 300,
    ) -> str:
        """List installed gsettings schemas, optionally substring-filtered
        (e.g. 'gnome', 'zora', 'desktop')."""
        return json_out(gs.gsettings_list_schemas(filter=filter, limit=limit))

    @mcp.tool
    def gsettings_list_keys(schema: str) -> str:
        """List keys in a gsettings schema."""
        return json_out(gs.gsettings_list_keys(schema))

    @mcp.tool
    def gsettings_describe(schema: str, key: str) -> str:
        """Describe a gsettings key and its allowed range/values."""
        return json_out(gs.gsettings_describe(schema, key))

    @mcp.tool
    def dconf_read(path: str) -> str:
        """Read a dconf key, e.g. /org/gnome/desktop/interface/gtk-theme."""
        return json_out(gs.dconf_read(path))

    @mcp.tool
    def dconf_write(path: str, value: str) -> str:
        """Write a dconf key (GVariant syntax value)."""
        return json_out(gs.dconf_write(path, value))

    @mcp.tool
    def dconf_list(path: str) -> str:
        """List keys/subdirs under a dconf path (must end with '/')."""
        return json_out(gs.dconf_list(path))
