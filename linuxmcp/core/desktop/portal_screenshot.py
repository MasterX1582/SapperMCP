#!/usr/bin/env python3
"""XDG portal screenshot client (standalone; only needs PyGObject).

Invoked by screen.py under a Python that has `gi` (usually the system
/usr/bin/python3 on Ubuntu/Zorin). The first non-interactive call makes
GNOME show a one-time "allow screenshot" prompt; the grant is persisted
by the portal and later calls are silent.

Usage: portal_screenshot.py [timeout_seconds] [--interactive]
Stdout: 'ok <file://uri>' | 'denied <code>' | 'timeout' | 'error <msg>'
"""
import sys
import time


def main() -> int:
    try:
        from gi.repository import Gio, GLib
    except ImportError:
        print("error PyGObject (gi) not available")
        return 4

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    interactive = '--interactive' in sys.argv
    timeout = int(args[0]) if args else 45

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    except Exception as e:
        print(f"error no session bus: {e}")
        return 4
    token = f"lmcp{int(time.time() * 1000)}"
    sender = bus.get_unique_name().lstrip(':').replace('.', '_')
    req_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = GLib.MainLoop()
    result = {"done": False, "resp": None, "results": {}}

    def on_response(_b, _s, _p, _i, _sig, params, *_a):
        resp, results = params.unpack()
        result.update(done=True, resp=resp,
                      results=dict(results or {}))
        loop.quit()

    sub = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request", "Response",
        req_path, None, Gio.DBusSignalFlags.NONE, on_response)

    try:
        bus.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot", "Screenshot",
            GLib.Variant("(sa{sv})", (
                "",
                {"handle_token": GLib.Variant("s", token),
                 "interactive": GLib.Variant("b", interactive),
                 "modal": GLib.Variant("b", False)},
            )),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE, 10000, None)
    except Exception as e:
        print(f"error portal call failed: {e}")
        return 4

    GLib.timeout_add_seconds(timeout, loop.quit)
    loop.run()
    bus.signal_unsubscribe(sub)

    if not result["done"]:
        print("timeout")
        return 2
    if result["resp"] == 0:
        print(f"ok {result['results'].get('uri', '')}")
        return 0
    print(f"denied {result['resp']}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
