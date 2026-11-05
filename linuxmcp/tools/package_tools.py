"""Package management tools (apt/dpkg for Debian/Ubuntu/Zorin)."""

from typing import Optional

from fastmcp import FastMCP

from ..core import packages
from ..util import json_out


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def package_search(query: str, limit: int = 50) -> str:
        """Search available packages by name (apt-cache search)."""
        return json_out(packages.package_search(query, limit=limit))

    @mcp.tool
    def package_info(name: str) -> str:
        """Package details: version, dependencies, description, install
        status, candidate version (apt-cache show/policy)."""
        return json_out(packages.package_info(name))

    @mcp.tool
    def package_list_installed(
        filter: Optional[str] = None,
        limit: int = 500,
    ) -> str:
        """List installed packages (dpkg). filter = name substring."""
        return json_out(packages.package_list_installed(filter=filter,
                                                        limit=limit))

    @mcp.tool
    def package_install(
        names: list[str],
        update_first: bool = False,
        timeout: float = 300.0,
    ) -> str:
        """Install packages via apt-get install -y (sudo).

        Args:
            names: package names, e.g. ["htop", "curl"]
            update_first: run apt-get update before installing
            timeout: apt timeout in seconds
        """
        return json_out(packages.package_install(names,
                                                 update_first=update_first,
                                                 timeout=timeout))

    @mcp.tool
    def package_remove(
        names: list[str],
        purge: bool = False,
        timeout: float = 300.0,
    ) -> str:
        """Remove packages (apt-get remove -y). purge=True also removes
        config files."""
        return json_out(packages.package_remove(names, purge=purge,
                                                timeout=timeout))

    @mcp.tool
    def package_update(timeout: float = 300.0) -> str:
        """Refresh package lists (apt-get update, sudo)."""
        return json_out(packages.package_update(timeout=timeout))

    @mcp.tool
    def package_upgrade(timeout: float = 600.0, full: bool = False) -> str:
        """Upgrade installed packages (apt-get upgrade -y, sudo).
        full=True runs dist-upgrade. Potentially long-running."""
        return json_out(packages.package_upgrade(timeout=timeout, full=full))

    @mcp.tool
    def package_files(name: str, limit: int = 300) -> str:
        """List files owned by an installed package (dpkg -L)."""
        return json_out(packages.package_files(name, limit=limit))

    @mcp.tool
    def package_owner(path: str) -> str:
        """Which package owns a file (dpkg -S)."""
        return json_out(packages.package_owner(path))
