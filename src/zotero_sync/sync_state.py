from __future__ import annotations

import json
from pathlib import Path

STATE_FILENAME = ".zotero-sync-state.json"


def state_path(vault_path: Path) -> Path:
    return vault_path / STATE_FILENAME


def load_state(vault_path: Path) -> dict[str, int]:
    """Maps Zotero item key -> last-known Last-Modified-Version, so a
    future write can send a correct If-Unmodified-Since-Version and a
    future read can tell what changed since last sync. Safe to lose: if
    this file goes missing, the next write becomes unconditional (or a
    stale guess 412s and the caller re-syncs) — never silent data loss,
    per docs/research/2023-zotero-web-api-2way-sync.md."""
    path = state_path(vault_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(vault_path: Path, state: dict[str, int]) -> None:
    state_path(vault_path).write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
