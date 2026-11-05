"""Knowledge-base tools: the shared offline technique/CVE/writeup store.

Wraps lib/kb.py directly. The kb root defaults to the repo's bundled kb/
(56 entries ship with sapper) or $SAPPER_KB_ROOT; override per call with
`root`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from linuxmcp.util import err, json_out

from ..core.sapperlib import kb as kb_mod


def _kb(root: Optional[str]):
    mod = kb_mod()
    r = Path(root) if root else mod.KnowledgeBase.default_root()
    return mod, mod.KnowledgeBase(r)


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def sapper_kb(action: str, target: Optional[str] = None,
                  description: Optional[str] = None,
                  detail: Optional[str] = None,
                  detail_file: Optional[str] = None,
                  tags: Optional[list] = None,
                  commands: Optional[list] = None,
                  source: Optional[str] = None,
                  root: Optional[str] = None,
                  limit: int = 5) -> str:
        """Shared offline knowledge base (like `sapper kb`).

        Actions:
            add     target=title; description/detail/tags/commands/source opts
            search  target=query (first tag filters; limit applies)
            show    target=kb id (e.g. kb001) -> full entry
            list    browse entries (tags filter)
            import  target=.md file or dir -> one entry per file
            root    print the kb root dir
        """
        try:
            mod, k = _kb(root)
            tags = tags or []
            if action == "add":
                if not target:
                    return err("kb add needs target=title")
                body = detail or ""
                if detail_file:
                    body = Path(detail_file).read_text(encoding="utf-8")
                entry = k.add(title=target, description=description or "",
                              detail=body, commands=commands or [],
                              tags=tags, source=source or "")
                return json_out({"ok": True, "entry": entry})
            if action == "show":
                if not target:
                    return err("kb show needs target=kb id")
                return json_out({"ok": True, "entry": k.get(target)})
            if action == "list":
                entries = k.list_entries()
                if tags:
                    wants = {t.strip().lower() for t in tags}
                    entries = [e for e in entries if wants & {
                        t.lower() for t in e.get("tags", [])}]
                return json_out({"ok": True, "root": str(k.root),
                                 "entries": [mod._brief(e) for e in entries],
                                 "count": len(entries)})
            if action == "search":
                if not target:
                    return err("kb search needs target=query")
                hits = k.search(target, tag=tags[0] if tags else None,
                                limit=max(1, limit))
                return json_out({"ok": True, "hits": hits,
                                 "count": len(hits)})
            if action == "import":
                if not target:
                    return err("kb import needs target=.md file or dir")
                p = Path(target)
                if not p.exists():
                    return err(f"import path not found: {target}")
                files = sorted(p.glob("*.md")) if p.is_dir() else [p]
                if p.is_dir() and not files:
                    return err(f"no .md files under {target}")
                added = []
                for f in files:
                    parsed = mod.import_markdown(f, base_tags=tags,
                                                 source=str(f))
                    added.append(k.add(**parsed))
                return json_out({"ok": True, "imported": len(added),
                                 "entries": [{"id": e["id"],
                                              "title": e["title"]}
                                             for e in added]})
            if action == "root":
                return json_out({"ok": True, "root": str(k.root)})
            return err(f"unknown kb action {action!r} "
                       "(add|search|show|list|import|root)")
        except Exception as exc:
            return err(str(exc))
