from __future__ import annotations

import datetime as dt
from pathlib import Path

from zotero_sync.filenames import sanitize
from zotero_sync.model import Paper
from zotero_sync.notes import index as index_notes
from zotero_sync.notes import paper as paper_notes

PAPERS_DIR = "Papers"
TRASH_DIR = ".trash"


class SyncCounts:
    def __init__(self) -> None:
        self.created: dict[str, int] = {}
        self.updated: dict[str, int] = {}
        self.retired: list[str] = []
        self.errors: list[str] = []

    def bump(self, category: str, action: str) -> None:
        bucket = self.created if action == "created" else self.updated
        bucket[category] = bucket.get(category, 0) + 1

    def summary_line(self) -> str:
        parts = []
        for category in ("Papers", "Collections", "Authors", "Keywords"):
            c = self.created.get(category, 0)
            u = self.updated.get(category, 0)
            if category == "Papers":
                parts.append(f"{category}: {c} created, {u} updated, {len(self.retired)} retired")
            else:
                parts.append(f"{category}: {c} created, {u} updated")
        return " · ".join(parts)


def paper_note_path(vault_path: Path, citekey: str) -> Path:
    return vault_path / PAPERS_DIR / f"{citekey}.md"


def index_note_path(vault_path: Path, kind: str, title: str) -> Path:
    folder = index_notes.INDEX_FOLDERS[kind]
    return vault_path / folder / f"{sanitize(title)}.md"


def existing_paper_citekeys(vault_path: Path) -> set[str]:
    papers_dir = vault_path / PAPERS_DIR
    if not papers_dir.exists():
        return set()
    return {p.stem for p in papers_dir.glob("*.md")}


def write_paper_note(
    vault_path: Path, paper: Paper, fields: list[str], dry_run: bool, counts: SyncCounts
) -> None:
    path = paper_note_path(vault_path, paper.citekey)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        new_text = paper_notes.update_existing_note(
            path.read_text(encoding="utf-8"), paper, fields
        )
        action = "updated"
    else:
        new_text = paper_notes.render_new_note(paper, fields)
        action = "created"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    counts.bump("Papers", action)


def write_index_note(
    vault_path: Path, kind: str, title: str, parent: str | None, dry_run: bool, counts: SyncCounts
) -> None:
    path = index_note_path(vault_path, kind, title)
    action = "updated" if path.exists() else "created"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(index_notes.render_index_note(kind=kind, title=title, parent=parent), encoding="utf-8")
    counts.bump(kind.capitalize() + "s", action)


def retire_note(vault_path: Path, citekey: str, dry_run: bool, counts: SyncCounts) -> None:
    src = paper_note_path(vault_path, citekey)
    if not src.exists():
        return
    if not dry_run:
        trash_dir = vault_path / TRASH_DIR
        trash_dir.mkdir(parents=True, exist_ok=True)
        dest = trash_dir / src.name
        if dest.exists():
            stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
            dest = trash_dir / f"{src.stem}-{stamp}.md"
        try:
            src.rename(dest)
        except OSError as exc:
            counts.errors.append(f"{citekey}: failed to retire ({exc})")
            return
    counts.retired.append(citekey)
