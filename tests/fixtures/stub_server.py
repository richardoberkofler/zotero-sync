"""A tiny local HTTP stub that serves the JSON fixtures in this directory,
standing in for both Zotero's Local API (http://127.0.0.1:23119/api/...)
and Better BibTeX's JSON-RPC endpoint (http://127.0.0.1:23119/better-bibtex/
json-rpc) during tests. Stdlib only (http.server) — no new test dependency.

Why one stub server for both: in a real Zotero install both live on the
same host:port (127.0.0.1:23119), Local API under /api and BBT under
/better-bibtex/json-rpc, so one process routing on path is the simplest
match for how src/zotero_sync/local_api.py and src/zotero_sync/bbt_client.py
actually address them.

Usage from a future test (tickets #5/#6)
-----------------------------------------
local_api.py and bbt_client.py hardcode their target host/port as module
constants (`local_api.BASE_URL`, `bbt_client.RPC_URL`) rather than reading
them from Config, so there's nothing to configure — a consuming test
monkeypatches those constants to point at this stub's bound port:

    import pytest
    from zotero_sync import local_api, bbt_client
    from tests.fixtures.stub_server import ZoteroStubServer

    @pytest.fixture
    def zotero_stub(monkeypatch):
        server = ZoteroStubServer()
        server.start()
        monkeypatch.setattr(local_api, "BASE_URL", server.local_api_base_url)
        monkeypatch.setattr(bbt_client, "RPC_URL", server.bbt_rpc_url)
        yield server
        server.stop()

Then point `annotations.default_zotero_sqlite_path()` (or wherever the test
constructs its Config/db path) at a fresh copy of tests/fixtures/zotero.sqlite,
e.g. via `shutil.copy2(FIXTURES_DIR / "zotero.sqlite", tmp_path / "zotero.sqlite")`
so tests never mutate the checked-in fixture, mirroring what
annotations.copy_database() does against a real install.

Every item id/key used across zotero.sqlite, local_api/items.json, and
bbt/citationkeys.json refers to the same fake library — see
build_zotero_sqlite.py's module docstring for the itemID/key/citekey table.

The stub deliberately does no pagination/filtering logic beyond what's
needed to exercise local_api.py's actual code paths:
  - GET  /api/users/0/items                       -> all items in items.json
  - GET  /api/users/0/collections/<key>/items      -> items.json entries whose
                                                       data.collections contains <key>
  - GET  /api/users/0/collections                  -> collections.json
  - POST /better-bibtex/json-rpc {method: "api.ready"}         -> {"result": true}
  - POST /better-bibtex/json-rpc {method: "item.citationkey"}  -> citationkeys.json's "result" map
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent

with open(FIXTURES_DIR / "local_api" / "items.json", encoding="utf-8") as f:
    _ITEMS = json.load(f)
with open(FIXTURES_DIR / "local_api" / "collections.json", encoding="utf-8") as f:
    _COLLECTIONS = json.load(f)
with open(FIXTURES_DIR / "bbt" / "citationkeys.json", encoding="utf-8") as f:
    _CITATIONKEYS_RESULT = json.load(f)["result"]

_COLLECTION_ITEMS_RE = re.compile(r"^/api/users/0/collections/([^/]+)/items$")


class _Handler(BaseHTTPRequestHandler):
    # Silence default request logging to keep test output clean.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/api/users/0/items":
            self._send_json(_ITEMS)
            return

        match = _COLLECTION_ITEMS_RE.match(path)
        if match:
            collection_key = match.group(1)
            filtered = [
                item for item in _ITEMS if collection_key in item["data"].get("collections", [])
            ]
            self._send_json(filtered)
            return

        if path == "/api/users/0/collections":
            self._send_json(_COLLECTIONS)
            return

        self._send_json({"error": f"stub: no route for GET {path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/better-bibtex/json-rpc":
            self._send_json({"error": f"stub: no route for POST {self.path}"}, status=404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        request = json.loads(raw or b"{}")
        method = request.get("method")
        request_id = request.get("id")

        if method == "api.ready":
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": True})
            return

        if method == "item.citationkey":
            item_ids = request["params"][0] if request.get("params") else []
            result = {
                item_id: _CITATIONKEYS_RESULT[item_id]
                for item_id in item_ids
                if item_id in _CITATIONKEYS_RESULT
            }
            self._send_json({"jsonrpc": "2.0", "id": request_id, "result": result})
            return

        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"message": f"stub: unknown method {method!r}"},
            },
            status=200,
        )


class ZoteroStubServer:
    """Serves the Local API + BBT fixtures on an OS-assigned localhost port.

    Not bound to Zotero's real port (23119) by default, since a real Zotero
    might be running on the test machine — tests redirect local_api.py/
    bbt_client.py to this server's actual port via monkeypatching their
    BASE_URL/RPC_URL constants (see module docstring above).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._httpd = HTTPServer((host, port), _Handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def local_api_base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/users/0"

    @property
    def bbt_rpc_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/better-bibtex/json-rpc"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self) -> "ZoteroStubServer":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
