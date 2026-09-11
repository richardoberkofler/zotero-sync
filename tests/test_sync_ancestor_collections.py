"""Regression test for issue #20: sync.run() must walk up the full
parentCollection chain and write an index note for every ancestor
collection, not just a paper's direct collection — while each note still
links only to its immediate parent.

Monkeypatches sync.build_papers()/sync.attach_annotations() directly
(same approach as tests/test_sync_run_retire.py) since the behavior under
test lives entirely in sync.run()'s collection-walking loop.

Also covers build_papers()/_collection_names_with_ancestors() directly:
a paper filed only in a subcollection must reference every collection
above it too, not just its direct one (see tests/test_sync_integration.py
for the end-to-end version against the real fixtures)."""

from __future__ import annotations

from pathlib import Path

import pytest

from zotero_sync import annotations, bbt_client, sync
from zotero_sync.config import Config
from zotero_sync.model import Paper


def _paper(citekey: str, collections: list[str]) -> Paper:
    return Paper(
        citekey=citekey,
        item_id=0,
        zotero_key=citekey,
        title=f"Title for {citekey}",
        authors=["Someone"],
        year="2020",
        item_type="journalArticle",
        doi=None,
        url=None,
        abstract=None,
        date_added=None,
        date_modified=None,
        collections=collections,
    )


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "Papers").mkdir()
    return tmp_path


@pytest.fixture
def no_network(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bbt_client, "check_ready", lambda: None)
    fake_db = tmp_path / "zotero.sqlite"
    fake_db.write_bytes(b"")
    monkeypatch.setattr(annotations, "default_zotero_sqlite_path", lambda: fake_db)
    monkeypatch.setattr(annotations, "copy_database", lambda source: fake_db)
    monkeypatch.setattr(sync, "attach_annotations", lambda papers, db_copy: None)
    monkeypatch.setattr(sync, "write_paper_note", lambda *args, **kwargs: None)


def test_run_writes_index_notes_for_every_ancestor_collection(monkeypatch, vault, no_network):
    # Root > A > B > C, paper filed only in C (the deepest subcollection).
    collection_info = {
        "names": {"root": "Root", "a": "A", "b": "B", "c": "C"},
        "parents": {"root": None, "a": "root", "b": "a", "c": "b"},
    }
    papers = [_paper("smith2020widget", ["C"])]
    monkeypatch.setattr(
        sync, "build_papers", lambda config, db_copy, counts=None: (papers, collection_info)
    )

    config = Config(vault_path=vault)
    counts = sync.run(config)

    written = {p.stem for p in (vault / "Collections").glob("*.md")}
    assert written == {"Root", "A", "B", "C"}

    def _parent_field(name: str) -> str:
        text = (vault / "Collections" / f"{name}.md").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("parent:"):
                return line
        raise AssertionError(f"no parent field in {name}.md")

    # Each note's `parent` field links only to its immediate parent, not the
    # whole chain — but `ancestors` carries the full chain above it, mirroring
    # how a paper's `collections` field lists every collection above it.
    assert 'parent: "B"' in _parent_field("C")
    assert 'parent: "A"' in _parent_field("B")
    assert 'parent: "Root"' in _parent_field("A")
    assert _parent_field("Root") == "parent:" or 'parent: "' not in _parent_field("Root")

    def _text(name: str) -> str:
        return (vault / "Collections" / f"{name}.md").read_text(encoding="utf-8")

    assert "Ancestors: [[B]], [[A]], [[Root]]" in _text("C")
    assert "Ancestors: [[A]], [[Root]]" in _text("B")
    assert "Ancestors: [[Root]]" in _text("A")
    assert "ancestors: []" in _text("Root")
    assert "Ancestors:" not in _text("Root")

    assert counts.created.get("Collections") == 4


def test_collection_names_with_ancestors_includes_full_chain():
    names = {"root": "Root", "a": "A", "b": "B", "c": "C"}
    parents = {"root": None, "a": "root", "b": "a", "c": "b"}

    # A paper filed only in the deepest subcollection must reference every
    # collection above it, not just its direct one.
    assert sync._collection_names_with_ancestors(["c"], names, parents) == [
        "C",
        "B",
        "A",
        "Root",
    ]

    # A top-level collection with no parent still resolves, just to itself.
    assert sync._collection_names_with_ancestors(["root"], names, parents) == ["Root"]

    # A paper filed in two collections that share an ancestor doesn't
    # duplicate that ancestor.
    assert sync._collection_names_with_ancestors(["b", "c"], names, parents) == [
        "B",
        "A",
        "Root",
        "C",
    ]
