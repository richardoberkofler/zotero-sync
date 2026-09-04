from __future__ import annotations

from zotero_sync import annotations, bbt_client, local_api
from zotero_sync.config import Config
from zotero_sync.errors import ZoteroSyncError
from zotero_sync.model import Annotation, Paper
from zotero_sync.vault import (
    SyncCounts,
    existing_paper_citekeys,
    retire_note,
    write_index_note,
    write_paper_note,
)

AUTOMATIC_TAG_TYPE = 1
# Better BibTeX's JSON-RPC addresses libraries by its own internal library
# ID, not the Zotero Web/Local API's numeric user ID that items[].library.id
# returns — 1 is BBT's ID for "My Library" (the default local library; per
# the map's Out of scope, multi-library support is future work).
BBT_LIBRARY_ID = 1


def _creator_name(creator: dict) -> str:
    # Zotero represents creators two ways: a single "name" field for
    # organizations/institutions, or split firstName/lastName for people.
    if "name" in creator:
        return creator["name"]
    return " ".join(part for part in (creator.get("firstName"), creator.get("lastName")) if part)


def _collection_maps() -> tuple[dict[str, str], dict[str, str | None]]:
    """Returns (key -> name, key -> parent_key)."""
    names: dict[str, str] = {}
    parents: dict[str, str | None] = {}
    for c in local_api.list_collections():
        data = c["data"]
        names[data["key"]] = data["name"]
        parents[data["key"]] = data.get("parentCollection") or None
    return names, parents


def build_papers(
    config: Config, db_copy_path, counts: SyncCounts | None = None
) -> tuple[list[Paper], dict[str, dict]]:
    collection_key = None
    if config.collection:
        collection_key = local_api.find_collection_key(config.collection)
        if collection_key is None:
            raise ZoteroSyncError(f'No Zotero collection named "{config.collection}" was found.')

    items = local_api.list_paper_items(collection_key)
    if not items:
        return [], {}

    item_ids = [f"{BBT_LIBRARY_ID}:{item['data']['key']}" for item in items]
    citekey_map = bbt_client.citationkeys(item_ids)

    collection_names, collection_parents = _collection_maps()

    keys = [item["data"]["key"] for item in items]
    item_id_by_key = annotations.item_ids_by_key(db_copy_path, keys)

    papers: list[Paper] = []
    for item, item_id in zip(items, item_ids):
        data = item["data"]
        citekey = citekey_map.get(item_id)
        if not citekey:
            if counts is not None:
                title = data.get("title") or "(untitled)"
                counts.errors.append(
                    f"{title}: skipped — no Better BibTeX citekey found for this item"
                )
            continue

        authors = [_creator_name(c) for c in data.get("creators", [])]
        tags = [
            t["tag"]
            for t in data.get("tags", [])
            if config.include_auto_tags or t.get("type", 0) != AUTOMATIC_TAG_TYPE
        ]
        collection_keys = data.get("collections", [])
        collections = [collection_names[k] for k in collection_keys if k in collection_names]

        papers.append(
            Paper(
                citekey=citekey,
                item_id=item_id_by_key.get(data["key"], 0),
                title=data.get("title", ""),
                authors=authors,
                year=(data.get("date") or "")[:4] or None,
                item_type=data.get("itemType", ""),
                doi=data.get("DOI"),
                url=data.get("url"),
                abstract=data.get("abstractNote"),
                date_added=data.get("dateAdded"),
                date_modified=data.get("dateModified"),
                collections=collections,
                tags=tags,
            )
        )

    return papers, {"names": collection_names, "parents": collection_parents}


# zotero.sqlite's itemAnnotations.type is an integer code, not a string;
# 1 = highlight (confirmed by inspecting a live database, since it isn't
# documented anywhere — see research/01-zotero-access-method-findings.md §2
# on this table's schema being unstable/undocumented across releases).
ANNOTATION_TYPE_HIGHLIGHT = 1


def attach_annotations(papers: list[Paper], db_copy_path) -> None:
    id_map = {p.citekey: p.item_id for p in papers if p.item_id}
    raw = annotations.read_annotations(db_copy_path, id_map)
    for paper in papers:
        rows = raw.get(paper.citekey, [])
        paper.annotations = [
            Annotation(
                text=row["text"] or "",
                comment=row["comment"],
                color=row["color"] or "#ffd400",
                page_label=row["pageLabel"] or "?",
                sort_index=row["sortIndex"] or "",
            )
            for row in rows
            if row["type"] == ANNOTATION_TYPE_HIGHLIGHT
        ]


def run(config: Config) -> SyncCounts:
    bbt_client.check_ready()

    counts = SyncCounts()

    source_db = annotations.default_zotero_sqlite_path()
    if source_db is None:
        raise ZoteroSyncError(
            "Couldn't find zotero.sqlite in its default location — has "
            "Zotero been run at least once on this machine?"
        )
    db_copy = annotations.copy_database(source_db)

    try:
        papers, collection_info = build_papers(config, db_copy, counts)
        attach_annotations(papers, db_copy)
    finally:
        db_copy.unlink(missing_ok=True)

    fields = config.frontmatter_fields
    seen_citekeys: set[str] = set()
    seen_collections: set[str] = set()
    # Citekeys that failed to sync this run (OSError or case-insensitive
    # collision) but are still present in the Zotero library — must be kept
    # out of the retire pass below, or a transient failure would wrongly
    # trash the paper's pre-existing note even though it's still in the
    # library.
    failed_citekeys: set[str] = set()
    # Paper notes live in a flat Papers/ folder keyed by citekey (filenames.py
    # sanitize()); on case-insensitive filesystems (Windows, default macOS),
    # two distinct citekeys differing only by case collide onto one file and
    # silently discard one paper. Detect and report rather than overwrite.
    seen_citekeys_lower: dict[str, str] = {}

    for paper in papers:
        lower = paper.citekey.lower()
        if lower in seen_citekeys_lower and seen_citekeys_lower[lower] != paper.citekey:
            counts.errors.append(
                f"{paper.citekey}: skipped — collides with citekey "
                f"{seen_citekeys_lower[lower]!r} on a case-insensitive filesystem"
            )
            failed_citekeys.add(paper.citekey)
            continue
        seen_citekeys_lower[lower] = paper.citekey
        try:
            write_paper_note(config.vault_path, paper, fields, config.dry_run, counts)
        except OSError as exc:
            counts.errors.append(f"{paper.citekey}: {exc}")
            failed_citekeys.add(paper.citekey)
            continue
        seen_citekeys.add(paper.citekey)
        seen_collections.update(paper.collections)

    names_to_key = {v: k for k, v in collection_info.get("names", {}).items()}
    for name in seen_collections:
        key = names_to_key.get(name)
        parent_key = collection_info.get("parents", {}).get(key) if key else None
        parent_name = collection_info["names"].get(parent_key) if parent_key else None
        write_index_note(config.vault_path, "collection", name, parent_name, config.dry_run, counts)

    if not config.collection:
        retire_candidates = (
            existing_paper_citekeys(config.vault_path) - seen_citekeys - failed_citekeys
        )
        for citekey in retire_candidates:
            retire_note(config.vault_path, citekey, config.dry_run, counts)

    return counts
