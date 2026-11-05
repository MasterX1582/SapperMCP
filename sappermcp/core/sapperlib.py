"""Lazy importlib loaders for the bundled sapper lib modules.

lib/sapper.py is POSIX-only (fcntl). Loading lazily keeps tool registration and
`sappermcp --list-tools` working on any platform, and surfaces a clear error at
call time if the toolkit cannot be loaded.
"""

from __future__ import annotations

import importlib.util

from ..paths import sapper_lib

_cache: dict[str, object] = {}


def _load(name: str, filename: str):
    if name not in _cache:
        path = sapper_lib() / filename
        if not path.exists():
            raise RuntimeError(
                f"sapper toolkit file not found at {path} "
                "(set SAPPER_ROOT to the sapper-v2 checkout)"
            )
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:
            raise RuntimeError(f"could not load {path}: {exc}") from exc
        _cache[name] = mod
    return _cache[name]


def sapper():
    """The bundled lib/sapper.py as a module (Store, renderers, cmd helpers)."""
    return _load("_sappermcp_sapper", "sapper.py")


def kb():
    """The bundled lib/kb.py (KnowledgeBase, import_markdown)."""
    return _load("_sappermcp_kb", "kb.py")


def arena():
    """The bundled lib/arena.py (ArenaClient, ArenaError)."""
    return _load("_sappermcp_arena", "arena.py")
