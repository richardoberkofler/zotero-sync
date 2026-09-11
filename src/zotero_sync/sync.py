from __future__ import annotations

from types import ModuleType

from zotero_sync import annotations, bbt_client, local_api, sync_state, web_api
from zotero_sync.config import Config
from zotero_sync.errors import ZoteroSyncError
from zotero_sync.merge import find_close_match, three_way_merge
from zotero_sync.model import Annotation, Paper
from zotero_sync.notes import paper as paper_notes
from zotero_sync.notes.paper import _slugify_tag
from zotero_sync.vault import (
    SyncCounts,
    existing_paper_citekeys,
    paper_note_path,
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


def _api_module(config: Config) -> ModuleType:
    """local_api and web_api expose matching read/write function names by
    design (#28's decision), so picking between them is a plain module
    swap — no client abstraction needed."""
    return web_api if config.mode == "web" else local_api


def _collection_maps(api: ModuleType) -> tuple[dict[str, str], dict[str, str | None]]:
    """Returns (key -> name, key -> parent_key)."""
    names: dict[str, str] = {}
    parents: dict[str, str | None] = {}
    for c in api.list_collections():
        data = c["data"]
        names[data["key"]] = data["name"]
        parents[data["key"]] = data.get("parentCollection") or None
    return names, parents


def _collection_names_with_ancestors(
    collection_keys: list[str],
    names: dict[str, str],
    parents: dict[str, str | None],
) -> list[str]:
    """A paper's direct collections plus every ancestor up each chain, so
    a paper filed only in a subcollection still references the overarching
    collections above it (issue #20)."""
    result: list[str] = []
    seen: set[str] = set()
    for key in collection_keys:
        while key is not None and key in names and key not in seen:
            seen.add(key)
            result.append(names[key])
            key = parents.get(key)
    return result


def build_papers(
    config: Config, db_copy_path, counts: SyncCounts | None = None
) -> tuple[list[Paper], dict[str, dict]]:
    api = _api_module(config)

    collection_key = None
    if config.collection:
        collection_key = api.find_collection_key(config.collection)
        if collection_key is None:
            raise ZoteroSyncError(f'No Zotero collection named "{config.collection}" was found.')

    items = api.list_paper_items(collection_key)
    if not items:
        return [], {}

    item_ids = [f"{BBT_LIBRARY_ID}:{item['data']['key']}" for item in items]
    citekey_map = bbt_client.citationkeys(item_ids)

    collection_names, collection_parents = _collection_maps(api)
    # Recorded for web mode only (sync_state.py) — the item's current
    # version, so a future write can send a correct
    # If-Unmodified-Since-Version. Not meaningful for local mode, which
    # stays read-only and whose fixtures don't always carry a "version".
    item_versions = {item["data"]["key"]: item["version"] for item in items if "version" in item}

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
        # Direct/leaf membership (#25/#31's representation fix) — kept
        # separate from the ancestor-expanded display list below, since
        # that's what the editable frontmatter field and the 3-way merge
        # need: an ancestor name in the expanded list isn't something the
        # paper is actually filed in.
        collection_keys = data.get("collections", [])
        direct_collections = [collection_names[k] for k in collection_keys if k in collection_names]
        collections = _collection_names_with_ancestors(
            collection_keys, collection_names, collection_parents
        )

        papers.append(
            Paper(
                citekey=citekey,
                item_id=item_id_by_key.get(data["key"], 0),
                zotero_key=data["key"],
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
                direct_collections=direct_collections,
                tags=tags,
            )
        )

    # New snapshot for sync_state.py (#24's design), covering only papers
    # that actually got a note written this run — an item dropped for
    # missing a citekey has no note to compare against next time.
    new_state = {
        p.zotero_key: {
            "version": item_versions.get(p.zotero_key),
            "collections": p.direct_collections,
            "tags": [_slugify_tag(t) for t in p.tags],
        }
        for p in papers
    }

    return papers, {
        "names": collection_names,
        "parents": collection_parents,
        "new_state": new_state,
    }


# zotero.sqlite's itemAnnotations.type is an integer code, not a string.
# Confirmed against Zotero's own client source (chrome/content/zotero/xpcom/
# annotations.js's ANNOTATION_TYPE_* constants, since this table isn't
# documented anywhere else — see research/01-zotero-access-method-findings.md
# §2 on this table's schema being unstable/undocumented across releases):
#   1 = highlight, 2 = note, 3 = image, 4 = ink, 5 = underline, 6 = text.
# We extract highlight/note/image/underline (issue #18); ink and text
# annotations aren't handled yet — out of scope for #18, left as a gap.
ANNOTATION_TYPE_HIGHLIGHT = 1
ANNOTATION_TYPE_NOTE = 2
ANNOTATION_TYPE_IMAGE = 3
ANNOTATION_TYPE_UNDERLINE = 5

# Maps the zotero.sqlite integer type code to the Annotation.kind string
# notes/paper.py's render_annotations() branches on.
ANNOTATION_TYPE_KINDS = {
    ANNOTATION_TYPE_HIGHLIGHT: "highlight",
    ANNOTATION_TYPE_NOTE: "note",
    ANNOTATION_TYPE_IMAGE: "image",
    ANNOTATION_TYPE_UNDERLINE: "underline",
}


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
                kind=ANNOTATION_TYPE_KINDS[row["type"]],
            )
            for row in rows
            if row["type"] in ANNOTATION_TYPE_KINDS
        ]


def _resolve_merged_collections(
    merged_names: set[str],
    names_to_key: dict[str, str],
    collection_names: dict[str, str],
    api: ModuleType,
    dry_run: bool,
    citekey: str,
    counts: SyncCounts,
) -> tuple[list[str], list[str] | None]:
    """Maps a merged set of collection names to Zotero collection keys —
    #25's typo-check/auto-create flow. A name close to an existing one is
    treated as a likely typo: warn and skip this paper's whole collections
    write this run (returns keys=None) rather than guess. A name with no
    close match is genuinely new: auto-created at the library's top level.
    Returns (final_names, final_keys); keys is None when the write should
    be skipped."""
    final_names: list[str] = []
    final_keys: list[str] = []
    for name in sorted(merged_names):
        key = names_to_key.get(name)
        if key is None:
            match = find_close_match(name, list(names_to_key.keys()))
            if match is not None:
                counts.errors.append(
                    f'{citekey}: collection "{name}" not found in Zotero — did you '
                    f'mean "{match}"? Skipping the collections sync for this paper '
                    "this run."
                )
                return [], None
            if dry_run:
                # Can't allocate a real key without writing. The write is
                # skipped for dry runs regardless, so just keep the name for
                # a truthful frontmatter preview.
                final_names.append(name)
                continue
            key = api.create_collection(name)
            names_to_key[name] = key
            collection_names[key] = name
        final_names.append(name)
        final_keys.append(key)
    return final_names, final_keys


def _resolve_merged_tags(
    merged_slugs: set[str],
    zotero_slugs: set[str],
    library_slugs: set[str],
    raw_by_slug: dict[str, str],
    citekey: str,
    counts: SyncCounts,
) -> tuple[list[str], list[str]]:
    """Per-tag typo-check (#25) — unlike collections, a near-miss here only
    drops *that* tag, not the whole field: tags have no identity to
    auto-create against, Zotero just stores whatever string is sent, so a
    genuinely new tag needs no special handling beyond using it as-is.
    Returns (final_slugs, final_raw_tag_strings)."""
    final_slugs: list[str] = []
    for slug in sorted(merged_slugs):
        if slug in zotero_slugs or slug in library_slugs:
            final_slugs.append(slug)
            continue
        match = find_close_match(slug, list(library_slugs))
        if match is not None:
            counts.errors.append(
                f'{citekey}: tag "{slug}" not found in the library — did you mean '
                f'"{match}"? Skipping this tag this run.'
            )
            continue
        final_slugs.append(slug)
    final_raw = [raw_by_slug.get(s, s) for s in final_slugs]
    return final_slugs, final_raw


def _reconcile_paper(
    paper: Paper,
    existing_text: str | None,
    snapshot: dict | None,
    names_to_key: dict[str, str],
    collection_names: dict[str, str],
    collection_parents: dict[str, str | None],
    library_tag_slugs: set[str],
    api: ModuleType,
    dry_run: bool,
    counts: SyncCounts,
) -> dict | None:
    """Runs #25's 3-way merge for one paper's collections/tags against the
    prior snapshot, mutating `paper` to hold the merged result — what
    render_frontmatter()/render_links() will write. Returns what changed
    relative to Zotero's current data, for the write-back step in run()
    below, or None when there's no snapshot to merge against (bootstrap:
    paper already reflects Zotero as fetched, nothing to reconcile)."""
    if snapshot is None:
        return None

    vault_collections, vault_tags = paper_notes.parse_vault_lists(existing_text)
    zot_collections = set(paper.direct_collections)
    zot_tags_slugs = {_slugify_tag(t) for t in paper.tags}
    tag_raw_by_slug = {_slugify_tag(t): t for t in paper.tags}

    snap_collections = set(snapshot.get("collections", []))
    snap_tags = set(snapshot.get("tags", []))

    merged_collections = three_way_merge(
        snap_collections,
        set(vault_collections) if vault_collections is not None else zot_collections,
        zot_collections,
    )
    merged_tags_slugs = three_way_merge(
        snap_tags,
        set(vault_tags) if vault_tags is not None else zot_tags_slugs,
        zot_tags_slugs,
    )

    final_names, final_keys = _resolve_merged_collections(
        merged_collections, names_to_key, collection_names, api, dry_run, paper.citekey, counts
    )
    if final_keys is None:
        # A typo warning fired for this paper — leave collections untouched
        # this run rather than guess.
        final_names = list(paper.direct_collections)
        final_keys = [names_to_key[n] for n in final_names if n in names_to_key]

    final_tag_slugs, final_tags_raw = _resolve_merged_tags(
        merged_tags_slugs, zot_tags_slugs, library_tag_slugs, tag_raw_by_slug, paper.citekey, counts
    )

    paper.direct_collections = final_names
    paper.collections = _collection_names_with_ancestors(
        final_keys, collection_names, collection_parents
    )
    paper.tags = final_tags_raw

    return {
        "final_direct_names": final_names,
        "final_direct_keys": final_keys,
        "final_tag_slugs": final_tag_slugs,
        "collections_changed": set(final_names) != zot_collections,
        "tags_changed": set(final_tag_slugs) != zot_tags_slugs,
    }


def run(config: Config) -> SyncCounts:
    bbt_client.check_ready()

    if config.mode == "web":
        web_api.configure(
            config.web_library_id,
            config.web_library_type,
            config.web_api_key,
            root=config.web_api_root,
        )

    counts = SyncCounts()

    source_db = annotations.zotero_sqlite_path(config.zotero_dir)
    if source_db is None:
        if config.zotero_dir is not None:
            raise ZoteroSyncError(
                f"Couldn't find zotero.sqlite in the configured zotero_dir "
                f"({config.zotero_dir}) — check the path in .zotero-sync.toml."
            )
        raise ZoteroSyncError(
            "Couldn't find zotero.sqlite in its default location — has "
            "Zotero been run at least once on this machine?"
        )
    db_copy = annotations.copy_database(source_db)

    # Loaded before build_papers/the loop below overwrite anything, since
    # both detect_changes() and the 3-way merge need the *prior* snapshot to
    # compare against — see notes/paper.py's detect_changes() and #24/#25.
    prior_state = sync_state.load_state(config.vault_path) if config.mode == "web" else {}

    try:
        papers, collection_info = build_papers(config, db_copy, counts)
        attach_annotations(papers, db_copy)
    finally:
        db_copy.unlink(missing_ok=True)

    fields = config.frontmatter_fields
    collection_names = collection_info.get("names", {})
    collection_parents = collection_info.get("parents", {})
    names_to_key = {v: k for k, v in collection_names.items()}
    # The library-wide tag vocabulary for #25's per-tag typo-check, captured
    # from Zotero's current data before any paper's tags get mutated by the
    # merge below — a paper's own tags are checked against every *other*
    # tag currently in the library, not just what it already has itself.
    library_tag_slugs = {_slugify_tag(t) for p in papers for t in p.tags}
    web_state_updates: dict[str, dict] = {}
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

        snapshot = prior_state.get(paper.zotero_key) if config.mode == "web" else None
        path = paper_note_path(config.vault_path, paper.citekey)
        existing_text = path.read_text(encoding="utf-8") if path.exists() else None

        if config.mode == "web":
            changes = paper_notes.detect_changes(existing_text, paper, snapshot)
            if changes["vault_collections"] or changes["vault_tags"]:
                counts.vault_side_changes.append(paper.citekey)
            if changes["zotero_collections"] or changes["zotero_tags"]:
                counts.zotero_side_changes.append(paper.citekey)

        reconciliation = None
        if config.mode == "web":
            reconciliation = _reconcile_paper(
                paper,
                existing_text,
                snapshot,
                names_to_key,
                collection_names,
                collection_parents,
                library_tag_slugs,
                web_api,
                config.dry_run,
                counts,
            )

        try:
            write_paper_note(config.vault_path, paper, fields, config.dry_run, counts)
        except OSError as exc:
            counts.errors.append(f"{paper.citekey}: {exc}")
            failed_citekeys.add(paper.citekey)
            continue
        seen_citekeys.add(paper.citekey)

        if config.mode == "web":
            if reconciliation is None:
                # Bootstrap: nothing to reconcile, trust Zotero's raw fetch
                # as-is (#24's decision).
                state_entry = collection_info["new_state"].get(paper.zotero_key)
                if state_entry is not None:
                    web_state_updates[paper.zotero_key] = state_entry
            else:
                current_version = (
                    collection_info["new_state"].get(paper.zotero_key, {}).get("version")
                )
                if reconciliation["collections_changed"] or reconciliation["tags_changed"]:
                    if not config.dry_run:
                        try:
                            new_version = web_api.update_item(
                                paper.zotero_key,
                                collections=(
                                    reconciliation["final_direct_keys"]
                                    if reconciliation["collections_changed"]
                                    else None
                                ),
                                tags=(
                                    [{"tag": t} for t in paper.tags]
                                    if reconciliation["tags_changed"]
                                    else None
                                ),
                                since_version=current_version,
                            )
                        except ZoteroSyncError as exc:
                            counts.errors.append(
                                f"{paper.citekey}: failed to write collections/tags "
                                f"back to Zotero ({exc}) — will retry next run."
                            )
                        else:
                            web_state_updates[paper.zotero_key] = {
                                "version": new_version,
                                "collections": reconciliation["final_direct_names"],
                                "tags": reconciliation["final_tag_slugs"],
                            }
                    # dry_run: nothing was actually written, so the prior
                    # snapshot stands — don't record a state update.
                else:
                    web_state_updates[paper.zotero_key] = {
                        "version": current_version,
                        "collections": reconciliation["final_direct_names"],
                        "tags": reconciliation["final_tag_slugs"],
                    }

        for name in paper.collections:
            key = names_to_key.get(name)
            while key is not None and key not in seen_collections:
                seen_collections.add(key)
                key = collection_parents.get(key)

    for key in seen_collections:
        name = collection_names[key]
        parent_key = collection_parents.get(key)
        parent_name = collection_names.get(parent_key) if parent_key else None
        ancestors = (
            _collection_names_with_ancestors([parent_key], collection_names, collection_parents)
            if parent_key
            else []
        )
        write_index_note(
            config.vault_path,
            "collection",
            name,
            parent_name,
            config.dry_run,
            counts,
            ancestors=ancestors,
        )

    if not config.collection:
        retire_candidates = (
            existing_paper_citekeys(config.vault_path) - seen_citekeys - failed_citekeys
        )
        for citekey in retire_candidates:
            retire_note(config.vault_path, citekey, config.dry_run, counts)

    if config.mode == "web" and not config.dry_run:
        # Merged rather than replaced outright: a --collection-scoped run
        # only touches a subset of papers, and a write that 412'd is
        # deliberately left out of web_state_updates so its prior snapshot
        # entry survives for a retry next run.
        merged_state = {**prior_state, **web_state_updates}
        sync_state.save_state(config.vault_path, merged_state)

    return counts
