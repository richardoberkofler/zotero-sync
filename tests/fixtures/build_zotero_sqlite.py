"""Builds tests/fixtures/zotero.sqlite: a minimal, hand-rolled stand-in for a
real Zotero library database.

Only the tables/columns that src/zotero_sync/annotations.py actually reads
are created here — this is not a full Zotero schema dump. If you need to
regenerate the fixture (e.g. after annotations.py starts reading a new
column), edit the DATA below and rerun:

    python tests/fixtures/build_zotero_sqlite.py

This overwrites tests/fixtures/zotero.sqlite in place.

Schema notes (see annotations.py's EXPECTED_ANNOTATION_COLUMNS and its
docstring on itemAnnotations being undocumented/unstable across Zotero
releases — these column names were confirmed by inspecting a live database,
not from official docs):

- items(itemID, key): maps the Local API's string item "key" to the
  internal numeric itemID used everywhere else in zotero.sqlite.
- itemAttachments(itemID, parentItemID): itemID is the attachment's own
  itemID; parentItemID is the itemID of the paper item it's attached to.
- itemAnnotations(itemID, parentItemID, type, text, comment, color,
  pageLabel, sortIndex, position): parentItemID here is confusingly a
  *different* relationship than itemAttachments.parentItemID — it's the
  itemID of the itemAttachments row the annotation lives on (i.e. the PDF),
  not the paper. read_annotations()'s query joins through both:
  itemAnnotations.parentItemID -> itemAttachments.itemID, then filters on
  itemAttachments.parentItemID (the paper's itemID). `type` is an integer
  code; 1 = highlight (ANNOTATION_TYPE_HIGHLIGHT in sync.py). Other codes
  (e.g. 2 here, standing in for a sticky "note" annotation) exist too and
  must NOT be treated as highlights.

Item keys/ids are kept consistent with tests/fixtures/local_api/items.json
and tests/fixtures/bbt/citationkeys.json so all three fixtures compose into
one coherent fake library:

  itemID  key        citekey (via BBT)      attachment itemID  annotations
  1       AAAA1111   smith2020neural        101                2 highlights + 1 non-highlight
  2       BBBB2222   jones2019language      102                1 highlight
  3       CCCC3333   lee2021optimization    103                (none)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "zotero.sqlite"

# (itemID, key) — the paper items. Keys match local_api/items.json.
ITEMS = [
    (1, "AAAA1111"),
    (2, "BBBB2222"),
    (3, "CCCC3333"),
    # Attachments and annotations get their own itemID rows too, in a real
    # database, but item_ids_by_key() only ever looks up paper items by
    # key, so we don't need entries for 101/102/103/201.. here.
]

# (itemID, parentItemID) — one PDF attachment per paper.
ITEM_ATTACHMENTS = [
    (101, 1),
    (102, 2),
    (103, 3),
]

# (itemID, parentItemID, type, text, comment, color, pageLabel, sortIndex, position)
# parentItemID points at the itemAttachments.itemID above (the PDF), not the paper.
ITEM_ANNOTATIONS = [
    (
        201,
        101,
        1,  # highlight
        "Deep learning models require large amounts of structured training data.",
        "Key point about representation learning.",
        "#ffd400",
        "12",
        "00001|000123|00045",
        '{"pageIndex": 11, "rects": [[100, 200, 300, 220]]}',
    ),
    (
        202,
        101,
        1,  # highlight
        "The optimization landscape is non-convex but well-behaved in practice.",
        None,
        "#ff6666",
        "13",
        "00001|000130|00010",
        '{"pageIndex": 12, "rects": [[100, 400, 320, 420]]}',
    ),
    (
        203,
        101,
        2,  # NOT a highlight — sticky note annotation, proves the type filter works
        None,
        "Follow up on this citation later.",
        "#2ea8e5",
        "14",
        "00001|000140|00000",
        "{}",
    ),
    (
        204,
        102,
        1,  # highlight
        "Evaluation methodology varies widely across benchmarks.",
        None,
        "#5fb236",
        "3",
        "00001|000030|00000",
        '{"pageIndex": 2, "rects": [[50, 100, 250, 120]]}',
    ),
    # Paper 3 (itemID 3, attachment 103) intentionally has zero annotations,
    # to exercise the "no highlights" path.
]


def build(db_path: Path = DB_PATH) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INTEGER)"
        )
        conn.execute(
            "CREATE TABLE itemAnnotations ("
            "itemID INTEGER PRIMARY KEY, parentItemID INTEGER, type INTEGER, "
            "text TEXT, comment TEXT, color TEXT, pageLabel TEXT, "
            "sortIndex TEXT, position TEXT"
            ")"
        )

        conn.executemany("INSERT INTO items (itemID, key) VALUES (?, ?)", ITEMS)
        conn.executemany(
            "INSERT INTO itemAttachments (itemID, parentItemID) VALUES (?, ?)",
            ITEM_ATTACHMENTS,
        )
        conn.executemany(
            "INSERT INTO itemAnnotations "
            "(itemID, parentItemID, type, text, comment, color, pageLabel, sortIndex, position) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ITEM_ANNOTATIONS,
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    build()
    print(f"Wrote {DB_PATH}")
