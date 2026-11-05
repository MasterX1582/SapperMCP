"""Fact-graph tools: structured access to the .sapper/ store.

These call the bundled sapper module's Store API directly (same code path as
the CLI) so results come back as JSON instead of printed text. Every tool
takes `store` = path to a .sapper/ directory (default ".sapper" relative to
the server cwd).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from linuxmcp.util import err, json_out

from ..core.sapperlib import sapper


def _store(path: str):
    mod = sapper()
    store = mod.Store(Path(path))
    store.require()
    return mod, store


def _doc(doc: Optional[str], doc_file: Optional[str]) -> Optional[str]:
    if doc_file:
        return Path(doc_file).read_text(encoding="utf-8")
    return doc


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def sapper_init(goal: str, store: str = ".sapper", origin: str = "",
                    force: bool = False) -> str:
        """Create a fact-intent graph (like `sapper init --goal`).

        Args:
            goal: the terminal goal, one line
            store: graph dir to create (default .sapper)
            origin: where this task came from
            force: overwrite an existing graph (destructive)
        """
        try:
            mod = sapper()
            st = mod.Store(Path(store))
            if st.exists() and not force:
                return err(f"graph exists at {st.root}; pass force=True to overwrite")
            if force and st.root.exists():
                mod._assert_safe_store_root(st.root, "overwrite")
                shutil.rmtree(st.root)
            st.init(origin=origin, goal=goal)
            return json_out({"ok": True, "store": str(st.root), "goal": goal})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_status(store: str = ".sapper") -> str:
        """Project + frontier summary text (like `sapper status`)."""
        try:
            mod, st = _store(store)
            return json_out({"ok": True, "status": mod.render_status(st)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_graph(store: str = ".sapper", format: str = "json") -> str:
        """Dump the whole graph. format=json gives the structured view,
        format=text renders the CLI text form."""
        try:
            mod, st = _store(store)
            if format == "text":
                return json_out({"ok": True, "graph": mod.render_graph_text(st)})
            return json_out({"ok": True, "graph": mod.build_graph_view(st)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_validate(store: str = ".sapper") -> str:
        """Integrity-check the graph; returns a list of errors (empty = valid)."""
        try:
            mod, st = _store(store)
            errors = mod.validate_graph(st)
            return json_out({"ok": not errors, "valid": not errors,
                             "errors": errors})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_frontier(store: str = ".sapper") -> str:
        """List open intents that are ready to work (dependencies met,
        confirmed). Claimed intents come first."""
        try:
            mod, st = _store(store)
            return json_out({"ok": True, "frontier": mod.frontier(st)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_pick(store: str = ".sapper", claim: bool = False,
                    any_open: bool = False,
                    worker: Optional[str] = None) -> str:
        """Pick the next intent to work (like `sapper pick`).

        Args:
            claim: claim the picked intent for `worker`
            any_open: include open-but-not-ready intents (e.g. unconfirmed)
            worker: worker name to claim as (default: generated)
        """
        try:
            mod, st = _store(store)
            w = (worker or mod._worker_id("agent")) if claim else None
            fr = mod.frontier(st)
            pool = [i for i in fr
                    if not claim or not i.get("worker") or i.get("worker") == w]
            if not pool and any_open:
                pool = [i for i in st.list_intents() if mod.is_open(i)]
            if not pool:
                return json_out({"ok": True, "id": None,
                                 "note": "nothing ready; any_open=True includes "
                                         "unconfirmed/blocked open intents"})
            chosen = pool[0]
            if claim:
                chosen = st.claim_intent(chosen["id"], w)
            return json_out({"ok": True, "id": chosen["id"], "intent": chosen})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_fact(description: str, store: str = ".sapper",
                    title: Optional[str] = None, kind: Optional[str] = None,
                    data: Optional[dict] = None, doc: Optional[str] = None,
                    doc_file: Optional[str] = None, creator: str = "mcp",
                    from_intent: Optional[str] = None) -> str:
        """Record a confirmed fact (like `sapper fact`).

        Args:
            description: one-sentence gist of the fact
            kind: host | service | cred | vuln | loot | flag | note
            data: structured key=value fields, e.g. {"ip": "10.0.0.1"}
            doc / doc_file: detailed markdown body (third doc layer)
            from_intent: conclude this intent with the new fact
        """
        try:
            mod, st = _store(store)
            fact = st.add_fact(
                description=description, creator=creator,
                source_intent=from_intent, title=title,
                doc=_doc(doc, doc_file), kind=kind, data=data,
            )
            return json_out({"ok": True, "fact": fact})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_intent(from_ids: list[str], description: str,
                      store: str = ".sapper", title: Optional[str] = None,
                      doc: Optional[str] = None, doc_file: Optional[str] = None,
                      creator: str = "mcp", confirm: bool = False) -> str:
        """Add an intent - a unit of work derived from existing facts
        (like `sapper intent --from f001,f002`).

        Args:
            from_ids: fact ids this intent builds on
            confirm: require human confirmation before it can be worked
        """
        try:
            mod, st = _store(store)
            intent = st.add_intent(
                from_ids=list(from_ids), description=description,
                creator=creator, requires_confirmation=confirm, title=title,
                doc=_doc(doc, doc_file),
            )
            return json_out({"ok": True, "intent": intent})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_hint(store: str = ".sapper", content: Optional[str] = None,
                    creator: str = "mcp", list: bool = False) -> str:
        """Add or list human hints for the agents (like `sapper hint`)."""
        try:
            mod, st = _store(store)
            if list:
                return json_out({"ok": True, "hints": st.list_hints()})
            if not content:
                return err("hint content required (or pass list=True)")
            return json_out({"ok": True, "hint": st.add_hint(content, creator)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_show(entity: str, id: Optional[str] = None,
                    store: str = ".sapper") -> str:
        """Show project | fact <id> | intent <id> as JSON."""
        try:
            mod, st = _store(store)
            if entity == "project":
                return json_out({"ok": True, "project": st.load_project()})
            if not id:
                return err(f"show {entity} requires an id")
            if entity == "fact":
                return json_out({"ok": True, "fact": st.get_fact(id)})
            if entity == "intent":
                return json_out({"ok": True, "intent": st.get_intent(id)})
            return err("entity must be project|fact|intent")
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_doc(id: str, store: str = ".sapper", set: Optional[str] = None,
                   set_file: Optional[str] = None) -> str:
        """Read or write a node's detailed doc (title=gist, doc=detail).

        `sapper_doc(id)` returns the doc; pass `set` or `set_file` to write.
        """
        try:
            mod, st = _store(store)
            mod._validate_lookup_id(id, "node")
            if id == mod.GOAL_ID or (st.facts_dir / f"{id}.json").exists():
                node = st.get_fact(id)
            elif (st.intents_dir / f"{id}.json").exists():
                node = st.get_intent(id)
            else:
                return err(f"no fact or intent named {id}")
            if set is not None or set_file:
                new_doc = set if set is not None else Path(set_file).read_text(
                    encoding="utf-8")
                new_doc = new_doc.strip() if isinstance(new_doc, str) else None
                node = st.update_doc(id, new_doc or None,
                                     expected_doc=node.get("doc"))
                return json_out({"ok": True, "id": id,
                                 "doc_chars": len(node.get("doc") or "")})
            doc = node.get("doc")
            if not doc:
                return err(f"{id} has no doc (write one with set=...)")
            return json_out({"ok": True, "id": id, "doc": doc})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_recall(query: str, store: str = ".sapper", limit: int = 5,
                      kind: str = "any") -> str:
        """Find prior facts/intents similar to a free-text gist; read the top
        hit's doc with sapper_doc to reuse what was learned."""
        try:
            mod, st = _store(store)
            kinds = ("fact",) if kind == "fact" else \
                    ("intent",) if kind == "intent" else ("fact", "intent")
            matches = mod.recall(st, query, limit=max(1, limit), kinds=kinds)
            return json_out({"ok": True, "matches": matches,
                             "count": len(matches)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_claim(id: str, worker: str, store: str = ".sapper") -> str:
        """Claim an open intent for a worker."""
        try:
            mod, st = _store(store)
            return json_out({"ok": True,
                             "intent": st.claim_intent(id, worker)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_release(id: str, store: str = ".sapper",
                       worker: Optional[str] = None) -> str:
        """Release a claimed intent back to open."""
        try:
            import os
            mod, st = _store(store)
            w = worker or f"agent-{os.getpid()}"
            return json_out({"ok": True,
                             "intent": st.release_intent(id, w)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_done(id: str, fact: str, store: str = ".sapper",
                    title: Optional[str] = None, kind: Optional[str] = None,
                    data: Optional[dict] = None, doc: Optional[str] = None,
                    doc_file: Optional[str] = None,
                    worker: str = "mcp") -> str:
        """Conclude an intent with the fact it produced (atomic, like
        `sapper done <id> --fact "..."`)."""
        try:
            mod, st = _store(store)
            new_fact, intent = st.conclude_with_new_fact(
                id, fact, worker, title=title,
                doc=_doc(doc, doc_file), kind=kind, data=data,
            )
            return json_out({"ok": True, "fact": new_fact, "intent": intent})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_complete(from_ids: list[str], store: str = ".sapper",
                        note: Optional[str] = None,
                        worker: str = "mcp") -> str:
        """Mark the project goal satisfied, justified by the given facts
        (like `sapper complete --from f001,f005`)."""
        try:
            mod, st = _store(store)
            intent = st.complete_project(list(from_ids),
                                         note or "goal satisfied", worker)
            return json_out({"ok": True, "intent": intent,
                             "status": "completed"})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_confirm(id: str, store: str = ".sapper") -> str:
        """Confirm an intent that was created with confirm=True."""
        try:
            mod, st = _store(store)
            return json_out({"ok": True,
                             "intent": st.confirm_intent(id)})
        except Exception as exc:
            return err(str(exc))
