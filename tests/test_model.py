from __future__ import annotations

from zotero_sync.model import (
    ZOTERO_HIGHLIGHT_COLORS,
    Annotation,
    Collection,
    LibrarySnapshot,
    Paper,
)


def _minimal_paper(**overrides) -> Paper:
    kwargs = dict(
        citekey="smith2024widget",
        item_id=1,
        title="A Widget Study",
        authors=["Smith, John"],
        year="2024",
        item_type="journalArticle",
        doi=None,
        url=None,
        abstract=None,
        date_added=None,
        date_modified=None,
    )
    kwargs.update(overrides)
    return Paper(**kwargs)


def test_paper_default_factories_are_empty() -> None:
    paper = _minimal_paper()

    assert paper.collections == []
    assert paper.tags == []
    assert paper.extra_fields == {}
    assert paper.annotations == []


def test_paper_default_factories_are_not_shared_between_instances() -> None:
    # Classic dataclass footgun: mutable defaults must use default_factory,
    # not a shared literal, or mutating one instance leaks into another.
    paper_a = _minimal_paper(citekey="a2024")
    paper_b = _minimal_paper(citekey="b2024")

    paper_a.collections.append("Some Collection")
    paper_a.tags.append("some-tag")
    paper_a.extra_fields["volume"] = "3"
    paper_a.annotations.append(
        Annotation(text="hi", comment=None, color="#ffd400", page_label="1", sort_index="0")
    )

    assert paper_b.collections == []
    assert paper_b.tags == []
    assert paper_b.extra_fields == {}
    assert paper_b.annotations == []


def test_paper_optional_fields_accept_none() -> None:
    paper = _minimal_paper(doi=None, url=None, abstract=None, year=None)

    assert paper.doi is None
    assert paper.url is None
    assert paper.abstract is None
    assert paper.year is None


def test_annotation_fields_roundtrip() -> None:
    ann = Annotation(
        text="highlighted text",
        comment="a note",
        color="#5fb236",
        page_label="12",
        sort_index="00042",
    )

    assert ann.text == "highlighted text"
    assert ann.comment == "a note"
    assert ann.color == "#5fb236"
    assert ann.page_label == "12"
    assert ann.sort_index == "00042"


def test_annotation_comment_may_be_none() -> None:
    ann = Annotation(text="x", comment=None, color="#aaaaaa", page_label="1", sort_index="0")

    assert ann.comment is None


def test_collection_defaults_to_no_parent() -> None:
    collection = Collection(name="Top Level")

    assert collection.parent is None


def test_collection_with_parent() -> None:
    collection = Collection(name="Child", parent="Top Level")

    assert collection.parent == "Top Level"


def test_library_snapshot_holds_all_components() -> None:
    paper = _minimal_paper()
    collection = Collection(name="Root")
    snapshot = LibrarySnapshot(
        papers=[paper],
        collections=[collection],
        authors={"Smith, John"},
        keywords={"widgets"},
    )

    assert snapshot.papers == [paper]
    assert snapshot.collections == [collection]
    assert snapshot.authors == {"Smith, John"}
    assert snapshot.keywords == {"widgets"}


def test_zotero_highlight_colors_cover_expected_names() -> None:
    # Guards against accidental edits to the color table (sourced from
    # zotero/reader's defines.js per research/03).
    assert ZOTERO_HIGHLIGHT_COLORS == {
        "#ffd400": "Yellow",
        "#ff6666": "Red",
        "#5fb236": "Green",
        "#2ea8e5": "Blue",
        "#a28ae5": "Purple",
        "#e56eee": "Magenta",
        "#f19837": "Orange",
        "#aaaaaa": "Gray",
    }
