from __future__ import annotations

from pathlib import Path

from zotero_sync.model import Paper
from zotero_sync.vault import (
    PAPERS_DIR,
    TRASH_DIR,
    SyncCounts,
    existing_paper_citekeys,
    index_note_path,
    paper_note_path,
    retire_note,
    write_index_note,
    write_paper_note,
)


def _paper(citekey: str = "smith2024widget", **overrides) -> Paper:
    kwargs = dict(
        citekey=citekey,
        item_id=1,
        title="A Widget Study",
        authors=["Smith, John"],
        year="2024",
        item_type="journalArticle",
        doi=None,
        url=None,
        abstract=None,
        date_added=None,
        date_modified=None,
    )
    kwargs.update(overrides)
    return Paper(**kwargs)


# --- SyncCounts -------------------------------------------------------


def test_sync_counts_bump_created_and_updated_are_independent() -> None:
    counts = SyncCounts()

    counts.bump("Papers", "created")
    counts.bump("Papers", "created")
    counts.bump("Papers", "updated")

    assert counts.created["Papers"] == 2
    assert counts.updated["Papers"] == 1


def test_sync_counts_summary_line_includes_retired_only_for_papers() -> None:
    counts = SyncCounts()
    counts.bump("Papers", "created")
    counts.bump("Collections", "created")
    counts.retired.append("gone2019")

    summary = counts.summary_line()

    assert "Papers: 1 created, 0 updated, 1 retired" in summary
    assert "Collections: 1 created, 0 updated" in summary
    # Non-paper categories must not mention "retired".
    collections_part = [p for p in summary.split(" · ") if p.startswith("Collections")][0]
    assert "retired" not in collections_part


def test_sync_counts_summary_line_defaults_zero_for_untouched_categories() -> None:
    counts = SyncCounts()

    summary = counts.summary_line()

    assert "Papers: 0 created, 0 updated, 0 retired" in summary
    assert "Authors: 0 created, 0 updated" in summary
    assert "Keywords: 0 created, 0 updated" in summary


# --- path helpers -------------------------------------------------------


def test_paper_note_path(tmp_path: Path) -> None:
    path = paper_note_path(tmp_path, "smith2024widget")

    assert path == tmp_path / PAPERS_DIR / "smith2024widget.md"


def test_index_note_path_sanitizes_title(tmp_path: Path) -> None:
    path = index_note_path(tmp_path, "author", 'Smith, John "Jr"')

    assert path.parent == tmp_path / "Authors"
    assert path.name == "Smith, John -Jr-.md"


def test_existing_paper_citekeys_when_papers_dir_missing(tmp_path: Path) -> None:
    assert existing_paper_citekeys(tmp_path) == set()


def test_existing_paper_citekeys_when_papers_dir_empty(tmp_path: Path) -> None:
    (tmp_path / PAPERS_DIR).mkdir()

    assert existing_paper_citekeys(tmp_path) == set()


def test_existing_paper_citekeys_lists_stems_of_md_files(tmp_path: Path) -> None:
    papers_dir = tmp_path / PAPERS_DIR
    papers_dir.mkdir()
    (papers_dir / "alpha2020.md").write_text("---\n---\n", encoding="utf-8")
    (papers_dir / "beta2021.md").write_text("---\n---\n", encoding="utf-8")
    (papers_dir / "not-a-note.txt").write_text("ignore me", encoding="utf-8")

    assert existing_paper_citekeys(tmp_path) == {"alpha2020", "beta2021"}


# --- write_paper_note ---------------------------------------------------


def test_write_paper_note_creates_new_note_and_bumps_created(tmp_path: Path) -> None:
    counts = SyncCounts()
    paper = _paper()

    write_paper_note(tmp_path, paper, fields=["title", "citekey"], dry_run=False, counts=counts)

    path = paper_note_path(tmp_path, paper.citekey)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "citekey" in text
    assert counts.created["Papers"] == 1
    assert counts.updated.get("Papers", 0) == 0


def test_write_paper_note_dry_run_does_not_write_but_still_counts(tmp_path: Path) -> None:
    counts = SyncCounts()
    paper = _paper()

    write_paper_note(tmp_path, paper, fields=["title", "citekey"], dry_run=True, counts=counts)

    path = paper_note_path(tmp_path, paper.citekey)
    assert not path.exists()
    assert counts.created["Papers"] == 1


def test_write_paper_note_updates_existing_note_and_preserves_freeform_content(
    tmp_path: Path,
) -> None:
    counts = SyncCounts()
    paper = _paper(title="Original Title")
    write_paper_note(tmp_path, paper, fields=["title", "citekey"], dry_run=False, counts=counts)

    path = paper_note_path(tmp_path, paper.citekey)
    # Simulate a user adding their own freeform notes below the generated
    # blocks; the frontmatter diff/regeneration must leave this untouched.
    with path.open("a", encoding="utf-8") as f:
        f.write("\nMy own thoughts on this paper.\n")

    updated_paper = _paper(title="Updated Title")
    write_paper_note(
        tmp_path, updated_paper, fields=["title", "citekey"], dry_run=False, counts=counts
    )

    text = path.read_text(encoding="utf-8")
    assert "Updated Title" in text
    assert "Original Title" not in text
    assert "My own thoughts on this paper." in text
    assert counts.created["Papers"] == 1
    assert counts.updated["Papers"] == 1


# --- write_index_note ----------------------------------------------------


def test_write_index_note_creates_note_and_bumps_created(tmp_path: Path) -> None:
    counts = SyncCounts()

    write_index_note(tmp_path, "author", "Smith, John", None, dry_run=False, counts=counts)

    path = index_note_path(tmp_path, "author", "Smith, John")
    assert path.exists()
    assert "Smith, John" in path.read_text(encoding="utf-8")
    assert counts.created["Authors"] == 1


def test_write_index_note_dry_run_does_not_write_but_still_counts(tmp_path: Path) -> None:
    counts = SyncCounts()

    write_index_note(tmp_path, "keyword", "widgets", None, dry_run=True, counts=counts)

    path = index_note_path(tmp_path, "keyword", "widgets")
    assert not path.exists()
    assert counts.created["Keywords"] == 1


def test_write_index_note_existing_note_counts_as_updated(tmp_path: Path) -> None:
    counts = SyncCounts()
    write_index_note(tmp_path, "collection", "Root", None, dry_run=False, counts=counts)
    write_index_note(tmp_path, "collection", "Root", "Parent", dry_run=False, counts=counts)

    assert counts.created["Collections"] == 1
    assert counts.updated["Collections"] == 1
    path = index_note_path(tmp_path, "collection", "Root")
    assert 'parent: "Parent"' in path.read_text(encoding="utf-8")


# --- retire_note ----------------------------------------------------------


def test_retire_note_noop_when_note_does_not_exist(tmp_path: Path) -> None:
    counts = SyncCounts()

    retire_note(tmp_path, "ghost2020", dry_run=False, counts=counts)

    assert counts.retired == []
    assert not (tmp_path / TRASH_DIR).exists()


def test_retire_note_moves_existing_note_to_trash(tmp_path: Path) -> None:
    counts = SyncCounts()
    papers_dir = tmp_path / PAPERS_DIR
    papers_dir.mkdir()
    (papers_dir / "gone2019.md").write_text("---\ncitekey: gone2019\n---\n", encoding="utf-8")

    retire_note(tmp_path, "gone2019", dry_run=False, counts=counts)

    assert not (papers_dir / "gone2019.md").exists()
    assert (tmp_path / TRASH_DIR / "gone2019.md").exists()
    assert counts.retired == ["gone2019"]


def test_retire_note_dry_run_does_not_move_but_still_counts(tmp_path: Path) -> None:
    counts = SyncCounts()
    papers_dir = tmp_path / PAPERS_DIR
    papers_dir.mkdir()
    (papers_dir / "gone2019.md").write_text("---\ncitekey: gone2019\n---\n", encoding="utf-8")

    retire_note(tmp_path, "gone2019", dry_run=True, counts=counts)

    assert (papers_dir / "gone2019.md").exists()
    assert not (tmp_path / TRASH_DIR).exists()
    assert counts.retired == ["gone2019"]


def test_retire_note_handles_name_collision_in_trash(tmp_path: Path) -> None:
    counts = SyncCounts()
    papers_dir = tmp_path / PAPERS_DIR
    papers_dir.mkdir()
    (papers_dir / "dup2020.md").write_text("---\ncitekey: dup2020\n---\n", encoding="utf-8")
    trash_dir = tmp_path / TRASH_DIR
    trash_dir.mkdir()
    # A note with the same name is already sitting in the trash (retired on
    # an earlier run and never cleaned up).
    (trash_dir / "dup2020.md").write_text("already retired once", encoding="utf-8")

    retire_note(tmp_path, "dup2020", dry_run=False, counts=counts)

    assert not (papers_dir / "dup2020.md").exists()
    # The pre-existing trash file must survive untouched...
    assert (trash_dir / "dup2020.md").read_text(encoding="utf-8") == "already retired once"
    # ...and the newly retired note must land under a distinct name rather
    # than overwriting it.
    other_files = [p for p in trash_dir.glob("dup2020-*.md")]
    assert len(other_files) == 1
    assert counts.retired == ["dup2020"]
