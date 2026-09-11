"""Covers #24/#30: parse_yaml_list() reads back exactly what yaml_list()
writes — a narrow reader/writer pair for this module's own format, not a
general YAML parser."""

from __future__ import annotations

from zotero_sync.notes.yaml_util import parse_yaml_list, yaml_list


def test_parse_yaml_list_roundtrips_simple_values():
    text = f"collections: {yaml_list(['Research', 'Machine Learning'])}\n"

    assert parse_yaml_list(text, "collections") == ["Research", "Machine Learning"]


def test_parse_yaml_list_roundtrips_empty_list():
    text = f"tags: {yaml_list([])}\n"

    assert parse_yaml_list(text, "tags") == []


def test_parse_yaml_list_roundtrips_escaped_characters():
    values = ['Quote " mark', "Back\\slash", "New\nline"]
    text = f"tags: {yaml_list(values)}\n"

    assert parse_yaml_list(text, "tags") == values


def test_parse_yaml_list_returns_none_when_field_absent():
    text = 'title: "Something"\n'

    assert parse_yaml_list(text, "collections") is None


def test_parse_yaml_list_stops_at_next_field():
    text = f"collections: {yaml_list(['Research'])}\ntags: {yaml_list(['a-tag'])}\n"

    assert parse_yaml_list(text, "collections") == ["Research"]
    assert parse_yaml_list(text, "tags") == ["a-tag"]
