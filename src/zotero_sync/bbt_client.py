from __future__ import annotations

import itertools
import json
import urllib.error
import urllib.request

from zotero_sync.errors import PreconditionError, ZoteroSyncError

RPC_URL = "http://127.0.0.1:23119/better-bibtex/json-rpc"
_id_counter = itertools.count(1)


def _call(method: str, params: list) -> object:
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params, "id": next(_id_counter)}
    ).encode("utf-8")
    req = urllib.request.Request(
        RPC_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        raise ZoteroSyncError(
            f"Better BibTeX's JSON-RPC endpoint returned HTTP {exc.code} for {method}:\n{raw_body}"
        ) from exc
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        raise PreconditionError(
            "Can't reach Zotero's Better BibTeX endpoint at "
            f"{RPC_URL} — make sure Zotero is running with the Better BibTeX "
            "plugin enabled."
        ) from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raw_body = raw.decode("utf-8", errors="replace")
        raise ZoteroSyncError(
            "Better BibTeX's JSON-RPC endpoint returned a response that isn't "
            f"valid JSON for {method}:\n{raw_body}"
        ) from exc

    if "error" in body:
        raise ZoteroSyncError(f"Better BibTeX JSON-RPC error calling {method}: {body['error']}")
    return body["result"]


def check_ready() -> None:
    """Precondition check: raises PreconditionError if BBT isn't reachable."""
    _call("api.ready", [])


def citationkeys(item_ids: list[str]) -> dict[str, str]:
    """item_ids are '<libraryID>:<itemKey>' strings. Returns {item_id: citekey}.
    This is the only fact BBT is authoritative for that the Zotero Local API
    doesn't expose (see research/01-zotero-access-method-findings.md) — all
    other bibliographic fields come from the Local API item JSON, since we
    already fetch that for date-added/date-modified/tags."""
    return _call("item.citationkey", [item_ids])
