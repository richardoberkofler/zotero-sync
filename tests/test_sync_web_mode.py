"""Covers #29: sync.run() in "web" mode — reads go through web_api.py
instead of local_api.py (see sync._api_module()), and a sync-state file
recording each item's current version gets written after a successful
run, for a future write path (#28's scope boundary: this ticket doesn't
add vault->Zotero writes, only the plumbing they'll need)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.fixtures.stub_server import FIXTURES_DIR, ZoteroStubServer
from zotero_sync import annotations, bbt_client, local_api, sync
from zotero_sync.config import Config
from zotero_sync.sync_state import state_path


@pytest.fixture
def zotero_stub(monkeypatch):
    server = ZoteroStubServer()
    server.start()
    # sync.run() calls web_api.configure(), which rebuilds BASE_URL from
    # config — so unlike local_api.py, monkeypatching web_api.BASE_URL
    # directly wouldn't survive that call. Config.web_api_root (a test-only
    # seam, see config.py) is what actually redirects it to the stub.
    monkeypatch.setattr(local_api, "BASE_URL", server.local_api_base_url)
    monkeypatch.setattr(bbt_client, "RPC_URL", server.bbt_rpc_url)
    yield server
    server.stop()


@pytest.fixture
def zotero_sqlite_copy(tmp_path, monkeypatch):
    dest = tmp_path / "zotero-source.sqlite"
    shutil.copy2(FIXTURES_DIR / "zotero.sqlite", dest)
    monkeypatch.setattr(annotations, "default_zotero_sqlite_path", lambda: dest)
    return dest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    return vault_dir


def _web_config(vault: Path, stub: ZoteroStubServer, **overrides) -> Config:
    defaults = dict(
        vault_path=vault,
        mode="web",
        web_api_key="test-key",
        web_library_id="0",
        web_library_type="user",
        web_api_root=f"http://127.0.0.1:{stub.port}",
    )
    defaults.update(overrides)
    return Config(**defaults)


def test_sync_run_in_web_mode_writes_paper_notes(zotero_stub, zotero_sqlite_copy, vault):
    counts = sync.run(_web_config(vault, zotero_stub))

    assert (vault / "Papers" / "smith2020neural.md").exists()
    assert not counts.errors


def test_sync_run_in_web_mode_writes_sync_state(zotero_stub, zotero_sqlite_copy, vault):
    sync.run(_web_config(vault, zotero_stub))

    state = json.loads(state_path(vault).read_text(encoding="utf-8"))

    assert state["AAAA1111"] == 101


def test_sync_run_in_web_mode_dry_run_does_not_write_sync_state(
    zotero_stub, zotero_sqlite_copy, vault
):
    sync.run(_web_config(vault, zotero_stub, dry_run=True))

    assert not state_path(vault).exists()


def test_sync_run_in_local_mode_does_not_write_sync_state(zotero_stub, zotero_sqlite_copy, vault):
    sync.run(Config(vault_path=vault))

    assert not state_path(vault).exists()
