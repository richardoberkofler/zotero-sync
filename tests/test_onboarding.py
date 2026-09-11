"""Covers the interactive first-run onboarding: choosing local vs. web mode
and, for web, collecting Zotero API credentials — writes exactly what
config.py's load_or_init_config() would otherwise generate/demand by hand,
just gathered interactively instead."""

from __future__ import annotations

from pathlib import Path

from zotero_sync import onboarding, web_api
from zotero_sync.config import CONFIG_FILENAME, env_path


def _answers(*values: str):
    it = iter(values)

    def ask(_prompt: str) -> str:
        return next(it)

    return ask


def test_is_first_run_true_when_no_config(tmp_path: Path) -> None:
    assert onboarding.is_first_run(tmp_path) is True


def test_is_first_run_false_once_config_exists(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text('mode = "local"\n', encoding="utf-8")

    assert onboarding.is_first_run(tmp_path) is False


def test_choosing_local_writes_local_mode_config_and_no_env(tmp_path: Path) -> None:
    onboarding.run(tmp_path, ask=_answers("1"), ask_secret=_answers())

    config_text = (tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8")
    assert 'mode = "local"' in config_text
    assert not env_path(tmp_path).exists()


def test_blank_answer_defaults_to_local(tmp_path: Path) -> None:
    onboarding.run(tmp_path, ask=_answers(""), ask_secret=_answers())

    config_text = (tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8")
    assert 'mode = "local"' in config_text


def test_choosing_web_writes_web_mode_config_and_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(onboarding, "_verify_credentials", lambda *a: True)

    onboarding.run(
        tmp_path,
        ask=_answers("2", "1234567", "group"),
        ask_secret=_answers("secret-key"),
    )

    config_text = (tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8")
    assert 'mode = "web"' in config_text
    env_text = env_path(tmp_path).read_text(encoding="utf-8")
    assert "ZOTERO_API_KEY=secret-key" in env_text
    assert "ZOTERO_LIBRARY_ID=1234567" in env_text
    assert "ZOTERO_LIBRARY_TYPE=group" in env_text


def test_choosing_web_gitignores_env_and_state_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(onboarding, "_verify_credentials", lambda *a: True)

    onboarding.run(
        tmp_path,
        ask=_answers("2", "1234567", "user"),
        ask_secret=_answers("secret-key"),
    )

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert ".zotero-sync-state.json" in gitignore


def test_invalid_library_type_reprompts_until_valid(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(onboarding, "_verify_credentials", lambda *a: True)

    onboarding.run(
        tmp_path,
        ask=_answers("2", "1234567", "bogus", "user"),
        ask_secret=_answers("secret-key"),
    )

    env_text = env_path(tmp_path).read_text(encoding="utf-8")
    assert "ZOTERO_LIBRARY_TYPE=user" in env_text


def test_blank_library_type_defaults_to_user(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(onboarding, "_verify_credentials", lambda *a: True)

    onboarding.run(
        tmp_path,
        ask=_answers("2", "1234567", ""),
        ask_secret=_answers("secret-key"),
    )

    env_text = env_path(tmp_path).read_text(encoding="utf-8")
    assert "ZOTERO_LIBRARY_TYPE=user" in env_text


def test_verify_credentials_true_when_web_api_call_succeeds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(web_api, "configure", lambda *a, **k: None)
    monkeypatch.setattr(web_api, "list_collections", lambda: [])

    assert onboarding._verify_credentials("1", "user", "key") is True


def test_verify_credentials_false_when_web_api_call_raises(monkeypatch, tmp_path: Path) -> None:
    from zotero_sync.errors import ZoteroSyncError

    monkeypatch.setattr(web_api, "configure", lambda *a, **k: None)

    def _raise():
        raise ZoteroSyncError("boom")

    monkeypatch.setattr(web_api, "list_collections", _raise)

    assert onboarding._verify_credentials("1", "user", "key") is False
