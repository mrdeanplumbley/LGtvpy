"""Tiny JSON config store for pairing keys and TV MAC addresses.

Stored at ``~/.lgtv/config.json``, keyed by TV IP::

    {
      "192.168.1.61": {
        "client_key": "abcdef...",
        "mac": "aa:bb:cc:dd:ee:ff"
      }
    }

Commands that don't specify an IP use :func:`get_default_ip`: when exactly
one TV has been paired, that's the default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DEFAULT_PATH = Path.home() / ".lgtv" / "config.json"


def load(path: Optional[Path] = None) -> dict:
    path = path or DEFAULT_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(cfg: dict, path: Optional[Path] = None) -> None:
    path = path or DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def get_default_ip(path: Optional[Path] = None) -> Optional[str]:
    """The IP to use when none was given: the single paired TV, else None."""
    tvs = list(load(path))
    return tvs[0] if len(tvs) == 1 else None


def get_tv(ip: str, path: Optional[Path] = None) -> dict:
    """Return the stored entry for one TV (empty dict if unknown)."""
    return load(path).get(ip, {})


def update_tv(ip: str, path: Optional[Path] = None, **fields) -> None:
    """Merge ``fields`` into the stored entry for ``ip``."""
    cfg = load(path)
    cfg.setdefault(ip, {}).update({k: v for k, v in fields.items() if v is not None})
    save(cfg, path)
