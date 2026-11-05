"""Engagement/battle-report builder for a .sapper/ fact graph.

Turns the graph (facts, intents, hints) into a standalone markdown report:
summary, flag ledger, typed findings, intent work-log, timeline, hints.
Pure stdlib, no MCP deps - the tool layer wraps this.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

_KIND_ORDER = ("flag", "vuln", "cred", "loot", "host", "service", "note")
_KIND_TITLES = {
    "flag": "Captured flags",
    "vuln": "Vulnerabilities",
    "cred": "Credentials",
    "loot": "Loot / artifacts",
    "host": "Hosts",
    "service": "Services",
    "note": "Notes",
}


def _esc(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def _fmt_data(data) -> str:
    if not isinstance(data, dict) or not data:
        return "-"
    return ", ".join(f"{k}={v}" for k, v in data.items())


def build_report(graph: dict, *, title: Optional[str] = None,
                 include_docs: bool = False) -> str:
    """Render a markdown engagement report from sapper.build_graph_view()."""
    p = graph.get("project") or {}
    facts = [f for f in graph.get("facts", []) if f.get("id") != "goal"]
    intents = graph.get("intents", [])
    hints = graph.get("hints", [])
    open_i = [i for i in intents if i.get("to") is None]
    done_i = [i for i in intents if i.get("to") is not None]
    flags = [f for f in facts if f.get("kind") == "flag"]

    kinds: dict[str, int] = {}
    for f in facts:
        k = f.get("kind") or "untyped"
        kinds[k] = kinds.get(k, 0) + 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    name = title or f"Sapper engagement report - {p.get('id', 'proj')}"
    lines: list[str] = [f"# {name}", ""]
    lines.append(f"_Generated {now} by SapperMCP._")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Goal:** {p.get('goal', '-')}")
    if p.get("origin"):
        lines.append(f"- **Origin:** {p['origin']}")
    lines.append(f"- **Status:** {p.get('status', '-')}")
    if p.get("created_at"):
        lines.append(f"- **Started:** {p['created_at']}")
    if p.get("completed_at"):
        lines.append(f"- **Completed:** {p['completed_at']}")
    kind_txt = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) or "none"
    lines.append(
        f"- **Graph:** {len(facts)} facts ({kind_txt}), "
        f"{len(done_i)} concluded / {len(open_i)} open intents, {len(hints)} hints"
    )
    submitted = sum(1 for f in flags
                    if (f.get("data") or {}).get("status") == "submitted")
    if flags:
        lines.append(f"- **Flags:** {len(flags)} captured, {submitted} submitted")
    lines.append("")

    if flags:
        lines.append("## Flag ledger")
        lines.append("")
        lines.append("| id | challenge | status | value |")
        lines.append("|---|---|---|---|")
        for f in flags:
            d = f.get("data") or {}
            lines.append(
                f"| {f['id']} | {_esc(d.get('challenge')) or '-'} | "
                f"{_esc(d.get('status') or 'recorded')} | `{_esc(d.get('value'))}` |"
            )
        lines.append("")

    by_kind: dict[str, list[dict]] = {}
    for f in facts:
        by_kind.setdefault(f.get("kind") or "untyped", []).append(f)
    ordered = [k for k in _KIND_ORDER if k in by_kind and k != "flag"]
    ordered += sorted(k for k in by_kind if k not in _KIND_ORDER and k != "flag")
    if ordered:
        lines.append("## Findings")
        lines.append("")
        for k in ordered:
            lines.append(f"### {_KIND_TITLES.get(k, k.capitalize())}")
            lines.append("")
            lines.append("| id | title | description | data | recorded |")
            lines.append("|---|---|---|---|---|")
            for f in sorted(by_kind[k], key=lambda x: x.get("created_at", "")):
                lines.append(
                    f"| {f['id']} | {_esc(f.get('title')) or '-'} | "
                    f"{_esc(f.get('description'))} | {_esc(_fmt_data(f.get('data')))} | "
                    f"{_esc(f.get('created_at'))} |"
                )
            lines.append("")

    if intents:
        lines.append("## Work log (intents)")
        lines.append("")
        lines.append("| id | status | from -> to | worker | description |")
        lines.append("|---|---|---|---|---|")
        for i in sorted(intents, key=lambda x: x.get("created_at", "")):
            frm = ",".join(i.get("from") or [])
            to = i.get("to") or "open"
            lines.append(
                f"| {i['id']} | {i.get('status', '-')} | {frm} -> {to} | "
                f"{_esc(i.get('worker')) or '-'} | {_esc(i.get('description'))} |"
            )
        lines.append("")

    events = sorted(
        [("fact", f) for f in facts] + [("intent", i) for i in intents],
        key=lambda t: t[1].get("created_at", ""),
    )
    if events:
        lines.append("## Timeline")
        lines.append("")
        for kind, node in events:
            stamp = node.get("created_at", "?")
            label = f"{kind} {node['id']}"
            txt = node.get("title") or node.get("description", "")
            lines.append(f"- `{stamp}` **{label}** - {_esc(txt)[:160]}")
        lines.append("")

    if hints:
        lines.append("## Human hints")
        lines.append("")
        for h in hints:
            lines.append(f"- **{h['id']}** ({h.get('creator', '?')}, "
                         f"{h.get('created_at', '?')}): {_esc(h.get('content'))}")
        lines.append("")

    if include_docs:
        documented = [f for f in facts if f.get("doc")] + \
                     [i for i in intents if i.get("doc")]
        if documented:
            lines.append("## Appendix - node documents")
            lines.append("")
            for n in documented:
                lines.append(f"### {n['id']} - {n.get('title') or n.get('description', '')[:80]}")
                lines.append("")
                lines.append(str(n["doc"]))
                lines.append("")

    return "\n".join(lines)
