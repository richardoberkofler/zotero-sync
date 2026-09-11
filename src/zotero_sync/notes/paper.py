from __future__ import annotations

import re

from zotero_sync.model import Annotation, Paper
from zotero_sync.notes.yaml_util import parse_yaml_list, yaml_list, yaml_scalar

LINKS_START = "<!-- zotero-sync:links:start -->"
LINKS_END = "<!-- zotero-sync:links:end -->"
ABSTRACT_START = "<!-- zotero-sync:abstract:start -->"
ABSTRACT_END = "<!-- zotero-sync:abstract:end -->"
ANNOTATIONS_START = "<!-- zotero-sync:annotations:start -->"
ANNOTATIONS_END = "<!-- zotero-sync:annotations:end -->"

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)
_LINKS_RE = re.compile(re.escape(LINKS_START) + r".*?" + re.escape(LINKS_END), re.DOTALL)
_ABSTRACT_RE = re.compile(re.escape(ABSTRACT_START) + r".*?" + re.escape(ABSTRACT_END), re.DOTALL)
_ANNOTATIONS_RE = re.compile(
    re.escape(ANNOTATIONS_START) + r".*?" + re.escape(ANNOTATIONS_END), re.DOTALL
)


def _slugify_tag(tag: str) -> str:
    """Obsidian's native tags: frontmatter property rejects spaces (and most
    punctuation) in tag names. Slugify for that field only — wikilinks and
    index notes use the raw tag text elsewhere, since Obsidian links and
    filenames allow spaces fine."""
    slug = re.sub(r"[^a-z0-9/_]+", "-", tag.lower())
    return slug.strip("-")


def render_frontmatter(paper: Paper, fields: list[str]) -> str:
    values: dict[str, str] = {
        "title": yaml_scalar(paper.title),
        "authors": yaml_list(paper.authors),
        "year": yaml_scalar(paper.year or ""),
        "type": yaml_scalar(paper.item_type),
        "doi": yaml_scalar(paper.doi or ""),
        "url": yaml_scalar(paper.url or ""),
        "citekey": yaml_scalar(paper.citekey),
        "collections": yaml_list(paper.direct_collections),
        "tags": yaml_list([_slugify_tag(t) for t in paper.tags]),
        "date-added": yaml_scalar(paper.date_added or ""),
        "date-modified": yaml_scalar(paper.date_modified or ""),
        **{k: yaml_scalar(v) for k, v in paper.extra_fields.items()},
    }
    lines = ["---"]
    for field_name in fields:
        if field_name in values:
            lines.append(f"{field_name}: {values[field_name]}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def render_links(paper: Paper) -> str:
    lines = [LINKS_START]
    if paper.collections:
        lines.append("Collections: " + ", ".join(f"[[{c}]]" for c in paper.collections))
    if paper.authors:
        lines.append("Authors: " + ", ".join(f"[[{a}]]" for a in paper.authors))
    if paper.tags:
        lines.append("Keywords: " + ", ".join(f"[[{t}]]" for t in paper.tags))
    lines.append(LINKS_END)
    return "\n".join(lines) + "\n"


def render_abstract(paper: Paper) -> str:
    lines = [ABSTRACT_START, "## Abstract"]
    lines.append(paper.abstract if paper.abstract else "*No abstract.*")
    lines.append(ABSTRACT_END)
    return "\n".join(lines) + "\n"


def _render_annotation_body(ann: Annotation) -> str:
    # highlight/underline both wrap the PDF text they mark up; note/image
    # don't have PDF text to wrap (ann.text is empty/None for them) — they
    # get a standalone label instead. See model.Annotation.kind and
    # sync.ANNOTATION_TYPE_KINDS for where `kind` comes from.
    if ann.kind == "underline":
        return (
            f'<span style="text-decoration:underline; '
            f'text-decoration-color:{ann.color};">{ann.text}</span>'
        )
    if ann.kind == "note":
        return "📝 *Note annotation*"
    if ann.kind == "image":
        return "🖼️ *Image annotation*"
    return f'<mark style="background-color:{ann.color};">{ann.text}</mark>'


def render_annotations(paper: Paper) -> str:
    lines = [ANNOTATIONS_START, "## Annotations"]
    if not paper.annotations:
        lines.append("*No annotations yet.*")
    else:
        for ann in paper.annotations:
            lines.append(f"- p. {ann.page_label}: {_render_annotation_body(ann)}")
            if ann.comment:
                lines.append(f"  - ↳ {ann.comment}")
    lines.append(ANNOTATIONS_END)
    return "\n".join(lines) + "\n"


def render_new_note(paper: Paper, fields: list[str]) -> str:
    return (
        render_frontmatter(paper, fields)
        + render_links(paper)
        + "\n"
        + render_abstract(paper)
        + "\n"
        + render_annotations(paper)
    )


def update_existing_note(existing_text: str, paper: Paper, fields: list[str]) -> str:
    """Regenerates the frontmatter, links, abstract, and annotations blocks in
    place; leaves everything else (the freeform region) untouched."""
    text = existing_text
    if _FRONTMATTER_RE.search(text):
        text = _FRONTMATTER_RE.sub(render_frontmatter(paper, fields), text, count=1)
    else:
        text = render_frontmatter(paper, fields) + text

    if _LINKS_RE.search(text):
        text = _LINKS_RE.sub(render_links(paper).rstrip("\n"), text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + render_links(paper)

    if _ABSTRACT_RE.search(text):
        text = _ABSTRACT_RE.sub(render_abstract(paper).rstrip("\n"), text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + render_abstract(paper)

    if _ANNOTATIONS_RE.search(text):
        text = _ANNOTATIONS_RE.sub(render_annotations(paper).rstrip("\n"), text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + render_annotations(paper)

    return text


def parse_vault_lists(existing_text: str | None) -> tuple[list[str] | None, list[str] | None]:
    """Reads the vault's *current* direct-collections/tags lists straight out
    of its frontmatter — before this run's write would overwrite them — for
    both detect_changes() below and sync.py's 3-way merge (#25/#31). None
    for a field means it wasn't present in the frontmatter at all (as
    opposed to present-but-empty)."""
    if existing_text is None:
        return None, None
    match = _FRONTMATTER_RE.search(existing_text)
    block = match.group(0) if match else ""
    return parse_yaml_list(block, "collections"), parse_yaml_list(block, "tags")


def detect_changes(
    existing_text: str | None, paper: Paper, snapshot: dict | None
) -> dict[str, bool]:
    """Compares both sides against the last-synced snapshot (#24's design):
    the vault's *current* frontmatter (parsed from existing_text, before
    update_existing_note() would overwrite it) against Zotero's *current*
    data (paper.direct_collections/paper.tags, already fetched this run). No
    snapshot (bootstrap: first sync, or a vault switching into web mode
    for the first time) means "trust Zotero, no vault edit" — nothing to
    diff against yet. Comparison is set-based: list order in these fields
    has never been meaningful. Tags compare in slugified form on both
    sides (matching what render_frontmatter() actually writes) since
    slugification is lossy/one-way — detection never needs to invert it."""
    if snapshot is None:
        return {
            "vault_collections": False,
            "vault_tags": False,
            "zotero_collections": False,
            "zotero_tags": False,
        }

    snap_collections = set(snapshot.get("collections", []))
    snap_tags = set(snapshot.get("tags", []))

    result = {
        "vault_collections": False,
        "vault_tags": False,
        "zotero_collections": set(paper.direct_collections) != snap_collections,
        "zotero_tags": {_slugify_tag(t) for t in paper.tags} != snap_tags,
    }

    vault_collections, vault_tags = parse_vault_lists(existing_text)
    if vault_collections is not None:
        result["vault_collections"] = set(vault_collections) != snap_collections
    if vault_tags is not None:
        result["vault_tags"] = set(vault_tags) != snap_tags

    return result
