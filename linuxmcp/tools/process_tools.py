"""Process management tools."""

from typing import Optional

from fastmcp import FastMCP

from ..core import processes
from ..util import json_out


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def list_processes(
        name_filter: Optional[str] = None,
        username: Optional[str] = None,
        sort_by: str = "cpu",
        limit: int = 200,
    ) -> str:
        """List running processes with pid, name, cpu%, mem%, status, cmdline.

        Args:
            name_filter: substring match on name or cmdline
            username: filter by owning user
            sort_by: cpu | mem | pid | name
            limit: max results
        """
        return json_out(processes.list_processes(name_filter=name_filter,
                                                 username=username,
                                                 sort_by=sort_by,
                                                 limit=limit))

    @mcp.tool
    def get_process_info(pid: int, include_env: bool = False) -> str:
        """Detailed info for one pid: exe, cmdline, cwd, threads, memory,
        cpu times, open files, network connections.

        Args:
            include_env: include the process environment (may contain secrets)
        """
        return json_out(processes.get_process_info(pid,
                                                   include_env=include_env))

    @mcp.tool
    def find_processes_by_name(name: str, exact: bool = False) -> str:
        """Find processes by name (substring on name/cmdline, or exact match)."""
        return json_out(processes.find_processes_by_name(name, exact=exact))

    @mcp.tool
    def start_process(
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> str:
        """Start a detached background process (shell command line).

        For interactive processes or output capture, use start_shell_session.
        """
        return json_out(processes.start_process(command, cwd=cwd, env=env))

    @mcp.tool
    def kill_process(pid: int, force: bool = False,
                     timeout: float = 5.0) -> str:
        """Terminate a process. SIGTERM by default, escalating to SIGKILL
        after timeout. force=True sends SIGKILL immediately."""
        return json_out(processes.kill_process(pid, force=force,
                                               timeout=timeout))

    @mcp.tool
    def kill_processes_by_name(
        name: str,
        exact: bool = False,
        force: bool = False,
    ) -> str:
        """Kill all processes matching a name. Returns per-pid results."""
        return json_out(processes.kill_processes_by_name(name, exact=exact,
                                                         force=force))

    @mcp.tool
    def send_signal(pid: int, signal_name: str) -> str:
        """Send a signal by name (TERM, KILL, INT, HUP, USR1, STOP, CONT, ...)
        to a process."""
        return json_out(processes.send_signal(pid, signal_name))

    @mcp.tool
    def wait_for_process(pid: int, timeout: float = 30.0) -> str:
        """Block until a process exits (or timeout)."""
        return json_out(processes.wait_for_exit(pid, timeout=timeout))

    @mcp.tool
    def process_tree(pid: int) -> str:
        """Show a process and all its descendants."""
        return json_out(processes.process_tree(pid))
