"""Operations tools: project setup/teardown, peers messaging, and the
multi-challenge orchestrators (fleet / command / sweep / bench).

All run the bundled sapper CLI in a subprocess - orchestrators support
background=True (PTY session) so hour-long runs don't block the MCP call.
`sapper_cli` is the generic escape hatch covering every flag.
"""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP
from linuxmcp.util import err, json_out

from ..core.runner import run_sapper, run_sapper_background, store_flag


def _run(args: list[str], cwd: Optional[str], background: bool,
         exec_timeout: float) -> str:
    if background:
        return json_out(run_sapper_background(args, cwd=cwd))
    return json_out(run_sapper(args, cwd=cwd, timeout=exec_timeout))


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def sapper_cli(args: list[str], store: Optional[str] = None,
                   cwd: Optional[str] = None, background: bool = False,
                   exec_timeout: float = 120.0) -> str:
        """Run any bundled `sapper` CLI command verbatim (escape hatch).

        Args:
            args: argv after `sapper`, e.g. ["status"] or
                  ["fact", "found sqli", "-k", "vuln"]
            store: prepends --store <path> when set
            background: launch in a PTY session, returns session_id
            exec_timeout: sync-mode cap in seconds
        """
        return _run(store_flag(store) + list(args), cwd, background,
                    exec_timeout)

    @mcp.tool
    def sapper_setup(project_dir: str, goal: Optional[str] = None,
                     origin: str = "", agents: bool = False,
                     force: bool = False, store: str = ".sapper") -> str:
        """Opt a project IN: create .sapper/ + register Claude Code hooks in
        <project_dir>/.claude/settings.json (like `sapper setup`)."""
        args = store_flag(store) + ["setup", "--origin", origin]
        if goal:
            args += ["--goal", goal]
        if agents:
            args.append("--agents")
        if force:
            args.append("--force")
        return json_out(run_sapper(args, cwd=project_dir))

    @mcp.tool
    def sapper_teardown(project_dir: str, purge: bool = False,
                        store: str = ".sapper") -> str:
        """Remove sapper hooks + its AGENTS.md from a project. purge=True also
        deletes the .sapper/ graph data (destructive)."""
        args = store_flag(store) + ["teardown"]
        if purge:
            args.append("--purge")
        return json_out(run_sapper(args, cwd=project_dir))

    @mcp.tool
    def sapper_peers(store: str = ".sapper", discover: bool = False,
                     add: Optional[str] = None, remove: Optional[str] = None,
                     target: Optional[str] = None,
                     sender: Optional[str] = None,
                     channel: Optional[str] = None,
                     note: Optional[str] = None,
                     cwd: Optional[str] = None) -> str:
        """Discover tmux panes and manage user-authorized AI peers
        (like `sapper peers`)."""
        args = store_flag(store) + ["peers", "--json"]
        if discover:
            args.append("--discover")
        if add:
            args += ["--add", add]
        if remove:
            args += ["--remove", remove]
        if target:
            args += ["--target", target]
        if sender:
            args += ["--sender", sender]
        if channel:
            args += ["--channel", channel]
        if note:
            args += ["--note", note]
        return json_out(run_sapper(args, cwd=cwd))

    @mcp.tool
    def sapper_send(peer: str, message: str, store: str = ".sapper",
                    sender: Optional[str] = None,
                    channel: Optional[str] = None, no_log: bool = False,
                    raw: bool = False, cwd: Optional[str] = None) -> str:
        """Send a message to a user-authorized tmux peer via load-buffer/
        paste-buffer (like `sapper send <peer> <msg>`)."""
        args = store_flag(store) + ["send", peer, message]
        if sender:
            args += ["--sender", sender]
        if channel:
            args += ["--channel", channel]
        if no_log:
            args.append("--no-log")
        if raw:
            args.append("--raw")
        return json_out(run_sapper(args, cwd=cwd))

    @mcp.tool
    def sapper_capture(peer: str, store: str = ".sapper", lines: int = 120,
                       channel: Optional[str] = None, log: bool = False,
                       cwd: Optional[str] = None) -> str:
        """Capture recent output from an authorized tmux peer
        (like `sapper capture`)."""
        args = store_flag(store) + ["capture", peer,
                                    "--lines", str(max(1, min(lines, 2000)))]
        if channel:
            args += ["--channel", channel]
        if log:
            args.append("--log")
        return json_out(run_sapper(args, cwd=cwd))

    @mcp.tool
    def sapper_fleet(action: str, cwd: Optional[str] = None,
                     file: Optional[str] = None, target: Optional[str] = None,
                     minutes: Optional[int] = None,
                     max_steps: Optional[int] = None,
                     extra_args: Optional[str] = None) -> str:
        """Manage the tmux worker fleet (like `sapper fleet`).

        action: init | up | down | status | hire | fire | workers
        hire/fire take target=<challenge name>; hire also minutes/max_steps/
        extra_args.
        """
        if action not in ("init", "up", "down", "status", "hire", "fire",
                          "workers"):
            return err("action must be init|up|down|status|hire|fire|workers")
        args = ["fleet", action]
        if file:
            args += ["--file", file]
        if target:
            args += ["--target", target]
        if minutes is not None:
            args += ["--minutes", str(minutes)]
        if max_steps is not None:
            args += ["--max-steps", str(max_steps)]
        if extra_args:
            args += ["--extra-args", extra_args]
        return json_out(run_sapper(args, cwd=cwd))

    @mcp.tool
    def sapper_command(cwd: str, root: str = "runs",
                       minutes: Optional[int] = None,
                       deadline: Optional[str] = None,
                       minutes_default: int = 20,
                       minutes_max: int = 40,
                       fleet_file: Optional[str] = None,
                       poll_seconds: int = 30,
                       model: Optional[str] = None,
                       timeout: Optional[int] = None,
                       templates: Optional[str] = None,
                       skip_permissions: bool = False,
                       verify: bool = False,
                       max_steps: int = 8,
                       background: bool = False,
                       exec_timeout: float = 1800.0) -> str:
        """Field commander loop: LLM allocates the next work slice across
        per-challenge graphs under `root` (like `sapper command`). Runs until
        deadline/stop - use background=True for real campaigns."""
        args = ["command", "--root", root,
                "--minutes-default", str(minutes_default),
                "--minutes-max", str(minutes_max),
                "--poll-seconds", str(poll_seconds),
                "--max-steps", str(max_steps)]
        if minutes is not None:
            args += ["--minutes", str(minutes)]
        if deadline:
            args += ["--deadline", deadline]
        if fleet_file:
            args += ["--fleet-file", fleet_file]
        if model:
            args += ["--model", model]
        if timeout:
            args += ["--timeout", str(timeout)]
        if templates:
            args += ["--templates", templates]
        if skip_permissions:
            args.append("--skip-permissions")
        if verify:
            args.append("--verify")
        return _run(args, cwd, background, exec_timeout)

    @mcp.tool
    def sapper_sweep(cwd: str, root: str = "runs",
                     minutes: Optional[int] = None,
                     deadline: Optional[str] = None,
                     minutes_per: int = 20,
                     model: Optional[str] = None,
                     templates: Optional[str] = None,
                     skip_permissions: bool = False,
                     verify: bool = False,
                     max_steps: int = 8,
                     background: bool = False,
                     exec_timeout: float = 1800.0) -> str:
        """Round-robin driver: every challenge graph under `root` gets
        minutes_per of `sapper auto` per round until deadline
        (like `sapper sweep`). Requires minutes or deadline."""
        args = ["sweep", "--root", root,
                "--minutes-per", str(minutes_per),
                "--max-steps", str(max_steps)]
        if minutes is not None:
            args += ["--minutes", str(minutes)]
        if deadline:
            args += ["--deadline", deadline]
        if model:
            args += ["--model", model]
        if templates:
            args += ["--templates", templates]
        if skip_permissions:
            args.append("--skip-permissions")
        if verify:
            args.append("--verify")
        return _run(args, cwd, background, exec_timeout)

    @mcp.tool
    def sapper_bench(cwd: str, root: str = "runs",
                     minutes: Optional[int] = None,
                     deadline: Optional[str] = None,
                     minutes_per_challenge: int = 25,
                     max_steps: int = 10,
                     round_gap_seconds: int = 20,
                     parallel: int = 1,
                     poll_seconds: int = 5,
                     model: Optional[str] = None,
                     templates: Optional[str] = None,
                     skip_permissions: bool = False,
                     verify: bool = False,
                     background: bool = False,
                     exec_timeout: float = 1800.0) -> str:
        """TSecBench end-to-end driver: list -> start -> solve -> submit ->
        close per challenge (like `sapper bench`). The hosted-mode entrypoint.
        Use background=True for real runs."""
        args = ["bench", "--root", root,
                "--minutes-per-challenge", str(minutes_per_challenge),
                "--max-steps", str(max_steps),
                "--round-gap-seconds", str(round_gap_seconds),
                "--parallel", str(parallel),
                "--poll-seconds", str(poll_seconds)]
        if minutes is not None:
            args += ["--minutes", str(minutes)]
        if deadline:
            args += ["--deadline", deadline]
        if model:
            args += ["--model", model]
        if templates:
            args += ["--templates", templates]
        if skip_permissions:
            args.append("--skip-permissions")
        if verify:
            args.append("--verify")
        return _run(args, cwd, background, exec_timeout)
