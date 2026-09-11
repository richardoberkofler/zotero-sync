"""Covers #29: the "web" mode config toggle designed in #28 — reading
`mode` from .zotero-sync.toml, sourcing web-mode credentials from a
sibling .env (never the TOML itself), auto-generating a template .env on
first setup, and the .gitignore safety net for both the .env and the
sync-state file."""

from __future__ import annotations

from pathlib import Path

import pytest

from zotero_sync.config import CONFIG_FILENAME, ENV_FILENAME, env_path, load_or_init_config
from zotero_sync.errors import ZoteroSyncError
from zotero_sync.sync_state import STATE_FILENAME


def _write_toml(tmp_path: Path, mode: str = "web") -> None:
    (tmp_path / CONFIG_FILENAME).write_text(f'mode = "{mode}"\n', encoding="utf-8")


def test_default_mode_is_local(tmp_path: Path) -> None:
    config, _ = load_or_init_config(tmp_path)
    assert config.mode == "local"
    assert config.web_api_key is None


def test_web_mode_without_env_file_generates_template_and_raises(tmp_path: Path) -> None:
    _write_toml(tmp_path)

    with pytest.raises(ZoteroSyncError, match="wrote a template"):
        load_or_init_config(tmp_path)

    assert env_path(tmp_path).exists()
    contents = env_path(tmp_path).read_text(encoding="utf-8")
    assert "ZOTERO_API_KEY=" in contents
    assert "ZOTERO_LIBRARY_ID=" in contents
    assert "ZOTERO_LIBRARY_TYPE=user" in contents


def test_web_mode_generating_env_template_gitignores_it(tmp_path: Path) -> None:
    _write_toml(tmp_path)

    with pytest.raises(ZoteroSyncError):
        load_or_init_config(tmp_path)

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ENV_FILENAME in gitignore
    assert STATE_FILENAME in gitignore


def test_web_mode_with_incomplete_env_raises(tmp_path: Path) -> None:
    _write_toml(tmp_path)
    env_path(tmp_path).write_text("ZOTERO_API_KEY=abc123\n", encoding="utf-8")

    with pytest.raises(ZoteroSyncError, match="ZOTERO_LIBRARY_ID"):
        load_or_init_config(tmp_path)


def test_web_mode_with_complete_env_loads_credentials(tmp_path: Path) -> None:
    _write_toml(tmp_path)
    env_path(tmp_path).write_text(
        "ZOTERO_API_KEY=abc123\n"
        "ZOTERO_LIBRARY_ID=1234567\n"
        "ZOTERO_LIBRARY_TYPE=group\n"
        "# a comment, and a blank line follow\n"
        "\n",
        encoding="utf-8",
    )

    config, _ = load_or_init_config(tmp_path)

    assert config.mode == "web"
    assert config.web_api_key == "abc123"
    assert config.web_library_id == "1234567"
    assert config.web_library_type == "group"


def test_web_mode_never_reads_credentials_from_toml(tmp_path: Path) -> None:
    # Deliberate: the design decision (#28) was to keep secrets out of the
    # TOML entirely, since it lives inside a vault that might be
    # version-controlled — putting a key field in DEFAULT_CONFIG_TEMPLATE
    # would silently invite that.
    (tmp_path / CONFIG_FILENAME).write_text(
        'mode = "web"\nZOTERO_API_KEY = "should-be-ignored"\n', encoding="utf-8"
    )
    env_path(tmp_path).write_text(
        "ZOTERO_API_KEY=real-key\nZOTERO_LIBRARY_ID=1\nZOTERO_LIBRARY_TYPE=user\n",
        encoding="utf-8",
    )

    config, _ = load_or_init_config(tmp_path)

    assert config.web_api_key == "real-key"


def test_local_mode_does_not_touch_env_file(tmp_path: Path) -> None:
    _write_toml(tmp_path, mode="local")

    load_or_init_config(tmp_path)

    assert not env_path(tmp_path).exists()
