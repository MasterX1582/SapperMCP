"""Flag ledger + arena (competition platform) tools.

sapper_flag replicates `sapper flag`: record deduped, optionally submit via
the arena API, crash-safe status bookkeeping (recorded -> submitted/rejected).
sapper_arena wraps the five TSecBench-style endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from linuxmcp.util import err, json_out

from ..core.sapperlib import arena, sapper


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def sapper_flag(value: str, store: str = ".sapper",
                    challenge: Optional[str] = None, submit: bool = False,
                    title: Optional[str] = None,
                    creator: str = "mcp") -> str:
        """Record a captured flag (deduped). With submit=True also sends it
        via the arena API and updates the fact's status
        (recorded -> submitted/rejected)."""
        try:
            mod = sapper()
            st = mod.Store(Path(store))
            st.require()
            value = value.strip()
            if not value:
                return err("flag value cannot be empty")
            existing = mod._find_flag_fact(st, value)
            if existing is not None:
                d = existing.get("data") or {}
                return err(
                    f"flag already recorded as {existing['id']} "
                    f"(status={d.get('status', 'recorded')}, "
                    f"challenge={d.get('challenge', '?')})",
                    fact_id=existing["id"],
                )
            ch = (challenge or "").strip()
            desc = f"flag captured: {value}" + \
                (f" (challenge {ch})" if ch else "")
            fact = st.add_fact(
                description=desc, creator=creator, source_intent=None,
                title=title or "flag", kind="flag",
                data={"value": value, "challenge": ch, "status": "recorded"},
            )
            if not submit:
                return json_out({"ok": True, "fact_id": fact["id"],
                                 "status": "recorded", "submitted": False})
            client = mod._arena_client(st)
            try:
                reply = client.submit_flag(ch or "-", value)
            except Exception as exc:
                st.update_flag_fact(fact["id"], "rejected", str(exc))
                return err(
                    f"submit failed, flag kept as {fact['id']} (recorded): {exc}",
                    fact_id=fact["id"], status="rejected",
                )
            import json as _json
            raw = _json.dumps(reply.get("result", {}), ensure_ascii=False)
            accepted = reply.get("status") == 200
            status = "submitted" if accepted else "rejected"
            st.update_flag_fact(fact["id"], status, raw[:500])
            return json_out({"ok": accepted, "fact_id": fact["id"],
                             "status": status, "reply": raw[:500]})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_arena(action: str, store: str = ".sapper",
                     challenge_id: Optional[str] = None,
                     flag: Optional[str] = None) -> str:
        """Competition platform bridge (TSecBench-style API).

        Actions:
            init        write .sapper/arena.json config template
            challenges  list all challenges
            start       start challenge_id
            stop        close challenge_id
            submit      submit `flag` for challenge_id
            hint        request hint for challenge_id (may cost score)

        Config: env BENCHMARK_BASE_URL + BENCHMARK_TOKEN, or .sapper/arena.json.
        """
        try:
            mod = sapper()
            ar = arena()
            st = mod.Store(Path(store))
            if action == "init":
                path = ar.ArenaClient.config_path(st.root)
                if path.exists():
                    return err(f"arena config already exists: {path}")
                written = ar.ArenaClient.write_template(st.root)
                return json_out({"ok": True, "config": str(written)})
            st.require()
            try:
                client = ar.ArenaClient.load(st.root)
            except ar.ArenaError as exc:
                return err(str(exc))
            if action == "challenges":
                reply = client.list_challenges()
            elif action == "start":
                if not challenge_id:
                    return err("start needs challenge_id")
                reply = client.start_challenge(challenge_id)
            elif action == "stop":
                if not challenge_id:
                    return err("stop needs challenge_id")
                reply = client.close_challenge(challenge_id)
            elif action == "submit":
                if not challenge_id or not flag:
                    return err("submit needs challenge_id and flag")
                reply = client.submit_flag(challenge_id, flag)
            elif action == "hint":
                if not challenge_id:
                    return err("hint needs challenge_id")
                reply = client.get_hint(challenge_id)
            else:
                return err(
                    f"unknown arena action {action!r} "
                    "(init|challenges|start|stop|submit|hint)"
                )
            if isinstance(reply, dict) and "result" in reply:
                reply = reply["result"]
            return json_out({"ok": True, "action": action, "result": reply})
        except Exception as exc:
            return err(str(exc))
