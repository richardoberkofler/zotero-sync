from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import tempfile
from pathlib import Path

from zotero_sync.errors import PreconditionError, SchemaDriftError

# zotero.sqlite's own `libraryID` for the default local library ("My
# Library") — mirrors sync.py's BBT_LIBRARY_ID assumption that zotero-sync
# only targets library id 1 (multi-library support is out of scope). Not
# imported from sync.py to avoid a circular import (sync.py imports this
# module).
ZOTERO_LIBRARY_ID = 1

# Per research/01-zotero-access-method-findings.md §2: zotero.sqlite's schema
# is not guaranteed stable across Zotero releases, so we verify these columns
# exist before trusting any read of them, and fail loudly on drift rather
# than silently misreading.
EXPECTED_ANNOTATION_COLUMNS = {
    "itemID",
    "parentItemID",
    "type",
    "text",
    "comment",
    "color",
    "pageLabel",
    "sortIndex",
    "position",
}


def default_zotero_sqlite_path() -> Path | None:
    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        import os

        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            candidates.append(Path(userprofile) / "Zotero" / "zotero.sqlite")
    elif system == "Darwin":
        candidates.append(Path.home() / "Zotero" / "zotero.sqlite")
    else:
        candidates.append(Path.home() / "Zotero" / "zotero.sqlite")

    for path in candidates:
        if path.exists():
            return path
    return None


def copy_database(source: Path) -> Path:
    """Copies zotero.sqlite to a temp file so we never read the live,
    potentially-locked file (per research/01-zotero-access-method-findings.md §2)."""
    if not source.exists():
        raise PreconditionError(
            f"Zotero database not found at {source} — set the correct path "
            "or make sure Zotero has been run at least once."
        )
    fd, tmp_name = tempfile.mkstemp(suffix=".sqlite", prefix="zotero-sync-")
    os.close(fd)
    tmp = Path(tmp_name)
    shutil.copy2(source, tmp)
    return tmp


def _verify_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(itemAnnotations)")}
    missing = EXPECTED_ANNOTATION_COLUMNS - columns
    if missing:
        raise SchemaDriftError(
            "zotero.sqlite's itemAnnotations table is missing expected "
            f"column(s) {sorted(missing)} — the schema has likely changed "
            "in a newer Zotero release. Refusing to read annotations rather "
            "than risk misreading them."
        )


def item_ids_by_key(db_copy_path: Path, keys: list[str]) -> dict[str, int]:
    """Maps Zotero item 'key' (the Local API's string identifier) to the
    internal numeric itemID used by zotero.sqlite's own tables."""
    conn = sqlite3.connect(f"file:{db_copy_path}?mode=ro", uri=True)
    try:
        # `key` is only unique within a single library, not across the whole
        # database — a group library synced locally alongside "My Library"
        # could have an item sharing the same `key` string as a personal
        # library item. Scope to ZOTERO_LIBRARY_ID so dict(rows) can't
        # collapse two different items' rows into one arbitrary itemID.
        placeholders = ",".join("?" * len(keys))
        rows = conn.execute(
            f"SELECT key, itemID FROM items WHERE key IN ({placeholders}) AND libraryID = ?",
            [*keys, ZOTERO_LIBRARY_ID],
        ).fetchall()
        return dict(rows)
    finally:
        conn.close()


def read_annotations(db_copy_path: Path, paper_item_ids: dict[str, int]) -> dict[str, list[dict]]:
    """paper_item_ids: {citekey: internal Zotero itemID}. Returns
    {citekey: [annotation dicts]}, each annotation ordered by
    (pageLabel, sortIndex) — reading order. Returns rows for every
    itemAnnotations.type code (highlight, note, image, underline, ...);
    filtering to the types zotero-sync actually renders is sync.py's job
    (see sync.ANNOTATION_TYPE_KINDS)."""
    conn = sqlite3.connect(f"file:{db_copy_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        _verify_schema(conn)
        result: dict[str, list[dict]] = {}
        for citekey, item_id in paper_item_ids.items():
            rows = conn.execute(
                """
                SELECT ia.type, ia.text, ia.comment, ia.color, ia.pageLabel,
                       ia.sortIndex, ia.position
                FROM itemAnnotations ia
                JOIN itemAttachments att ON att.itemID = ia.parentItemID
                WHERE att.parentItemID = ?
                ORDER BY ia.pageLabel, ia.sortIndex
                """,
                (item_id,),
            ).fetchall()
            result[citekey] = [dict(row) for row in rows]
        return result
    finally:
        conn.close()
