from __future__ import annotations

from dataclasses import dataclass, field

# Per zotero/reader's defines.js, confirmed in
# research/03-obsidian-colored-highlights-findings.md.
ZOTERO_HIGHLIGHT_COLORS = {
    "#ffd400": "Yellow",
    "#ff6666": "Red",
    "#5fb236": "Green",
    "#2ea8e5": "Blue",
    "#a28ae5": "Purple",
    "#e56eee": "Magenta",
    "#f19837": "Orange",
    "#aaaaaa": "Gray",
}


@dataclass
class Annotation:
    text: str
    comment: str | None
    color: str
    page_label: str
    sort_index: str
    # One of "highlight", "underline", "note", "image" — see
    # sync.ANNOTATION_TYPE_* for the zotero.sqlite integer codes this is
    # derived from. Determines how notes/paper.py's render_annotations()
    # renders the entry (highlight/underline wrap PDF text; note/image
    # don't).
    kind: str = "highlight"


@dataclass
class Paper:
    citekey: str
    item_id: int
    title: str
    authors: list[str]
    year: str | None
    item_type: str
    doi: str | None
    url: str | None
    abstract: str | None
    date_added: str | None
    date_modified: str | None
    collections: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    extra_fields: dict[str, str] = field(default_factory=dict)
    annotations: list[Annotation] = field(default_factory=list)


@dataclass
class Collection:
    name: str
    parent: str | None = None


@dataclass
class LibrarySnapshot:
    papers: list[Paper]
    collections: list[Collection]
    authors: set[str]
    keywords: set[str]
