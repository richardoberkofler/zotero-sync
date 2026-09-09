from __future__ import annotations

import codecs

from zotero_sync.model import Paper
from zotero_sync.notes.paper import (
    ABSTRACT_END,
    ABSTRACT_START,
    _slugify_tag,
    render_abstract,
    render_frontmatter,
)
from zotero_sync.notes.yaml_util import yaml_scalar as _yaml_scalar


def _make_paper(**overrides) -> Paper:
    defaults = dict(
        citekey="doe2020",
        item_id=1,
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
