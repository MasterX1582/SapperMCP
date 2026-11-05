#!/usr/bin/env python3
"""End-to-end smoke test for a running SapperMCP HTTP server.

Usage:
    python tests/smoke_test_mcp.py [url]
    # default url: http://127.0.0.1:3940/mcp

Creates a throwaway .sapper graph under /tmp and exercises every tool
category: graph CRUD, work lifecycle, recall/doc, flag ledger, kb,
reporting (view/board/report), the generic CLI, plus a couple of
LinuxMCP calls to prove both toolsets share the server.

Requires: fastmcp (same venv as the server). Exits non-zero on failure.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from fastmcp import Client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3940/mcp"
FAILURES = []


def check(name, result_text, must_have=None, want_ok=True):
    ok = True
    detail = ""
    try:
        data = json.loads(result_text)
        if want_ok and data.get("ok") is not True:
            ok = False
            detail = f"not ok: {str(data)[:200]}"
        if must_have:
            for k in must_have:
                if k not in data:
                    ok = False
                    detail += f" missing {k}"
    except Exception as e:
        ok = False
        detail = f"unparsable: {e}: {result_text[:160]}"
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAILURES.append(name)
    return data if ok else {}


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="sappermcp-test-"))
    store = str(tmp / ".sapper")
    print(f"test graph: {store}")

    async with Client(URL) as client:
        tools = {t.name for t in await client.list_tools()}
        print(f"tools exposed: {len(tools)}")
        for name in ("sapper_init", "sapper_status", "sapper_report",
                     "sapper_cli", "run_command"):
            if name not in tools:
                print(f"[FAIL] tool missing: {name}")
                FAILURES.append(f"missing {name}")

        async def call(tool, **kw):
            res = await client.call_tool(tool, kw)
            return "".join(c.text for c in res.content if hasattr(c, "text"))

        # --- graph lifecycle ------------------------------------------------
        check("sapper_init", await call(
            "sapper_init", store=store,
            goal="smoke test goal: verify MCP control"))
        f = check("sapper_fact", await call(
            "sapper_fact", store=store,
            description="target host 10.0.0.5 is up",
            kind="host", title="host up",
            data={"ip": "10.0.0.5"}), must_have=["fact"])
        fid = f.get("fact", {}).get("id")
        i = check("sapper_intent", await call(
            "sapper_intent", store=store, from_ids=[fid],
            description="port-scan the host"), must_have=["intent"])
        iid = i.get("intent", {}).get("id")
        check("sapper_hint", await call(
            "sapper_hint", store=store, content="focus web ports first"))
        check("sapper_hint --list", await call(
            "sapper_hint", store=store, list=True), must_have=["hints"])
        check("sapper_status", await call("sapper_status", store=store),
              must_have=["status"])
        check("sapper_graph", await call("sapper_graph", store=store),
              must_have=["graph"])
        check("sapper_validate", await call("sapper_validate", store=store),
              must_have=["valid"])
        fr = check("sapper_frontier", await call(
            "sapper_frontier", store=store), must_have=["frontier"])
        if fr.get("frontier", [{}])[0].get("id") != iid:
            print(f"[WARN] frontier head is not {iid}: {fr}")
        p = check("sapper_pick --claim", await call(
            "sapper_pick", store=store, claim=True, worker="tester"),
              must_have=["id"])
        check("sapper_recall", await call(
            "sapper_recall", store=store, query="port scan host"), )
        check("sapper_doc write", await call(
            "sapper_doc", store=store, id=fid, set="# detail\nnmap showed 22/80"))
        check("sapper_doc read", await call(
            "sapper_doc", store=store, id=fid), must_have=["doc"])
        check("sapper_done", await call(
            "sapper_done", store=store, id=p.get("id", iid),
            fact="ports 22 and 80 open", kind="service",
            data={"ports": "22,80"}, worker="tester"), must_have=["fact"])

        # --- flag ledger -----------------------------------------------------
        fl = check("sapper_flag", await call(
            "sapper_flag", store=store, value="flag{smoke_test_123}",
            challenge="c01"), must_have=["fact_id"])
        dup = json.loads(await call(
            "sapper_flag", store=store, value="flag{smoke_test_123}"))
        if dup.get("ok") is False and "already recorded" in dup.get("error", ""):
            print("[PASS] sapper_flag dedupe")
        else:
            print(f"[FAIL] sapper_flag dedupe {dup}")
            FAILURES.append("sapper_flag dedupe")

        # --- kb --------------------------------------------------------------
        check("sapper_kb list", await call("sapper_kb", action="list"),
              must_have=["entries"])
        check("sapper_kb search", await call(
            "sapper_kb", action="search", target="sqli"), )
        k = check("sapper_kb add", await call(
            "sapper_kb", action="add", target="smoke test entry",
            description="temp entry from smoke test",
            tags=["test"], root=str(tmp / "kb")), must_have=["entry"])
        if k.get("entry", {}).get("id"):
            check("sapper_kb show", await call(
                "sapper_kb", action="show",
                target=k["entry"]["id"], root=str(tmp / "kb")),
                must_have=["entry"])

        # --- reporting -------------------------------------------------------
        check("sapper_view", await call("sapper_view", store=store),
              must_have=["html_path"])
        check("sapper_board", await call("sapper_board", root=str(tmp.parent)),
              must_have=["rows"])
        r = check("sapper_report", await call(
            "sapper_report", store=store), must_have=["markdown"])
        if r and "flag{smoke_test_123}" not in r.get("markdown", ""):
            print("[FAIL] report missing flag ledger entry")
            FAILURES.append("report flag ledger")

        # --- generic CLI + project ops ---------------------------------------
        check("sapper_cli status", await call(
            "sapper_cli", store=store, args=["status"]), must_have=["stdout"])
        check("sapper_complete", await call(
            "sapper_complete", store=store, from_ids=[fid],
            note="smoke test done"), must_have=["intent"])

        # --- linuxmcp toolset still present ----------------------------------
        check("run_command (linuxmcp)", await call(
            "run_command", command="echo sappermcp-ok"), must_have=["ok"])

    print()
    if FAILURES:
        print("FAILURES:", FAILURES)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
