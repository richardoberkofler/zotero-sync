from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from zotero_sync.errors import PreconditionError, ZoteroSyncError

# Unlike local_api.py's BASE_URL (fixed — Zotero's local API always lives
# at 127.0.0.1:23119), the web API's base depends on which library this
# run is configured for, so it's set once via configure() rather than
# hardcoded. Module-level state, mirroring local_api.py's pattern, so
# sync.py can pick between the two modules by name (see sync.py's `api =
# web_api if config.mode == "web" else local_api`) and tests can
# monkeypatch BASE_URL/API_KEY directly instead of going through
# configure().
BASE_URL: str | None = None
API_KEY: str | None = None

PAGE_SIZE = 100
NON_PAPER_ITEM_TYPES = {"attachment", "note", "annotation"}


def configure(
    library_id: str, library_type: str, api_key: str, root: str = "https://api.zotero.org"
) -> None:
    """Point this module at a specific library for the rest of the process.
    See docs/research/2023-zotero-web-api-2way-sync.md for the "users"/
    "groups" prefix convention this mirrors."""
    global BASE_URL, API_KEY
    prefix = "groups" if library_type == "group" else "users"
    BASE_URL = f"{root}/{prefix}/{library_id}"
    API_KEY = api_key


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json", "Zotero-API-Version": "3"}
    if API_KEY:
        headers["Zotero-API-Key"] = API_KEY
    if extra:
        headers.update(extra)
    return headers


def _request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    data: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    if BASE_URL is None:
        raise PreconditionError(
            "web_api.configure() hasn't been called — this is an internal "
            "error in zotero-sync, not something you can fix in config."
        )
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers=_headers(extra_headers))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ZoteroSyncError(
            f"Zotero's web API returned HTTP {exc.code} for {method} {url}:\n{body}"
        ) from exc
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        raise PreconditionError(
            f"Can't reach Zotero's web API at {BASE_URL} — check your network "
            "connection and the ZOTERO_API_KEY/ZOTERO_LIBRARY_ID/ZOTERO_LIBRARY_TYPE "
            "settings in .env."
        ) from exc


def _get(path: str, params: dict | None = None) -> object:
    raw, _headers_out = _request("GET", path, params=params)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        body = raw.decode("utf-8", errors="replace")
        raise ZoteroSyncError(
            f"Zotero's web API returned a response that isn't valid JSON for {path}:\n{body}"
        ) from exc


def _paginated(path: str, params: dict | None = None) -> list[dict]:
    items: list[dict] = []
    start = 0
    params = dict(params or {})
    while True:
        params.update(start=start, limit=PAGE_SIZE)
        batch = _get(path, params)
        if not batch:
            break
        items.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return items


def list_paper_items(collection_key: str | None = None) -> list[dict]:
    """Top-level bibliographic items only (no attachments/notes/annotations)."""
    path = f"/collections/{collection_key}/items" if collection_key else "/items"
    items = _paginated(path)
    return [i for i in items if i["data"].get("itemType") not in NON_PAPER_ITEM_TYPES]


def list_collections() -> list[dict]:
    """All collections in the library, flat (each has data.key/name/parentCollection)."""
    return _paginated("/collections")


def find_collection_key(name: str) -> str | None:
    for c in list_collections():
        if c["data"]["name"] == name:
            return c["data"]["key"]
    return None


def update_item(
    key: str,
    *,
    collections: list[str] | None = None,
    tags: list[dict] | None = None,
    since_version: int,
) -> int:
    """PATCHes only the given fields — collections/tags are each a full-
    array replace, not an add/remove diff, per the real API's documented
    behavior (verified in docs/research/2023-zotero-web-api-2way-sync.md).
    Sends If-Unmodified-Since-Version so a concurrent Zotero-side change
    is caught as a 412 (surfaced as ZoteroSyncError by _request) instead
    of silently overwritten. Returns the item's new version, read from the
    Last-Modified-Version response header."""
    payload: dict[str, object] = {}
    if collections is not None:
        payload["collections"] = collections
    if tags is not None:
        payload["tags"] = tags

    _raw, headers = _request(
        "PATCH",
        f"/items/{key}",
        data=json.dumps(payload).encode("utf-8"),
        extra_headers={
            "Content-Type": "application/json",
            "If-Unmodified-Since-Version": str(since_version),
        },
    )
    return int(headers["Last-Modified-Version"])
