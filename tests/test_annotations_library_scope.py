"""Regression test for issue #12: annotations.item_ids_by_key() must scope
its lookup by libraryID, or a group-library item sharing a `key` string with
a "My Library" item can collapse dict(rows) onto the wrong itemID and
misroute that item's annotations.

tests/fixtures/zotero.sqlite (via build_zotero_sqlite.py) contains exactly
this collision: itemID 1 (libraryID 1, "My Library") and itemID 999
(libraryID 2, a decoy group library) both use key "AAAA1111". itemID 999 has
its own attachment/annotation ("GROUP LIBRARY DECOY...") that must never
surface when looking up key "AAAA1111".
"""

from __future__ import annotations

import shutil
from pathlib import Path

from zotero_sync import annotations

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _db_copy(tmp_path):
    dest = tmp_path / "zotero.sqlite"
    shutil.copy2(FIXTURES_DIR / "zotero.sqlite", dest)
    return dest


def test_item_ids_by_key_scopes_to_my_library(tmp_path):
    db = _db_copy(tmp_path)

    result = annotations.item_ids_by_key(db, ["AAAA1111", "BBBB2222", "CCCC3333"])

    # Must resolve to the "My Library" (libraryID 1) itemID, not the
    # group-library decoy's itemID 999, despite the shared key.
    assert result == {"AAAA1111": 1, "BBBB2222": 2, "CCCC3333": 3}


def test_attach_annotations_does_not_leak_other_library_items(tmp_path):
    db = _db_copy(tmp_path)

    item_id_by_key = annotations.item_ids_by_key(db, ["AAAA1111"])
    paper_item_ids = {"smith2020neural": item_id_by_key["AAAA1111"]}

    result = annotations.read_annotations(db, paper_item_ids)

    texts = [row["text"] for row in result["smith2020neural"]]
    assert not any("DECOY" in (t or "") for t in texts)
    assert any("Deep learning models" in (t or "") for t in texts)
