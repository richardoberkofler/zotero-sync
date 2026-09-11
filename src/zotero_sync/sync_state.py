from __future__ import annotations

import json
from pathlib import Path

STATE_FILENAME = ".zotero-sync-state.json"


def state_path(vault_path: Path) -> Path:
    return vault_path / STATE_FILENAME


def load_state(vault_path: Path) -> dict[str, dict]:
    """Maps Zotero item key -> {"version": int, "collections": [...],
    "tags": [...] (already slugified, see notes/paper.py's
    _slugify_tag())} as of the last successful web-mode sync — the shared
    snapshot #24 designed for change detection (notes/paper.py's
    detect_changes()) plus the version If-Unmodified-Since-Version needs
    for a future write. Safe to lose: if this file goes missing, the next
    write becomes unconditional (or a stale guess 412s and the caller
    re-syncs), and the next read just treats every paper as unseen
    (bootstrap case) — never silent data loss, per
    docs/research/2023-zotero-web-api-2way-sync.md."""
    path = state_path(vault_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(vault_path: Path, state: dict[str, dict]) -> None:
    state_path(vault_path).write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
