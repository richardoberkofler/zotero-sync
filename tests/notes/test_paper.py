from __future__ import annotations

import codecs

from zotero_sync.model import Paper
from zotero_sync.notes.paper import (
    ABSTRACT_END,
    ABSTRACT_START,
    _slugify_tag,
    detect_changes,
    render_abstract,
    render_frontmatter,
    update_existing_note,
)
from zotero_sync.notes.yaml_util import yaml_scalar as _yaml_scalar


def _make_paper(**overrides) -> Paper:
    defaults = dict(
        citekey="doe2020",
        item_id=1,
        zotero_key="AAAA1111",
        title="A Title",
        authors=["Jane Doe"],
        year="2020",
        item_type="journalArticle",
        doi=None,
        url=None,
        abstract=None,
        date_added=None,
        date_modified=None,
    )
    defaults.update(overrides)
    return Paper(**defaults)


def _unescape_double_quoted(scalar: str) -> str:
    """Minimal decoder for the subset of double-quoted YAML escapes this
    module emits (\\\\, \\", \\n), used to verify round-tripping without
    depending on PyYAML being installed."""
    assert scalar.startswith('"') and scalar.endswith('"')
    inner = scalar[1:-1]
    return codecs.decode(inner, "unicode_escape")


def test_yaml_scalar_escapes_double_quotes():
    assert _yaml_scalar('he said "hi"') == '"he said \\"hi\\""'


def test_yaml_scalar_escapes_backslashes():
    assert _yaml_scalar("C:\\path\\to\\file") == '"C:\\\\path\\\\to\\\\file"'


def test_yaml_scalar_escapes_newlines():
    assert _yaml_scalar("line one\nline two") == '"line one\\nline two"'


def test_yaml_scalar_escapes_backslash_before_quotes_no_double_escaping():
    # A trailing backslash right before a quote must not combine with the
    # quote's own escaping to form an invalid/incorrect sequence.
    value = 'a\\"b'
    scalar = _yaml_scalar(value)
    assert _unescape_double_quoted(scalar) == value


def test_yaml_scalar_round_trips_mixed_content():
    value = 'Backslash \\ and "quote" and\nnewline\r\nand crlf'
    scalar = _yaml_scalar(value)
    assert _unescape_double_quoted(scalar) == ('Backslash \\ and "quote" and\nnewline\nand crlf')


def test_render_frontmatter_keeps_each_field_on_a_single_line():
    paper = _make_paper(title='A "quoted" title\nwith an embedded\r\nnewline')
    fields = ["title", "citekey"]
    frontmatter = render_frontmatter(paper, fields)

    body_lines = frontmatter.strip("\n").split("\n")
    # ---, title, citekey, --- => 4 lines, one per field plus fences
    assert body_lines[0] == "---"
    assert body_lines[-1] == "---"
    field_lines = body_lines[1:-1]
    assert len(field_lines) == len(fields)
    for line in field_lines:
        # No embedded raw newlines: each element of the split is a genuine
        # single physical line.
        assert "\n" not in line


def test_render_frontmatter_omits_abstract_even_when_listed():
    paper = _make_paper(abstract="Some abstract text.")
    frontmatter = render_frontmatter(paper, ["title", "abstract", "citekey"])
    assert "abstract" not in frontmatter


def test_render_abstract_wraps_text_in_markers():
    paper = _make_paper(
        abstract="First paragraph.\nSecond paragraph.\r\nThird with a \\backslash\\."
    )
    block = render_abstract(paper)
    assert block.startswith(ABSTRACT_START)
    assert block.rstrip("\n").endswith(ABSTRACT_END)
    assert "First paragraph.\nSecond paragraph.\r\nThird with a \\backslash\\." in block


def test_render_abstract_placeholder_when_missing():
    paper = _make_paper(abstract=None)
    block = render_abstract(paper)
    assert "*No abstract.*" in block


def test_slugify_tag_replaces_spaces_with_hyphens():
    assert _slugify_tag("INDUSTRIAL PLANTS") == "industrial-plants"


def test_slugify_tag_collapses_space_hyphen_space():
    assert _slugify_tag("MANAGEMENT - Information Systems") == "management-information-systems"


def test_slugify_tag_lowercases():
    assert _slugify_tag("ENTERPRISE INTEGRATION") == "enterprise-integration"


def test_slugify_tag_preserves_nesting_slash():
    assert _slugify_tag("Topic/Sub Topic") == "topic/sub-topic"


def test_render_frontmatter_slugifies_tags_field():
    paper = _make_paper(tags=["INDUSTRIAL PLANTS", "ENTERPRISE INTEGRATION"])
    frontmatter = render_frontmatter(paper, ["tags"])
    assert '"industrial-plants"' in frontmatter
    assert '"enterprise-integration"' in frontmatter
    assert '"INDUSTRIAL PLANTS"' not in frontmatter


def test_render_frontmatter_parses_with_pyyaml_if_available():
    try:
        import yaml
    except ImportError:
        return

    paper = _make_paper(title='Multi\nline "title" with a \\ backslash.')
    fields = ["title", "citekey", "year"]
    frontmatter = render_frontmatter(paper, fields)
    text = frontmatter.strip("-\n")
    parsed = yaml.safe_load(text)
    assert parsed["title"] == 'Multi\nline "title" with a \\ backslash.'


# --- detect_changes (#24) ----------------------------------------------


def _note_text(paper: Paper) -> str:
    return update_existing_note("", paper, ["collections", "tags"])


def test_detect_changes_with_no_snapshot_reports_nothing():
    paper = _make_paper(direct_collections=["Research"], tags=["Neural Networks"])

    result = detect_changes(_note_text(paper), paper, None)

    assert result == {
        "vault_collections": False,
        "vault_tags": False,
        "zotero_collections": False,
        "zotero_tags": False,
    }


def test_detect_changes_with_matching_snapshot_reports_nothing():
    paper = _make_paper(direct_collections=["Research"], tags=["Neural Networks"])
    snapshot = {"collections": ["Research"], "tags": ["neural-networks"]}

    result = detect_changes(_note_text(paper), paper, snapshot)

    assert result == {
        "vault_collections": False,
        "vault_tags": False,
        "zotero_collections": False,
        "zotero_tags": False,
    }


def test_detect_changes_flags_vault_side_collection_edit():
    paper = _make_paper(direct_collections=["Research"], tags=["Neural Networks"])
    snapshot = {"collections": ["Research"], "tags": ["neural-networks"]}
    # Simulate a hand-edit: the vault note's frontmatter now says something
    # the last-synced snapshot doesn't know about.
    edited_text = _note_text(paper).replace('"Research"', '"Research", "Hand-added"')

    result = detect_changes(edited_text, paper, snapshot)

    assert result["vault_collections"] is True
    assert result["vault_tags"] is False


def test_detect_changes_flags_vault_side_tag_edit():
    paper = _make_paper(direct_collections=["Research"], tags=["Neural Networks"])
    snapshot = {"collections": ["Research"], "tags": ["neural-networks"]}
    edited_text = _note_text(paper).replace('"neural-networks"', '"hand-added-tag"')

    result = detect_changes(edited_text, paper, snapshot)

    assert result["vault_tags"] is True
    assert result["vault_collections"] is False


def test_detect_changes_flags_zotero_side_change():
    # paper.collections/tags reflect what Zotero has *now*; a snapshot
    # from an older sync that doesn't match means Zotero changed since.
    paper = _make_paper(direct_collections=["Research", "New In Zotero"], tags=["Neural Networks"])
    snapshot = {"collections": ["Research"], "tags": ["neural-networks"]}

    result = detect_changes(_note_text(paper), paper, snapshot)

    assert result["zotero_collections"] is True
    assert result["zotero_tags"] is False


def test_detect_changes_ignores_list_order():
    paper = _make_paper(
        direct_collections=["Research", "Machine Learning"], tags=["A Tag", "B Tag"]
    )
    snapshot = {"collections": ["Machine Learning", "Research"], "tags": ["b-tag", "a-tag"]}

    result = detect_changes(_note_text(paper), paper, snapshot)

    assert not any(result.values())


def test_detect_changes_with_no_frontmatter_block_reports_no_vault_change():
    paper = _make_paper(direct_collections=["Research"], tags=["Neural Networks"])
    snapshot = {"collections": ["Research"], "tags": ["neural-networks"]}

    result = detect_changes("# Just a heading, no frontmatter", paper, snapshot)

    assert result["vault_collections"] is False
    assert result["vault_tags"] is False


def test_detect_changes_with_none_existing_text_skips_vault_side():
    paper = _make_paper(direct_collections=["Research"], tags=["Neural Networks"])
    snapshot = {"collections": ["Research"], "tags": ["neural-networks"]}

    result = detect_changes(None, paper, snapshot)

    assert result["vault_collections"] is False
    assert result["vault_tags"] is False
