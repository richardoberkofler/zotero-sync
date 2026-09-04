from __future__ import annotations

import re

from zotero_sync.model import Annotation, Paper

LINKS_START = "<!-- zotero-sync:links:start -->"
LINKS_END = "<!-- zotero-sync:links:end -->"
ANNOTATIONS_START = "<!-- zotero-sync:annotations:start -->"
ANNOTATIONS_END = "<!-- zotero-sync:annotations:end -->"

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)
_LINKS_RE = re.compile(re.escape(LINKS_START) + r".*?" + re.escape(LINKS_END), re.DOTALL)
_ANNOTATIONS_RE = re.compile(
    re.escape(ANNOTATIONS_START) + r".*?" + re.escape(ANNOTATIONS_END), re.DOTALL
)


def _yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return f'"{escaped}"'


def _yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "\n" + "\n".join(f"  - {_yaml_scalar(v)}" for v in values)


def _slugify_tag(tag: str) -> str:
    """Obsidian's native tags: frontmatter property rejects spaces (and most
    punctuation) in tag names. Slugify for that field only — wikilinks and
    index notes use the raw tag text elsewhere, since Obsidian links and
    filenames allow spaces fine."""
    slug = re.sub(r"[^a-z0-9/_]+", "-", tag.lower())
    return slug.strip("-")


def render_frontmatter(paper: Paper, fields: list[str]) -> str:
    values: dict[str, str] = {
        "title": _yaml_scalar(paper.title),
        "authors": _yaml_list(paper.authors),
        "year": _yaml_scalar(paper.year or ""),
        "type": _yaml_scalar(paper.item_type),
        "doi": _yaml_scalar(paper.doi or ""),
        "url": _yaml_scalar(paper.url or ""),
        "citekey": _yaml_scalar(paper.citekey),
        "collections": _yaml_list(paper.collections),
        "tags": _yaml_list([_slugify_tag(t) for t in paper.tags]),
        "date-added": _yaml_scalar(paper.date_added or ""),
        "date-modified": _yaml_scalar(paper.date_modified or ""),
        "abstract": _yaml_scalar(paper.abstract or ""),
        **{k: _yaml_scalar(v) for k, v in paper.extra_fields.items()},
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
        render_frontmatter(paper, fields) + render_links(paper) + "\n" + render_annotations(paper)
    )


def update_existing_note(existing_text: str, paper: Paper, fields: list[str]) -> str:
    """Regenerates the frontmatter, links, and annotations blocks in place;
    leaves everything else (the freeform region) untouched."""
    text = existing_text
    if _FRONTMATTER_RE.search(text):
        text = _FRONTMATTER_RE.sub(render_frontmatter(paper, fields), text, count=1)
    else:
        text = render_frontmatter(paper, fields) + text

    if _LINKS_RE.search(text):
        text = _LINKS_RE.sub(render_links(paper).rstrip("\n"), text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + render_links(paper)

    if _ANNOTATIONS_RE.search(text):
        text = _ANNOTATIONS_RE.sub(render_annotations(paper).rstrip("\n"), text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n" + render_annotations(paper)

    return text
