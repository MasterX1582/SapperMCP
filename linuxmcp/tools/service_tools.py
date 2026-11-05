"""systemd services and log tools (journald + /var/log)."""

from typing import Optional

from fastmcp import FastMCP

from ..core import services
from ..util import json_out


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def list_services(
        state: Optional[str] = None,
        pattern: Optional[str] = None,
        user: bool = False,
        limit: int = 300,
    ) -> str:
        """List systemd service units with load/active/sub state.

        Args:
            state: filter e.g. 'running', 'failed', 'active', 'exited'
            pattern: unit name glob like 'nginx*'
            user: query user manager instead of system
        """
        return json_out(services.list_services(state=state, pattern=pattern,
                                               user=user, limit=limit))

    @mcp.tool
    def get_service_status(name: str, user: bool = False) -> str:
        """Detailed unit status: ActiveState/SubState, MainPID, memory,
        enablement, plus last status output lines."""
        return json_out(services.get_service_status(name, user=user))

    @mcp.tool
    def manage_service(
        action: str,
        name: str,
        user: bool = False,
        sudo: bool = True,
    ) -> str:
        """Control a systemd unit.

        Args:
            action: start | stop | restart | reload | enable | disable |
                    mask | unmask | try-restart
            name: unit name ('.service' appended if missing)
            user: act on the user manager (no sudo needed)
            sudo: elevate for system units
        """
        return json_out(services.service_action(action, name, user=user,
                                                sudo=sudo))

    @mcp.tool
    def get_service_logs(
        name: str,
        lines: int = 100,
        since: Optional[str] = None,
        priority: Optional[str] = None,
        user: bool = False,
    ) -> str:
        """Journal logs for one unit.

        Args:
            since: e.g. '1 hour ago', 'today', '2024-06-01 12:00'
            priority: emerg|alert|crit|err|warning|notice|info|debug
        """
        return json_out(services.get_service_logs(name, lines=lines,
                                                  since=since,
                                                  priority=priority,
                                                  user=user))

    @mcp.tool
    def read_journal(
        unit: Optional[str] = None,
        lines: int = 100,
        since: Optional[str] = None,
        priority: Optional[str] = None,
        grep: Optional[str] = None,
        identifier: Optional[str] = None,
        user: bool = False,
        reverse: bool = False,
        sudo: bool = False,
    ) -> str:
        """Query the systemd journal (journalctl).

        Args:
            unit: filter by unit e.g. 'ssh.service'
            since: '1 hour ago', 'today', '2024-06-01', ...
            priority: minimum priority err|warning|info|debug...
            grep: regex filter (journalctl -g)
            identifier: syslog identifier (-t)
            reverse: newest first
            sudo: retry with sudo on permission errors (system journal needs
                  root or systemd-journal group)
        """
        return json_out(services.read_journal(unit=unit, lines=lines,
                                              since=since, priority=priority,
                                              grep=grep,
                                              identifier=identifier,
                                              user=user, reverse=reverse,
                                              sudo=sudo))

    @mcp.tool
    def read_log_file(
        path: str,
        lines: int = 100,
        offset: int = 0,
        tail: bool = True,
    ) -> str:
        """Read a log file. tail=True returns the last `lines` lines;
        tail=False reads `lines` lines starting at `offset`."""
        return json_out(services.read_log_file(path, lines=lines,
                                               offset=offset, tail=tail))

    @mcp.tool
    def list_log_files(
        directory: str = "/var/log",
        pattern: Optional[str] = None,
        max_entries: int = 300,
    ) -> str:
        """List log files under /var/log (or another dir), newest first."""
        return json_out(services.list_log_files(directory=directory,
                                                pattern=pattern,
                                                max_entries=max_entries))
