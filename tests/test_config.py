from __future__ import annotations

from pathlib import Path

import pytest

from zotero_sync.config import CONFIG_FILENAME, load_or_init_config
from zotero_sync.errors import ZoteroSyncError


def test_load_or_init_config_generates_default_when_missing(tmp_path: Path) -> None:
    config, generated = load_or_init_config(tmp_path)

    assert generated is True
    assert config.vault_path == tmp_path
    assert config.frontmatter == "slim"
    assert (tmp_path / CONFIG_FILENAME).exists()


def test_load_or_init_config_raises_zotero_sync_error_on_malformed_toml(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / CONFIG_FILENAME
    config_file.write_text("this is not valid toml [[[", encoding="utf-8")

    with pytest.raises(ZoteroSyncError) as exc_info:
        load_or_init_config(tmp_path)

    message = str(exc_info.value)
    assert str(config_file) in message
