from __future__ import annotations

from zotero_sync.notes.yaml_util import yaml_list

INDEX_FOLDERS = {
    "collection": "Collections",
    "author": "Authors",
    "keyword": "Keywords",
}


def render_index_note(
    *, kind: str, title: str, parent: str | None = None, ancestors: list[str] | None = None
) -> str:
    """Index notes are fully regenerated every sync (issues/03-index-note-format.md):
    frontmatter only (type, title, parent/ancestors for collections), no
    freeform region, no explicit body list of linked papers — membership is
    read via Obsidian's backlinks panel from the papers that link to this
    note.

    `parent` stays the single immediate parent (issue #20's original scope:
    a note's hierarchy link never points past one level up); `ancestors` is
    the full chain above it (issue #20 follow-up), same shape as a paper's
    `collections` field, so a subcollection references every overarching
    collection above it too, not just its direct parent."""
    lines = ["---", f"type: {kind}", f'title: "{title}"']
    if kind == "collection":
        lines.append(f'parent: "{parent}"' if parent else "parent:")
        lines.append(f"ancestors: {yaml_list(ancestors or [])}")
    lines.append("---")
    lines.append(f"# {title}")
    if kind == "collection" and ancestors:
        lines.append("")
        lines.append("Ancestors: " + ", ".join(f"[[{a}]]" for a in ancestors))
    return "\n".join(lines) + "\n"
