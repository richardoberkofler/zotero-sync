"""Regression tests for issue #14: sync.run() must not retire (trash) a
paper's existing note just because that paper failed to sync *this run*
(transient OSError, or a case-insensitive citekey collision) — only a
citekey that is genuinely absent from the library should be retired.

These monkeypatch sync.build_papers()/sync.attach_annotations() directly
(rather than driving the whole pipeline through the stub server + fixture
sqlite) since the behavior under test lives entirely in sync.run()'s
per-paper loop and retire pass; build_papers/attach_annotations are
exercised elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zotero_sync import annotations, bbt_client, sync
from zotero_sync.config import Config
from zotero_sync.model import Paper


def _paper(citekey: str) -> Paper:
    return Paper(
        citekey=citekey,
        item_id=0,
        title=f"Title for {citekey}",
        authors=["Someone"],
        year="2020",
        item_type="journalArticle",
        doi=None,
        url=None,
        abstract=None,
        date_added=None,
        date_modified=None,
    )


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    papers_dir = tmp_path / "Papers"
    papers_dir.mkdir()
    return tmp_path


def _write_stub_note(vault: Path, citekey: str) -> None:
    (vault / "Papers" / f"{citekey}.md").write_text(
        f"---\ncitekey: {citekey}\n---\n", encoding="utf-8"
    )


@pytest.fixture
def no_network(monkeypatch, tmp_path: Path):
    """Bypass the real BBT precondition check and sqlite discovery/copy —
    this test only cares about sync.run()'s citekey bookkeeping, which runs
    after build_papers()/attach_annotations() (both monkeypatched per-test)."""
    monkeypatch.setattr(bbt_client, "check_ready", lambda: None)
    fake_db = tmp_path / "zotero.sqlite"
    fake_db.write_bytes(b"")
    monkeypatch.setattr(annotations, "default_zotero_sqlite_path", lambda: fake_db)
    monkeypatch.setattr(annotations, "copy_database", lambda source: fake_db)
    monkeypatch.setattr(sync, "attach_annotations", lambda papers, db_copy: None)


def test_oserror_during_write_does_not_retire_existing_note(monkeypatch, vault, no_network):
    # A paper that is still in the library but whose note write blows up
    # with an OSError this run (e.g. a transient file-lock/permission issue).
    _write_stub_note(vault, "errpaper2020")
    papers = [_paper("alive2020"), _paper("errpaper2020")]
    monkeypatch.setattr(sync, "build_papers", lambda config, db_copy, counts=None: (papers, {}))

    def fake_write_paper_note(vault_path, paper, fields, dry_run, counts):
        if paper.citekey == "errpaper2020":
            raise OSError("simulated transient write failure")
        counts.bump("Papers", "created")

    monkeypatch.setattr(sync, "write_paper_note", fake_write_paper_note)

    config = Config(vault_path=vault)
    counts = sync.run(config)

    # The pre-existing note must survive untouched, not get trashed.
    assert (vault / "Papers" / "errpaper2020.md").exists()
    assert not (vault / ".trash" / "errpaper2020.md").exists()
    assert "errpaper2020" not in counts.retired
    assert any("errpaper2020" in err for err in counts.errors)


def test_case_collision_does_not_retire_existing_note(monkeypatch, vault, no_network):
    # "coll2020" already has a note from a previous run. This run, the
    # library has both "Coll2020" and "coll2020" — a case-insensitive
    # filesystem collision — so "coll2020" gets skipped as a collision.
    # It's still genuinely present in the library, so its old note must
    # not be retired.
    _write_stub_note(vault, "coll2020")
    papers = [_paper("Coll2020"), _paper("coll2020")]
    monkeypatch.setattr(sync, "build_papers", lambda config, db_copy, counts=None: (papers, {}))

    config = Config(vault_path=vault)
    counts = sync.run(config)

    assert not (vault / ".trash" / "coll2020.md").exists()
    assert not (vault / ".trash" / "Coll2020.md").exists()
    assert "coll2020" not in counts.retired
    assert any("coll2020" in err for err in counts.errors)


def test_paper_genuinely_absent_from_library_is_still_retired(monkeypatch, vault, no_network):
    # Sanity check that the fix doesn't disable retirement altogether: a
    # note for a citekey that simply isn't in the library anymore (no
    # error, no collision) should still be trashed.
    _write_stub_note(vault, "gone2019")
    papers: list[Paper] = []
    monkeypatch.setattr(sync, "build_papers", lambda config, db_copy, counts=None: (papers, {}))

    config = Config(vault_path=vault)
    counts = sync.run(config)

    assert (vault / ".trash" / "gone2019.md").exists()
    assert not (vault / "Papers" / "gone2019.md").exists()
    assert "gone2019" in counts.retired
