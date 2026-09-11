from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from zotero_sync.errors import ZoteroSyncError
from zotero_sync.sync_state import STATE_FILENAME

CONFIG_FILENAME = ".zotero-sync.toml"
ENV_FILENAME = ".env"

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
# doi/url/citekey/collections/tags/date-added/date-modified),
# "full" (adds volume/issue/pages/container-title/publisher/isbn/issn), or
# an explicit array of field names, e.g. ["title", "authors", "citekey"].
# The abstract is rendered as its own block in the note body, not frontmatter.
frontmatter = "slim"

# Directory containing zotero.sqlite (Zotero's data directory, not the
# storage/ subfolder). Leave commented out to use Zotero's default location
# for this OS. Only needed if Zotero is configured to use a custom data
# directory.
# zotero_dir = "/path/to/Zotero"

# "local" (default): read-only, via Zotero's local HTTP API — vault edits
# to collections/tags never flow back to Zotero.
# "web": 2-way, via the Zotero web API (api.zotero.org) — reads AND writes
# go through your Zotero account, so it needs credentials. Setting this
# to "web" writes a .env template on the next run for you to fill in.
mode = "local"
"""

DEFAULT_ENV_TEMPLATE = """\
# zotero-sync web-mode credentials.
# Generated automatically because mode = "web" is set but no .env file
# existed yet. Get an API key at https://www.zotero.org/settings/keys
# (needs read/write access to the library below), fill these in, and
# re-run. This file is listed in .gitignore — keep it that way if this
# vault is (or might become) a git repository, since it holds a secret.

# API key with write access to the library below.
ZOTERO_API_KEY=

# Numeric library id — your personal library id, or a group library id.
ZOTERO_LIBRARY_ID=

# "user" for your personal library, "group" for a group library.
ZOTERO_LIBRARY_TYPE=user
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
    zotero_dir: Path | None = None
    dry_run: bool = False
    mode: str = "local"
    web_api_key: str | None = None
    web_library_id: str | None = None
    web_library_type: str | None = None
    # Not user-configurable (no TOML/.env setting) — exists purely as a
    # test seam so sync.run()'s web_api.configure() call can point at a
    # stub server instead of api.zotero.org, mirroring how local_api.py's
    # BASE_URL is monkeypatched directly in tests.
    web_api_root: str = "https://api.zotero.org"

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


def env_path(vault_path: Path) -> Path:
    return vault_path / ENV_FILENAME


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _ensure_gitignored(vault_path: Path, *entries: str) -> None:
    """Best-effort safety net for the secret in .env (see #28's design
    decision): if the vault turns out to be a git repo, don't let these
    local-only files get committed by default."""
    path = vault_path / ".gitignore"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    missing = [e for e in entries if e not in existing]
    if not missing:
        return
    with path.open("a", encoding="utf-8") as f:
        if existing and existing[-1] != "":
            f.write("\n")
        for entry in missing:
            f.write(f"{entry}\n")


def _load_web_credentials(vault_path: Path) -> tuple[str, str, str]:
    path = env_path(vault_path)
    if not path.exists():
        path.write_text(DEFAULT_ENV_TEMPLATE, encoding="utf-8")
        _ensure_gitignored(vault_path, ENV_FILENAME, STATE_FILENAME)
        raise ZoteroSyncError(
            f'mode = "web" needs Zotero credentials — wrote a template to {path}. '
            "Fill it in and re-run."
        )

    values = _parse_env(path.read_text(encoding="utf-8"))
    api_key = values.get("ZOTERO_API_KEY", "")
    library_id = values.get("ZOTERO_LIBRARY_ID", "")
    library_type = values.get("ZOTERO_LIBRARY_TYPE", "")
    missing = [
        name
        for name, value in (
            ("ZOTERO_API_KEY", api_key),
            ("ZOTERO_LIBRARY_ID", library_id),
            ("ZOTERO_LIBRARY_TYPE", library_type),
        )
        if not value
    ]
    if missing:
        raise ZoteroSyncError(f"{path} is missing: {', '.join(missing)} — fill in and re-run.")

    _ensure_gitignored(vault_path, ENV_FILENAME, STATE_FILENAME)
    return api_key, library_id, library_type


def load_or_init_config(vault_path: Path) -> tuple[Config, bool]:
    """Returns (config, was_generated)."""
    path = config_path(vault_path)
    generated = False
    if not path.exists():
        path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        generated = True

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ZoteroSyncError(f"Failed to parse {path}: {exc}") from exc

    zotero_dir = data.get("zotero_dir")
    mode = data.get("mode", "local")

    web_api_key = web_library_id = web_library_type = None
    if mode == "web":
        web_api_key, web_library_id, web_library_type = _load_web_credentials(vault_path)

    return (
        Config(
            vault_path=vault_path,
            collection=data.get("collection"),
            include_auto_tags=bool(data.get("include_auto_tags", False)),
            frontmatter=data.get("frontmatter", "slim"),
            zotero_dir=Path(zotero_dir) if zotero_dir is not None else None,
            mode=mode,
            web_api_key=web_api_key,
            web_library_id=web_library_id,
            web_library_type=web_library_type,
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
    # Unlike the other flags, dry_run has no config-file counterpart to fall
    # back to, so it's always taken from the CLI (argparse defaults it to
    # False rather than None) instead of being guarded by an is-None check.
    config.dry_run = dry_run
    return config
