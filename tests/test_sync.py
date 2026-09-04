"""Covers #11: build_papers must not silently drop items that Better BibTeX
has no citekey for — the drop should surface as a counts.errors entry
instead of vanishing with no trace."""

from __future__ import annotations

from pathlib import Path

from zotero_sync import bbt_client, local_api, sync
from zotero_sync.config import Config
from zotero_sync.vault import SyncCounts


def _item(key: str, title: str) -> dict:
    return {
        "data": {
            "key": key,
            "itemType": "journalArticle",
            "title": title,
            "creators": [],
            "tags": [],
            "collections": [],
        }
    }


def test_build_papers_reports_missing_citekey_as_error(monkeypatch, tmp_path):
    items = [_item("AAAA1111", "Has A Citekey"), _item("BBBB2222", "Missing Its Citekey")]

    monkeypatch.setattr(local_api, "list_paper_items", lambda collection_key=None: items)
    monkeypatch.setattr(local_api, "list_collections", lambda: [])
    monkeypatch.setattr(
        bbt_client,
        "citationkeys",
        lambda item_ids: {f"{sync.BBT_LIBRARY_ID}:AAAA1111": "smith2024widget"},
    )
    monkeypatch.setattr("zotero_sync.annotations.item_ids_by_key", lambda db_copy_path, keys: {})

    config = Config(vault_path=tmp_path)
    counts = SyncCounts()

    papers, _ = sync.build_papers(config, Path("unused.sqlite"), counts)

    assert [p.citekey for p in papers] == ["smith2024widget"]
    assert len(counts.errors) == 1
    assert "Missing Its Citekey" in counts.errors[0]
    assert "no Better BibTeX citekey" in counts.errors[0]


def test_build_papers_without_counts_still_drops_silently(monkeypatch, tmp_path):
    # Backward-compatible default: callers that don't pass counts keep the
    # old silent-drop behavior rather than crashing.
    items = [_item("BBBB2222", "Missing Its Citekey")]

    monkeypatch.setattr(local_api, "list_paper_items", lambda collection_key=None: items)
    monkeypatch.setattr(local_api, "list_collections", lambda: [])
    monkeypatch.setattr(bbt_client, "citationkeys", lambda item_ids: {})
    monkeypatch.setattr("zotero_sync.annotations.item_ids_by_key", lambda db_copy_path, keys: {})

    config = Config(vault_path=tmp_path)

    papers, _ = sync.build_papers(config, Path("unused.sqlite"))

    assert papers == []
