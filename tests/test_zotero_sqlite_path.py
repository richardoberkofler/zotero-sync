from __future__ import annotations

from pathlib import Path

from zotero_sync.annotations import zotero_sqlite_path


def test_zotero_sqlite_path_uses_configured_dir_when_file_exists(tmp_path: Path) -> None:
    (tmp_path / "zotero.sqlite").write_bytes(b"")

    assert zotero_sqlite_path(tmp_path) == tmp_path / "zotero.sqlite"


def test_zotero_sqlite_path_returns_none_when_configured_dir_has_no_sqlite(
    tmp_path: Path,
) -> None:
    assert zotero_sqlite_path(tmp_path) is None
