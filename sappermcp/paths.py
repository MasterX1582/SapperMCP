"""Locate the bundled sapper-v2 toolkit tree (the dir holding lib/sapper.py)."""

from __future__ import annotations

import os
from pathlib import Path


def sapper_root() -> Path:
    """Root of the sapper toolkit checkout.

    Resolution order:
      1. $SAPPER_ROOT (explicit override - set this for pip-installed use)
      2. repo layout: <repo>/sappermcp/paths.py -> <repo>/lib/sapper.py
      3. nearest ancestor containing lib/sapper.py
    """
    env = os.environ.get("SAPPER_ROOT")
    if env:
        return Path(env).expanduser()
    here = Path(__file__).resolve()
    for cand in (here.parent.parent, *here.parents):
        if (cand / "lib" / "sapper.py").exists():
            return cand
    return here.parent.parent


def sapper_cli() -> Path:
    return sapper_root() / "lib" / "sapper.py"


def sapper_lib() -> Path:
    return sapper_root() / "lib"
