from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from zotero_sync.errors import PreconditionError, ZoteroSyncError

# Zotero's local HTTP API always addresses the local user's library as
# user id 0, regardless of the actual zotero.org account id — there is no
# "current user" endpoint to discover a real id from.
BASE_URL = "http://127.0.0.1:23119/api/users/0"
PAGE_SIZE = 100
NON_PAPER_ITEM_TYPES = {"attachment", "note", "annotation"}


def _get(path: str, params: dict | None = None) -> object:
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ZoteroSyncError(
            f"Zotero's local API returned HTTP {exc.code} for {url}:\n{body}"
        ) from exc
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        raise PreconditionError(
            "Can't reach Zotero's local API at http://127.0.0.1:23119 — make "
            'sure Zotero is running and Settings > Advanced > "Allow other '
            'applications on this computer to communicate with Zotero" is '
            "enabled."
        ) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        body = raw.decode("utf-8", errors="replace")
        raise ZoteroSyncError(
            f"Zotero's local API returned a response that isn't valid JSON for {url}:\n{body}"
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
