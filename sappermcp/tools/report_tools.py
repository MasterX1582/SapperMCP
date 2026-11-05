"""Reporting tools: status/graph already live in graph_tools; this module
adds the HTML graph view, the multi-challenge board, and the generated
markdown engagement report."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from linuxmcp.util import err, json_out

from ..core.report import build_report
from ..core.sapperlib import sapper


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def sapper_view(store: str = ".sapper", out: Optional[str] = None,
                    return_html: bool = False) -> str:
        """Render the interactive HTML graph visualization (like
        `sapper view`). Writes a self-contained snapshot file; set
        return_html=True to also get the HTML in the response."""
        try:
            mod = sapper()
            st = mod.Store(Path(store))
            st.require()
            html = mod._render_static_html(st)
            out_path = Path(out) if out else \
                st.root.parent / "sapper-graph.html"
            out_path.write_text(html, encoding="utf-8")
            result = {"ok": True, "html_path": str(out_path.resolve()),
                      "bytes": len(html)}
            if return_html:
                result["html"] = html
            return json_out(result)
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_board(root: str = "runs") -> str:
        """One-line status per challenge graph under `root` - the commander's
        board (flags sub/rec, intel counts, open intents, last activity)."""
        try:
            mod = sapper()
            rows = mod._board_summary(Path(root))
            return json_out({"ok": True, "rows": rows, "count": len(rows),
                             "table": mod.render_board(rows)})
        except Exception as exc:
            return err(str(exc))

    @mcp.tool
    def sapper_report(store: str = ".sapper", out: Optional[str] = None,
                      title: Optional[str] = None,
                      include_docs: bool = False) -> str:
        """Generate a markdown engagement report from the graph: summary,
        flag ledger, typed findings (hosts/services/creds/vulns/loot), work
        log, timeline, hints. Writes `out` (default
        <store>/../sapper-report.md) and returns the markdown."""
        try:
            mod = sapper()
            st = mod.Store(Path(store))
            st.require()
            md = build_report(mod.build_graph_view(st), title=title,
                              include_docs=include_docs)
            out_path = Path(out) if out else \
                st.root.parent / "sapper-report.md"
            out_path.write_text(md, encoding="utf-8")
            return json_out({"ok": True,
                             "report_path": str(out_path.resolve()),
                             "markdown": md})
        except Exception as exc:
            return err(str(exc))
