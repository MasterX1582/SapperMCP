"""Findings exporters for the SapperMCP GUI (and anything else that has a
list of fact dicts from a .sapper graph).

Formats: markdown table, JSON, and a simple XML document. Pure stdlib.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import escape


def _fields(f: dict) -> dict:
    return {
        "id": f.get("id", ""),
        "kind": f.get("kind") or "note",
        "title": f.get("title") or "",
        "description": f.get("description") or "",
        "data": f.get("data") or {},
        "created_at": f.get("created_at") or "",
        "creator": f.get("creator") or "",
        "doc": f.get("doc") or "",
    }


def to_json(facts: list[dict]) -> str:
    return json.dumps(
        {"findings": [_fields(f) for f in facts]},
        ensure_ascii=False, indent=2) + "\n"


def to_xml(facts: list[dict]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<findings>"]
    for f in facts:
        e = _fields(f)
        out.append(f'  <finding id="{escape(str(e["id"]))}" '
                   f'kind="{escape(str(e["kind"]))}">')
        for tag in ("title", "description", "created_at", "creator", "doc"):
            if e[tag]:
                out.append(f"    <{tag}>{escape(str(e[tag]))}</{tag}>")
        if e["data"]:
            out.append("    <data>")
            for k, v in e["data"].items():
                out.append(f'      <entry key="{escape(str(k))}">'
                           f"{escape(str(v))}</entry>")
            out.append("    </data>")
        out.append("  </finding>")
    out.append("</findings>")
    return "\n".join(out) + "\n"


def to_markdown(facts: list[dict]) -> str:
    def esc(t) -> str:
        return str(t or "").replace("|", "\\|").replace("\n", " ")

    out = ["# Sapper findings export", "",
           "| id | kind | title | description | data | recorded |",
           "|---|---|---|---|---|---|"]
    for f in facts:
        e = _fields(f)
        dtxt = ", ".join(f"{k}={v}" for k, v in e["data"].items()) or "-"
        out.append(f"| {e['id']} | {e['kind']} | {esc(e['title'])} | "
                   f"{esc(e['description'])} | {esc(dtxt)} | "
                   f"{esc(e['created_at'])} |")
    docs = [f for f in facts if f.get("doc")]
    if docs:
        out += ["", "## Detail documents", ""]
        for f in docs:
            out += [f"### {f['id']} - {f.get('title') or f['id']}", "",
                    f["doc"], ""]
    return "\n".join(out) + "\n"


_FORMATS = {"md": to_markdown, "json": to_json, "xml": to_xml}


def export_findings(facts: list[dict], fmt: str) -> str:
    """Render facts as md|json|xml. fmt is a file extension or name."""
    fn = _FORMATS.get(fmt.lower().lstrip("."))
    if fn is None:
        raise ValueError(f"unknown format {fmt!r} (use md, json or xml)")
    return fn(facts)
