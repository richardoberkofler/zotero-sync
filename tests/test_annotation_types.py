"""Covers issue #18: sync.attach_annotations must extract note/underline/
image annotations, not just highlights, and notes/paper.render_annotations
must render each kind sensibly (highlight/underline wrap PDF text; note/
image render as standalone entries with no PDF text to wrap).

tests/fixtures/zotero.sqlite (via build_zotero_sqlite.py) has one paper
(smith2020neural, itemID 1) with a highlight, a second highlight, a note
(type=2), an underline (type=5), and an image (type=3) annotation attached
to it — exactly the set this test exercises.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from zotero_sync import annotations, sync
from zotero_sync.model import Annotation, Paper
from zotero_sync.notes.paper import render_annotations

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _db_copy(tmp_path):
    dest = tmp_path / "zotero.sqlite"
    shutil.copy2(FIXTURES_DIR / "zotero.sqlite", dest)
    return dest


def _paper(citekey: str, item_id: int) -> Paper:
    return Paper(
        citekey=citekey,
        item_id=item_id,
        title="",
        authors=[],
        year=None,
        item_type="journalArticle",
        doi=None,
        url=None,
        abstract=None,
        date_added=None,
        date_modified=None,
    )


def test_attach_annotations_extracts_all_four_kinds(tmp_path):
    db = _db_copy(tmp_path)
    paper = _paper("smith2020neural", 1)

    sync.attach_annotations([paper], db)

    kinds = [a.kind for a in paper.annotations]
    assert kinds.count("highlight") == 2
    assert kinds.count("note") == 1
    assert kinds.count("underline") == 1
    assert kinds.count("image") == 1


def test_attach_annotations_note_and_image_carry_comment_not_text(tmp_path):
    db = _db_copy(tmp_path)
    paper = _paper("smith2020neural", 1)

    sync.attach_annotations([paper], db)

    note = next(a for a in paper.annotations if a.kind == "note")
    assert note.text == ""
    assert note.comment == "Follow up on this citation later."

    image = next(a for a in paper.annotations if a.kind == "image")
    assert image.text == ""
    assert image.comment == "Screenshot of the results table."

    underline = next(a for a in paper.annotations if a.kind == "underline")
    assert underline.text == "This sentence is underlined rather than highlighted."


def test_attach_annotations_ignores_unhandled_types(tmp_path):
    # zotero.sqlite's fixture only contains highlight/note/underline/image
    # rows (types 1/2/5/3) — asserting the total count here also guards
    # against a future ink/text row silently slipping through
    # ANNOTATION_TYPE_KINDS without an explicit decision to extract it.
    db = _db_copy(tmp_path)
    paper = _paper("smith2020neural", 1)

    sync.attach_annotations([paper], db)

    assert len(paper.annotations) == 5


def test_read_annotations_still_returns_raw_rows_for_all_types(tmp_path):
    # annotations.read_annotations() itself does no type filtering — that's
    # sync.attach_annotations's job — so it should surface every row,
    # including ones sync.py doesn't currently extract into an Annotation.
    db = _db_copy(tmp_path)
    item_id_by_key = annotations.item_ids_by_key(db, ["AAAA1111"])
    result = annotations.read_annotations(db, {"smith2020neural": item_id_by_key["AAAA1111"]})

    types = [row["type"] for row in result["smith2020neural"]]
    assert sorted(types) == [1, 1, 2, 3, 5]


def test_render_annotations_wraps_pdf_text_for_highlight_and_underline():
    paper = _paper("smith2020neural", 1)
    paper.annotations = [
        Annotation(
            text="highlighted text",
            comment=None,
            color="#ffd400",
            page_label="1",
            sort_index="a",
            kind="highlight",
        ),
        Annotation(
            text="underlined text",
            comment=None,
            color="#a28ae5",
            page_label="2",
            sort_index="b",
            kind="underline",
        ),
    ]

    rendered = render_annotations(paper)

    assert '<mark style="background-color:#ffd400;">highlighted text</mark>' in rendered
    assert "text-decoration:underline" in rendered
    assert "underlined text" in rendered


def test_render_annotations_note_and_image_do_not_wrap_pdf_text():
    paper = _paper("smith2020neural", 1)
    paper.annotations = [
        Annotation(
            text="",
            comment="Follow up on this citation later.",
            color="#2ea8e5",
            page_label="14",
            sort_index="c",
            kind="note",
        ),
        Annotation(
            text="",
            comment="Screenshot of the results table.",
            color="#f19837",
            page_label="16",
            sort_index="d",
            kind="image",
        ),
    ]

    rendered = render_annotations(paper)

    assert "<mark" not in rendered
    assert "Note annotation" in rendered
    assert "Image annotation" in rendered
    assert "Follow up on this citation later." in rendered
    assert "Screenshot of the results table." in rendered
