"""Fixture-based integration test for issue #6: drives sync.run() end-to-end
against the fake Zotero Local API + Better BibTeX JSON-RPC (ZoteroStubServer)
and a scratch copy of the recorded zotero.sqlite fixture, then asserts on
the resulting vault state.

Unlike tests/test_sync_run_retire.py (which monkeypatches sync.build_papers/
sync.attach_annotations directly to isolate sync.run()'s citekey bookkeeping)
this test exercises the real pipeline: local_api.py and bbt_client.py talk
real HTTP to the stub server, annotations.py reads the real sqlite copy, and
sync.build_papers()/attach_annotations() run unmodified. Per tests/fixtures/
README.md's itemID/key/citekey table, the fixtures describe a 3-paper "My
Library":

  citekey             collections            annotations
  smith2020neural     Research               2 highlights (+1 filtered note)
  jones2019language   Machine Learning       1 highlight
  lee2021optimization (none)                 0

Author/Keyword index notes are explicitly out of scope (see issue #1's
"## Notes" — only Collection index notes are covered here) — sync.run()
itself never writes them, so this test also asserts the Authors/ and
Keywords/ folders are never created.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.fixtures.stub_server import FIXTURES_DIR, ZoteroStubServer
from zotero_sync import annotations, bbt_client, local_api, sync
from zotero_sync.config import Config


@pytest.fixture
def zotero_stub(monkeypatch):
    server = ZoteroStubServer()
    server.start()
    monkeypatch.setattr(local_api, "BASE_URL", server.local_api_base_url)
    monkeypatch.setattr(bbt_client, "RPC_URL", server.bbt_rpc_url)
    yield server
    server.stop()


@pytest.fixture
def zotero_sqlite_copy(tmp_path, monkeypatch):
    # Mirrors what annotations.copy_database() does against a real install —
    # point default_zotero_sqlite_path() at a throwaway copy of the checked-in
    # fixture so sync.run()'s own copy_database() call (a *second* copy, of
    # this one) never touches the repo's fixture file.
    dest = tmp_path / "zotero-source.sqlite"
    shutil.copy2(FIXTURES_DIR / "zotero.sqlite", dest)
    monkeypatch.setattr(annotations, "default_zotero_sqlite_path", lambda: dest)
    return dest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    return vault_dir


def _write_stub_note(vault: Path, citekey: str) -> None:
    papers_dir = vault / "Papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    (papers_dir / f"{citekey}.md").write_text(
        f"---\ncitekey: {citekey}\n---\n# Old note\n\nSome freeform notes I wrote by hand.\n",
        encoding="utf-8",
    )


def test_sync_run_writes_paper_and_collection_notes(zotero_stub, zotero_sqlite_copy, vault):
    config = Config(vault_path=vault)

    counts = sync.run(config)

    # --- Paper notes -------------------------------------------------
    papers_dir = vault / "Papers"
    written = {p.stem for p in papers_dir.glob("*.md")}
    assert written == {"smith2020neural", "jones2019language", "lee2021optimization"}

    smith = (papers_dir / "smith2020neural.md").read_text(encoding="utf-8")
    assert 'citekey: "smith2020neural"' in smith
    assert 'title: "Neural Representations for Structured Data"' in smith
    assert "Ada Smith" in smith
    assert 'year: "2020"' in smith
    assert 'type: "journalArticle"' in smith
    assert "Collections: [[Research]]" in smith
    # 2 highlights plus the note/underline/image annotations added by #18
    # should all be rendered.
    assert "Deep learning models require large amounts" in smith
    assert "The optimization landscape is non-convex" in smith
    assert "Follow up on this citation later." in smith

    jones = (papers_dir / "jones2019language.md").read_text(encoding="utf-8")
    assert 'citekey: "jones2019language"' in jones
    assert "Collections: [[Machine Learning]]" in jones
    assert "Evaluation methodology varies widely" in jones

    lee = (papers_dir / "lee2021optimization.md").read_text(encoding="utf-8")
    assert 'citekey: "lee2021optimization"' in lee
    assert "*No annotations yet.*" in lee

    # --- Collection index notes (NOT author/keyword — out of scope) --
    assert (vault / "Collections" / "Research.md").exists()
    research = (vault / "Collections" / "Research.md").read_text(encoding="utf-8")
    assert 'title: "Research"' in research
    assert "parent:" in research and 'parent: "' not in research  # top-level: no parent

    assert (vault / "Collections" / "Machine Learning.md").exists()
    ml = (vault / "Collections" / "Machine Learning.md").read_text(encoding="utf-8")
    assert 'title: "Machine Learning"' in ml
    assert 'parent: "Research"' in ml

    assert not (vault / "Authors").exists()
    assert not (vault / "Keywords").exists()

    assert counts.created.get("Papers") == 3
    assert counts.created.get("Collections") == 2
    assert counts.errors == []


def test_sync_run_retires_note_for_citekey_no_longer_in_library(
    zotero_stub, zotero_sqlite_copy, vault
):
    # A pre-existing note for a citekey that simply isn't in the fixture
    # library (never was, and isn't now) should be moved to .trash/, not
    # left behind or deleted outright.
    _write_stub_note(vault, "ghost1999vanished")

    config = Config(vault_path=vault)
    counts = sync.run(config)

    assert not (vault / "Papers" / "ghost1999vanished.md").exists()
    trashed = vault / ".trash" / "ghost1999vanished.md"
    assert trashed.exists()
    assert "Some freeform notes I wrote by hand." in trashed.read_text(encoding="utf-8")
    assert "ghost1999vanished" in counts.retired

    # The 3 real papers are untouched by the retire pass.
    for citekey in ("smith2020neural", "jones2019language", "lee2021optimization"):
        assert (vault / "Papers" / f"{citekey}.md").exists()
        assert citekey not in counts.retired


def test_sync_run_skips_case_insensitive_citekey_collision(
    monkeypatch, zotero_stub, zotero_sqlite_copy, vault
):
    # The fixtures' 3 real citekeys don't collide with each other, so this
    # test drives the same real stub-server + sqlite pipeline but overrides
    # the BBT JSON-RPC response data (the stub's module-level fixture dicts,
    # read fresh on every request) so two distinct items resolve to
    # case-colliding citekeys, exactly like a real Better BibTeX library
    # could produce. Everything else (Local API items, collections, sqlite
    # annotations) stays the real fixture data — sync.build_papers()/
    # sync.run() are not monkeypatched.
    import tests.fixtures.stub_server as stub_server_module

    colliding_citationkeys = {
        "1:AAAA1111": "Smith2020Neural",
        "1:BBBB2222": "smith2020neural",  # collides with AAAA1111's on case-insensitive FS
        "1:CCCC3333": "lee2021optimization",
    }
    monkeypatch.setattr(stub_server_module, "_CITATIONKEYS_RESULT", colliding_citationkeys)

    config = Config(vault_path=vault)
    counts = sync.run(config)

    papers_dir = vault / "Papers"
    written = {p.stem for p in papers_dir.glob("*.md")}
    # Per ADR 0002: skip-not-overwrite. The first-seen citekey (AAAA1111,
    # first in local_api/items.json's ordering) wins the write; the second
    # (BBBB2222) is skipped and reported as an error rather than silently
    # overwriting/being overwritten on a case-insensitive filesystem.
    assert "Smith2020Neural" in written
    assert "smith2020neural" not in written
    assert "lee2021optimization" in written

    assert any("smith2020neural" in err and "collides with citekey" in err for err in counts.errors)
    assert counts.created.get("Papers") == 2
