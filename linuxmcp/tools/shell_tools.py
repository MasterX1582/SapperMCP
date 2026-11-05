"""Shell execution tools: one-shot commands and persistent PTY sessions."""

from typing import Optional

from fastmcp import FastMCP

from ..core import shell as sh
from ..util import err, json_out


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def run_command(
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: float = 120.0,
        shell: str = "/bin/bash",
        login: bool = False,
        sudo: bool = False,
    ) -> str:
        """Run a shell command and return stdout, stderr and exit code.

        Args:
            command: shell command line, e.g. "systemctl status nginx | head"
            cwd: working directory (default: server cwd)
            env: extra environment variables to set
            timeout: seconds before the command is killed (default 120)
            shell: shell to use (default /bin/bash)
            login: run as login shell (-lc) so profile/PATH is loaded
            sudo: run via sudo -n (needs passwordless sudo) or sudo -S when
                  LINUXMCP_SUDO_PASSWORD is set on the server
        """
        return json_out(sh.run_command(command, cwd=cwd, env=env,
                                       timeout=timeout, shell=shell,
                                       login=login, sudo=sudo))

    @mcp.tool
    def run_argv(
        argv: list[str],
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: float = 120.0,
        sudo: bool = False,
    ) -> str:
        """Run a program with an argument list (no shell interpretation).

        Safer than run_command for arguments containing shell metacharacters.
        """
        return json_out(sh.run_argv(argv, cwd=cwd, env=env,
                                    timeout=timeout, sudo=sudo))

    @mcp.tool
    def start_shell_session(
        command: Optional[str] = None,
        cwd: Optional[str] = None,
        shell: str = "/bin/bash",
        sudo: bool = False,
    ) -> str:
        """Start a persistent interactive PTY session and return its id.

        With command=None spawns an interactive shell. With a command, runs
        `shell -c <command>` inside the PTY - ideal for long-running apps,
        debuggers (gdb), REPLs, or anything needing a TTY. Use
        write_to_session / read_session_output to interact.
        """
        return json_out(sh.start_session(command=command, cwd=cwd,
                                         shell=shell, sudo=sudo))

    @mcp.tool
    def write_to_session(
        session_id: str,
        text: str,
        press_enter: bool = True,
    ) -> str:
        """Write input to a PTY session's stdin.

        Args:
            session_id: id from start_shell_session
            text: text to send
            press_enter: append a newline (like pressing Enter)
        """
        session = sh.get_session(session_id)
        if session is None:
            return err(f"Unknown session: {session_id}")
        data = text + ("\n" if press_enter else "")
        written = session.write(data)
        return json_out({"ok": True, "session_id": session_id,
                         "bytes_written": written})

    @mcp.tool
    def read_session_output(
        session_id: str,
        all_output: bool = False,
    ) -> str:
        """Read output from a PTY session.

        Returns only new output since the last read unless all_output=True.
        """
        session = sh.get_session(session_id)
        if session is None:
            return err(f"Unknown session: {session_id}")
        return json_out({"ok": True, **session.read(all_output)})

    @mcp.tool
    def list_shell_sessions() -> str:
        """List all active PTY sessions."""
        return json_out({"ok": True, "sessions": sh.list_sessions()})

    @mcp.tool
    def close_shell_session(session_id: str) -> str:
        """Terminate a PTY session (SIGTERM then SIGKILL)."""
        if not sh.close_session(session_id):
            return err(f"Unknown session: {session_id}")
        return json_out({"ok": True, "session_id": session_id})
