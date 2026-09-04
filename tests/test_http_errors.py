"""Covers #10: HTTP error responses and non-JSON bodies from Zotero's Local
API / Better BibTeX endpoint must surface as a diagnosable ZoteroSyncError
(with the status code/body), not get swallowed into the generic
"Zotero unreachable" PreconditionError message, and must not raise an
unhandled json.JSONDecodeError."""

from __future__ import annotations

import pytest

from tests.fixtures.stub_server import ZoteroStubServer
from zotero_sync import bbt_client, local_api
from zotero_sync.errors import PreconditionError, ZoteroSyncError


@pytest.fixture
def zotero_stub(monkeypatch):
    server = ZoteroStubServer()
    server.start()
    monkeypatch.setattr(local_api, "BASE_URL", server.local_api_base_url)
    monkeypatch.setattr(bbt_client, "RPC_URL", server.bbt_rpc_url)
    yield server
    server.stop()


def test_local_api_http_error_reports_status_and_body(zotero_stub):
    zotero_stub.set_fault(404, b"Not Found: no such collection", content_type="text/plain")

    with pytest.raises(ZoteroSyncError) as exc_info:
        local_api.list_collections()

    assert not isinstance(exc_info.value, PreconditionError)
    assert "404" in str(exc_info.value)
    assert "Not Found: no such collection" in str(exc_info.value)


def test_local_api_non_json_body_reports_diagnosable_error(zotero_stub):
    zotero_stub.set_fault(200, b"<html>not json</html>", content_type="text/html")

    with pytest.raises(ZoteroSyncError) as exc_info:
        local_api.list_collections()

    assert not isinstance(exc_info.value, PreconditionError)
    assert "<html>not json</html>" in str(exc_info.value)


def test_bbt_client_http_error_reports_status_and_body(zotero_stub):
    zotero_stub.set_fault(500, b"internal server error", content_type="text/plain")

    with pytest.raises(ZoteroSyncError) as exc_info:
        bbt_client.check_ready()

    assert not isinstance(exc_info.value, PreconditionError)
    assert "500" in str(exc_info.value)
    assert "internal server error" in str(exc_info.value)


def test_bbt_client_non_json_body_reports_diagnosable_error(zotero_stub):
    zotero_stub.set_fault(200, b"<html>not json</html>", content_type="text/html")

    with pytest.raises(ZoteroSyncError) as exc_info:
        bbt_client.check_ready()

    assert not isinstance(exc_info.value, PreconditionError)
    assert "<html>not json</html>" in str(exc_info.value)


def test_local_api_connection_failure_still_raises_precondition_error(monkeypatch):
    # Point at a port nothing is listening on — a true connectivity failure
    # (as opposed to a real HTTP error response) should still get the
    # friendly "make sure Zotero is running" message.
    monkeypatch.setattr(local_api, "BASE_URL", "http://127.0.0.1:1/api/users/0")

    with pytest.raises(PreconditionError):
        local_api.list_collections()
