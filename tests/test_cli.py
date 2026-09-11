"""Covers cli.main()'s onboarding gate: interactive first-run onboarding
only fires when both conditions hold — no config file yet, and stdin is a
real terminal. Everything past that gate (sync.run() itself) is exercised
elsewhere; here we only care whether onboarding.run() gets invoked."""

from __future__ import annotations

from pathlib import Path

import pytest

from zotero_sync import cli, onboarding


@pytest.fixture
def no_sync(monkeypatch):
    """Stub out the actual sync so these tests only exercise the onboarding
    gate, not a real Zotero/BBT connection."""
    from zotero_sync.vault import SyncCounts

    monkeypatch.setattr(cli.sync, "run", lambda config: SyncCounts())


def test_onboarding_runs_on_first_run_in_a_tty(monkeypatch, tmp_path: Path, no_sync) -> None:
    calls = []
    monkeypatch.setattr(onboarding, "run", lambda vault_path: calls.append(vault_path))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)

    cli.main(["--vault", str(tmp_path)])

    assert calls == [tmp_path]


def test_onboarding_skipped_when_not_a_tty(monkeypatch, tmp_path: Path, no_sync) -> None:
    calls = []
    monkeypatch.setattr(onboarding, "run", lambda vault_path: calls.append(vault_path))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)

    cli.main(["--vault", str(tmp_path)])

    assert calls == []
    assert (tmp_path / ".zotero-sync.toml").exists()


def test_onboarding_skipped_when_config_already_exists(
    monkeypatch, tmp_path: Path, no_sync
) -> None:
    (tmp_path / ".zotero-sync.toml").write_text('mode = "local"\n', encoding="utf-8")
    calls = []
    monkeypatch.setattr(onboarding, "run", lambda vault_path: calls.append(vault_path))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)

    cli.main(["--vault", str(tmp_path)])

    assert calls == []
