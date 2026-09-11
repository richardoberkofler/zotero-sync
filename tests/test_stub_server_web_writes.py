"""Covers #27: the stub server's simulation of the web API's write surface
(PATCH .../items/<key>, version bump + Last-Modified-Version, and
If-Unmodified-Since-Version / 412 optimistic-concurrency), per
docs/research/2023-zotero-web-api-2way-sync.md's verified real-API
behavior. No web_api.py client exists yet (that's #28's job), so these
tests talk raw HTTP to the stub directly."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from tests.fixtures.stub_server import ZoteroStubServer

ITEM_KEY = "AAAA1111"


@pytest.fixture
def zotero_stub():
    server = ZoteroStubServer()
    server.start()
    yield server
    server.stop()


def _get_item(base_url: str, key: str) -> dict:
    with urllib.request.urlopen(f"{base_url}/items/{key}") as resp:
        return json.loads(resp.read())


def _patch(base_url: str, key: str, payload: dict, since_version: int | None = None):
    req = urllib.request.Request(
        f"{base_url}/items/{key}",
        data=json.dumps(payload).encode("utf-8"),
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    if since_version is not None:
        req.add_header("If-Unmodified-Since-Version", str(since_version))
    return urllib.request.urlopen(req)


def test_get_item_returns_current_state(zotero_stub):
    item = _get_item(zotero_stub.web_api_base_url, ITEM_KEY)
    assert item["key"] == ITEM_KEY
    assert item["version"] == 101


def test_get_unknown_item_returns_404(zotero_stub):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get_item(zotero_stub.web_api_base_url, "NOSUCHKEY")
    assert exc_info.value.code == 404


def test_patch_updates_collections_and_tags_and_bumps_version(zotero_stub):
    resp = _patch(
        zotero_stub.web_api_base_url,
        ITEM_KEY,
        {"collections": ["NEWCOLL1"], "tags": [{"tag": "test-tag"}]},
        since_version=101,
    )

    assert resp.status == 204
    assert resp.headers["Last-Modified-Version"] == "102"

    item = _get_item(zotero_stub.web_api_base_url, ITEM_KEY)
    assert item["version"] == 102
    assert item["data"]["version"] == 102
    assert item["data"]["collections"] == ["NEWCOLL1"]
    assert item["data"]["tags"] == [{"tag": "test-tag"}]


def test_patch_without_since_version_header_applies_unconditionally(zotero_stub):
    resp = _patch(zotero_stub.web_api_base_url, ITEM_KEY, {"tags": [{"tag": "unconditional"}]})

    assert resp.status == 204

    item = _get_item(zotero_stub.web_api_base_url, ITEM_KEY)
    assert item["data"]["tags"] == [{"tag": "unconditional"}]


def test_patch_with_stale_since_version_returns_412_and_does_not_apply(zotero_stub):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _patch(
            zotero_stub.web_api_base_url,
            ITEM_KEY,
            {"tags": [{"tag": "should-not-stick"}]},
            since_version=100,
        )

    assert exc_info.value.code == 412
    body = exc_info.value.read().decode("utf-8")
    assert "expected 100" in body
    assert "found 101" in body

    item = _get_item(zotero_stub.web_api_base_url, ITEM_KEY)
    assert item["version"] == 101
    assert item["data"]["tags"] != [{"tag": "should-not-stick"}]


def test_patch_then_replay_of_stale_version_still_412s(zotero_stub):
    # Mirrors the real-API race documented in the research: applying a
    # correct-at-the-time version doesn't retroactively make an earlier
    # stale version acceptable on a retry.
    first = _patch(zotero_stub.web_api_base_url, ITEM_KEY, {"tags": []}, since_version=101)
    assert first.status == 204
    assert first.headers["Last-Modified-Version"] == "102"

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _patch(zotero_stub.web_api_base_url, ITEM_KEY, {"tags": []}, since_version=101)
    assert exc_info.value.code == 412


def test_patch_is_isolated_per_server_instance(zotero_stub):
    # Guards against the shared module-level fixture leaking writes across
    # tests/instances now that items are mutated in place.
    _patch(zotero_stub.web_api_base_url, ITEM_KEY, {"tags": [{"tag": "leaky"}]}, since_version=101)

    other = ZoteroStubServer()
    other.start()
    try:
        item = _get_item(other.web_api_base_url, ITEM_KEY)
        assert item["data"]["tags"] != [{"tag": "leaky"}]
        assert item["version"] == 101
    finally:
        other.stop()
