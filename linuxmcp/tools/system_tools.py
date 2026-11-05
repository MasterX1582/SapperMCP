"""System information tools."""

from fastmcp import FastMCP

from ..core import system
from ..util import json_out


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def get_system_info() -> str:
        """Overall system snapshot: OS/distro, kernel, uptime, CPU model and
        load, memory, swap, root disk, logged-in users."""
        return json_out(system.get_system_info())

    @mcp.tool
    def get_cpu_usage(interval: float = 1.0, per_core: bool = False) -> str:
        """CPU usage percent (samples over `interval` seconds)."""
        return json_out(system.get_cpu_usage(interval=interval,
                                             per_core=per_core))

    @mcp.tool
    def get_memory_info() -> str:
        """Memory and swap details (total/available/used/cached/buffers)."""
        return json_out(system.get_memory_info())

    @mcp.tool
    def get_disk_usage(path: str = "/") -> str:
        """Disk usage for the filesystem containing `path`."""
        return json_out(system.get_disk_usage(path))

    @mcp.tool
    def list_disks() -> str:
        """Mounted partitions with fstype, usage and IO counters."""
        return json_out(system.list_disks())

    @mcp.tool
    def get_network_info() -> str:
        """Network interfaces with IPs, state, speed, IO counters, default
        route and DNS servers."""
        return json_out(system.get_network_info())

    @mcp.tool
    def list_listening_ports(protocol: str = "all") -> str:
        """Listening TCP/UDP ports with owning pid and process name.

        Args:
            protocol: all | tcp | udp | tcp4 | tcp6 | udp4 | udp6
        """
        return json_out(system.list_listening_ports(protocol=protocol))

    @mcp.tool
    def get_environment_variables(mask_secrets: bool = True) -> str:
        """Environment variables of the linuxmcp process.

        mask_secrets redacts vars whose name contains KEY/TOKEN/SECRET/
        PASSWORD/PWD - set False to see raw values."""
        return json_out(system.get_environment(mask_secrets=mask_secrets))

    @mcp.tool
    def get_hardware_info() -> str:
        """Hardware details via lscpu, lsusb, lspci, lsblk when available."""
        return json_out(system.get_hardware_info())
