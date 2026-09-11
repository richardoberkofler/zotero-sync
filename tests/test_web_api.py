"""Covers #29: web_api.py's read functions (mirroring local_api.py) and
its update_item() write function, against the stub server's web-prefixed
routes (added for #27/#29)."""

from __future__ import annotations

import pytest

from tests.fixtures.stub_server import ZoteroStubServer
from zotero_sync import web_api
from zotero_sync.errors import ZoteroSyncError

ITEM_KEY = "AAAA1111"


@pytest.fixture
def zotero_stub(monkeypatch):
    server = ZoteroStubServer()
    server.start()
    monkeypatch.setattr(web_api, "BASE_URL", server.web_api_base_url)
    monkeypatch.setattr(web_api, "API_KEY", "test-key")
    yield server
    server.stop()


def test_list_paper_items_excludes_non_paper_types(zotero_stub):
    items = web_api.list_paper_items()

    assert all(item["data"]["itemType"] not in web_api.NON_PAPER_ITEM_TYPES for item in items)
    assert any(item["key"] == ITEM_KEY for item in items)


def test_list_paper_items_filters_by_collection(zotero_stub):
    items = web_api.list_paper_items(collection_key="RES00001")

    assert all("RES00001" in item["data"].get("collections", []) for item in items)


def test_list_collections(zotero_stub):
    collections = web_api.list_collections()

    assert any(c["data"]["name"] == "Research" for c in collections)


def test_find_collection_key(zotero_stub):
    key = web_api.find_collection_key("Research")

    assert key is not None
    assert web_api.find_collection_key("No Such Collection") is None


def test_update_item_replaces_collections_and_tags(zotero_stub):
    new_version = web_api.update_item(
        ITEM_KEY, collections=["NEWCOLL1"], tags=[{"tag": "web-api-test"}], since_version=101
    )

    assert new_version == 102


def test_update_item_stale_version_raises(zotero_stub):
    with pytest.raises(ZoteroSyncError, match="412"):
        web_api.update_item(ITEM_KEY, tags=[{"tag": "stale"}], since_version=1)


def test_create_collection_returns_new_key(zotero_stub):
    key = web_api.create_collection("Astrophysics")

    assert key
    assert any(c["data"]["name"] == "Astrophysics" for c in web_api.list_collections())


def test_configure_sets_base_url_and_key():
    web_api.configure("1234567", "group", "my-key", root="https://example.org")

    assert web_api.BASE_URL == "https://example.org/groups/1234567"
    assert web_api.API_KEY == "my-key"

    web_api.configure("0", "user", "another-key", root="https://example.org")

    assert web_api.BASE_URL == "https://example.org/users/0"
