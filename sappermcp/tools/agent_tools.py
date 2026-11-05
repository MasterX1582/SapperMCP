"""Agent-dispatch tools: the LLM-driven sapper commands.

These run the bundled sapper CLI in a subprocess because they spawn an agent
CLI (claude/codex/...) and can run for a long time. Pass background=True to
launch inside a persistent PTY session instead - poll progress with
read_session_output, steer with write_to_session, stop with
close_shell_session (all provided by the embedded LinuxMCP toolset).
"""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP
from linuxmcp.util import json_out

from ..core.runner import run_sapper, run_sapper_background, store_flag


def _run(args: list[str], cwd: Optional[str], background: bool,
         exec_timeout: float) -> str:
    if background:
        return json_out(run_sapper_background(args, cwd=cwd))
    return json_out(run_sapper(args, cwd=cwd, timeout=exec_timeout))


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def sapper_dispatch(target: str, store: str = ".sapper",
                        model: Optional[str] = None,
                        timeout: Optional[int] = None,
                        templates: Optional[str] = None,
                        skip_permissions: bool = False,
                        dry_run: bool = False,
                        claim: bool = False,
                        intent: Optional[str] = None,
                        max_options: int = 4,
                        cwd: Optional[str] = None,
                        background: bool = False,
                        exec_timeout: float = 700.0) -> str:
        """Run one commander/executor step via the agent CLI
        (like `sapper dispatch <target>`).

        Args:
            target: reason | verify | blindspot | brainstorm | <intent-id>
            model: agent model (default $SAPPER_MODEL or 'sonnet')
            timeout: per-call agent timeout seconds (default $SAPPER_TIMEOUT 600)
            dry_run: print the rendered prompt and exit
            claim: (explore) claim the intent first
            intent: (verify) intent id to verify
            max_options: (brainstorm) number of options to generate
            background: run in a PTY session, return session_id immediately
            exec_timeout: sync-mode cap on the whole subprocess
        """
        args = store_flag(store) + ["dispatch", target]
        if model:
            args += ["--model", model]
        if timeout:
            args += ["--timeout", str(timeout)]
        if templates:
            args += ["--templates", templates]
        if skip_permissions:
            args.append("--skip-permissions")
        if dry_run:
            args.append("--dry-run")
        if claim:
            args.append("--claim")
        if intent:
            args += ["--intent", intent]
        args += ["--max-options", str(max_options)]
        return _run(args, cwd, background, exec_timeout)

    @mcp.tool
    def sapper_auto(store: str = ".sapper", model: Optional[str] = None,
                    timeout: Optional[int] = None,
                    templates: Optional[str] = None,
                    skip_permissions: bool = False,
                    dry_run: bool = False,
                    verify: bool = False,
                    max_steps: int = 8,
                    max_explore: int = 6,
                    minutes: Optional[int] = None,
                    deadline: Optional[str] = None,
                    cwd: Optional[str] = None,
                    background: bool = False,
                    exec_timeout: float = 1800.0) -> str:
        """Drive a graph toward its goal autonomously: reason -> explore ->
        optional verify, looping until max-steps, the goal, or the deadline
        (like `sapper auto`).

        Args:
            dry_run: reason only, no explore
            verify: verify each explore result
            max_steps / max_explore: loop caps
            minutes / deadline: slot-clock budget (ISO 8601 local deadline)
            background: run in a PTY session (recommended for real runs);
                        poll with read_session_output
            exec_timeout: sync-mode cap (default 30 min)
        """
        args = store_flag(store) + ["auto"]
        if model:
            args += ["--model", model]
        if timeout:
            args += ["--timeout", str(timeout)]
        if templates:
            args += ["--templates", templates]
        if skip_permissions:
            args.append("--skip-permissions")
        if dry_run:
            args.append("--dry-run")
        if verify:
            args.append("--verify")
        args += ["--max-steps", str(max_steps),
                 "--max-explore", str(max_explore)]
        if minutes is not None:
            args += ["--minutes", str(minutes)]
        if deadline:
            args += ["--deadline", deadline]
        return _run(args, cwd, background, exec_timeout)

    @mcp.tool
    def sapper_brainstorm_pick(id: str, store: str = ".sapper",
                               cwd: Optional[str] = None) -> str:
        """Pick one brainstorm option; siblings from the same batch are
        concluded with a rejection fact (like `sapper brainstorm-pick`)."""
        return json_out(run_sapper(
            store_flag(store) + ["brainstorm-pick", id], cwd=cwd))
