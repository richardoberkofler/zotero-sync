from __future__ import annotations

import codecs

from zotero_sync.model import Paper
from zotero_sync.notes.paper import _yaml_scalar, render_frontmatter


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
    paper = _make_paper(
        abstract="First paragraph.\nSecond paragraph.\r\nThird with a \\backslash\\.",
        title='A "quoted" title',
    )
    fields = ["title", "abstract", "citekey"]
    frontmatter = render_frontmatter(paper, fields)

    body_lines = frontmatter.strip("\n").split("\n")
    # ---, title, abstract, citekey, --- => 5 lines, one per field plus fences
    assert body_lines[0] == "---"
    assert body_lines[-1] == "---"
    field_lines = body_lines[1:-1]
    assert len(field_lines) == len(fields)
    for line in field_lines:
        # No embedded raw newlines: each element of the split is a genuine
        # single physical line.
        assert "\n" not in line

    abstract_line = next(line for line in field_lines if line.startswith("abstract:"))
    _, _, scalar = abstract_line.partition(": ")
    assert _unescape_double_quoted(scalar) == (
        "First paragraph.\nSecond paragraph.\nThird with a \\backslash\\."
    )


def test_render_frontmatter_parses_with_pyyaml_if_available():
    try:
        import yaml
    except ImportError:
        return

    paper = _make_paper(
        abstract='Multi\nline "abstract" with a \\ backslash.',
        title="Normal Title",
    )
    fields = ["title", "abstract", "citekey", "year"]
    frontmatter = render_frontmatter(paper, fields)
    text = frontmatter.strip("-\n")
    parsed = yaml.safe_load(text)
    assert parsed["abstract"] == 'Multi\nline "abstract" with a \\ backslash.'
    assert parsed["title"] == "Normal Title"
