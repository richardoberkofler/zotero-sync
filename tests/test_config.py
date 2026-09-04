from __future__ import annotations

from pathlib import Path

import pytest

from zotero_sync.config import (
    CONFIG_FILENAME,
    FRONTMATTER_FULL,
    FRONTMATTER_SLIM,
    Config,
    apply_overrides,
    config_path,
    load_or_init_config,
)
from zotero_sync.errors import ZoteroSyncError


def test_load_or_init_config_generates_default_when_missing(tmp_path: Path) -> None:
    config, generated = load_or_init_config(tmp_path)

    assert generated is True
    assert config.vault_path == tmp_path
    assert config.frontmatter == "slim"
    assert (tmp_path / CONFIG_FILENAME).exists()


def test_load_or_init_config_defaults_when_file_exists_but_is_empty(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text("", encoding="utf-8")

    config, generated = load_or_init_config(tmp_path)

    assert generated is False
    assert config.collection is None
    assert config.include_auto_tags is False
    assert config.frontmatter == "slim"
    assert config.dry_run is False


def test_load_or_init_config_reads_overrides_from_existing_file(tmp_path: Path) -> None:
    config_file = tmp_path / CONFIG_FILENAME
    config_file.write_text(
        'collection = "My Collection"\n'
        "include_auto_tags = true\n"
        'frontmatter = ["title", "citekey"]\n',
        encoding="utf-8",
    )

    config, generated = load_or_init_config(tmp_path)

    assert generated is False
    assert config.collection == "My Collection"
    assert config.include_auto_tags is True
    assert config.frontmatter == ["title", "citekey"]


def test_load_or_init_config_raises_zotero_sync_error_on_malformed_toml(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / CONFIG_FILENAME
    config_file.write_text("this is not valid toml [[[", encoding="utf-8")

    with pytest.raises(ZoteroSyncError) as exc_info:
        load_or_init_config(tmp_path)

    message = str(exc_info.value)
    assert str(config_file) in message


def test_config_path_joins_vault_and_filename(tmp_path: Path) -> None:
    assert config_path(tmp_path) == tmp_path / CONFIG_FILENAME


def test_frontmatter_fields_slim(tmp_path: Path) -> None:
    config = Config(vault_path=tmp_path, frontmatter="slim")

    assert config.frontmatter_fields == FRONTMATTER_SLIM


def test_frontmatter_fields_full(tmp_path: Path) -> None:
    config = Config(vault_path=tmp_path, frontmatter="full")

    assert config.frontmatter_fields == FRONTMATTER_FULL


def test_frontmatter_fields_explicit_list(tmp_path: Path) -> None:
    config = Config(vault_path=tmp_path, frontmatter=["title", "citekey"])

    assert config.frontmatter_fields == ["title", "citekey"]


def test_frontmatter_fields_invalid_value_raises(tmp_path: Path) -> None:
    config = Config(vault_path=tmp_path, frontmatter="bogus")

    with pytest.raises(ZoteroSyncError, match="bogus"):
        _ = config.frontmatter_fields


def test_apply_overrides_cli_values_override_file_values(tmp_path: Path) -> None:
    config = Config(vault_path=tmp_path, collection="From File", include_auto_tags=False)

    result = apply_overrides(config, collection="From CLI", include_auto_tags=True, dry_run=True)

    assert result.collection == "From CLI"
    assert result.include_auto_tags is True
    assert result.dry_run is True


def test_apply_overrides_none_values_fall_back_to_file_config(tmp_path: Path) -> None:
    config = Config(vault_path=tmp_path, collection="From File", include_auto_tags=True)

    result = apply_overrides(config, collection=None, include_auto_tags=None, dry_run=False)

    # collection/include_auto_tags are unset on the CLI (None), so the
    # file-derived config values must survive untouched.
    assert result.collection == "From File"
    assert result.include_auto_tags is True


def test_apply_overrides_dry_run_always_taken_from_cli_even_when_false(tmp_path: Path) -> None:
    # dry_run has no config-file counterpart, so unlike the other flags it's
    # never guarded by an is-None check — False from the CLI must still win.
    config = Config(vault_path=tmp_path, dry_run=True)

    result = apply_overrides(config, collection=None, include_auto_tags=None, dry_run=False)

    assert result.dry_run is False


def test_apply_overrides_returns_the_same_config_instance(tmp_path: Path) -> None:
    config = Config(vault_path=tmp_path)

    result = apply_overrides(config, collection=None, include_auto_tags=None, dry_run=False)

    assert result is config
