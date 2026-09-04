from __future__ import annotations

INDEX_FOLDERS = {
    "collection": "Collections",
    "author": "Authors",
    "keyword": "Keywords",
}


def render_index_note(*, kind: str, title: str, parent: str | None = None) -> str:
    """Index notes are fully regenerated every sync (issues/03-index-note-format.md):
    frontmatter only (type, title, parent for collections), no freeform region,
    no explicit body list of linked papers — membership is read via Obsidian's
    backlinks panel from the papers that link to this note."""
    lines = ["---", f"type: {kind}", f'title: "{title}"']
    if kind == "collection":
        lines.append(f'parent: "{parent}"' if parent else "parent:")
    lines.append("---")
    lines.append(f"# {title}")
    return "\n".join(lines) + "\n"
