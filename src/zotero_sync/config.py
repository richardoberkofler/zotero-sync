from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from zotero_sync.errors import ZoteroSyncError

CONFIG_FILENAME = ".zotero-sync.toml"

DEFAULT_CONFIG_TEMPLATE = """\
# zotero-sync configuration.
# Generated automatically because no config file existed yet. Edit freely —
# these are the same settings available as CLI flags; flags override this
# file for a single run.

# Restrict syncing to one Zotero collection (by name). Leave commented out
# to sync the whole library.
# collection = "My Collection"

# Include Zotero's automatically-derived tags (as opposed to ones you added
# manually) in keyword index notes. Off by default since automatic tags are
# often noisy and uncurated.
include_auto_tags = false

# Frontmatter field set for paper notes: "slim" (title/authors/year/type/
# doi/url/citekey/collections/tags/date-added/date-modified/abstract),
# "full" (adds volume/issue/pages/container-title/publisher/isbn/issn), or
# an explicit array of field names, e.g. ["title", "authors", "citekey"].
frontmatter = "slim"
"""

FRONTMATTER_SLIM = [
    "title",
    "authors",
    "year",
    "type",
    "doi",
    "url",
    "citekey",
    "collections",
    "tags",
    "date-added",
    "date-modified",
    "abstract",
]

FRONTMATTER_FULL = FRONTMATTER_SLIM + [
    "volume",
    "issue",
    "pages",
    "container-title",
    "publisher",
    "isbn",
    "issn",
]


@dataclass
class Config:
    vault_path: Path
    collection: str | None = None
    include_auto_tags: bool = False
    frontmatter: str | list[str] = "slim"
    dry_run: bool = False

    @property
    def frontmatter_fields(self) -> list[str]:
        if self.frontmatter == "slim":
            return FRONTMATTER_SLIM
        if self.frontmatter == "full":
            return FRONTMATTER_FULL
        if isinstance(self.frontmatter, list):
            return self.frontmatter
        raise ZoteroSyncError(
            f"Invalid frontmatter setting {self.frontmatter!r} — expected "
            '"slim", "full", or a list of field names.'
        )



def config_path(vault_path: Path) -> Path:
    return vault_path / CONFIG_FILENAME


def load_or_init_config(vault_path: Path) -> tuple[Config, bool]:
    """Returns (config, was_generated)."""
    path = config_path(vault_path)
    generated = False
    if not path.exists():
        path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        generated = True

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return (
        Config(
            vault_path=vault_path,
            collection=data.get("collection"),
            include_auto_tags=bool(data.get("include_auto_tags", False)),
            frontmatter=data.get("frontmatter", "slim"),
        ),
        generated,
    )


def apply_overrides(
    config: Config,
    *,
    collection: str | None,
    include_auto_tags: bool | None,
    dry_run: bool,
) -> Config:
    if collection is not None:
        config.collection = collection
    if include_auto_tags is not None:
        config.include_auto_tags = include_auto_tags
    config.dry_run = dry_run
    return config
