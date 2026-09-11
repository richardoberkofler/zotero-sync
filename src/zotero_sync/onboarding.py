"""Interactive first-run setup for a new vault: choose local vs. web mode
and, for web, collect Zotero API credentials — mirroring
scripts/wizard-zotero-write-key.sh's guided-prompt UX, but shipped as part
of the CLI itself (Python, cross-platform, no bash) since this one runs for
every end user, not just this repo's own contributors.

Only ever invoked by cli.main() when both are true: no .zotero-sync.toml
exists yet in the vault (is_first_run()) and stdin is a real terminal. A
non-interactive first run (CI, scripts, piped input) is untouched — it
still gets config.py's existing silent local-mode default + .env template
generation."""

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Callable

from zotero_sync import web_api
from zotero_sync.config import (
    DEFAULT_CONFIG_TEMPLATE,
    ENV_FILENAME,
    _ensure_gitignored,
    config_path,
    env_path,
)
from zotero_sync.errors import ZoteroSyncError
from zotero_sync.sync_state import STATE_FILENAME

Ask = Callable[[str], str]


def is_first_run(vault_path: Path) -> bool:
    return not config_path(vault_path).exists()


def run(vault_path: Path, *, ask: Ask = input, ask_secret: Ask = getpass.getpass) -> None:
    """Writes .zotero-sync.toml (and, for web mode, .env) so the
    load_or_init_config() call right after this in cli.main() just reads
    what got written here instead of generating its own local-mode
    default."""
    print("Welcome to zotero-sync! Setting up this vault.\n")
    print("Sync mode:")
    print("  1) local (default) — read-only; vault edits never reach Zotero")
    print("  2) web — 2-way sync; vault edits to collections/tags flow back")
    print("     to Zotero too. Needs a Zotero API key.")
    choice = ask("Choose [1/2, Enter = 1]: ").strip()
    mode = "web" if choice == "2" else "local"

    config_path(vault_path).write_text(
        DEFAULT_CONFIG_TEMPLATE.replace('mode = "local"', f'mode = "{mode}"'),
        encoding="utf-8",
    )
    print(f'Wrote {config_path(vault_path)} (mode = "{mode}")')

    if mode == "web":
        _collect_web_credentials(vault_path, ask=ask, ask_secret=ask_secret)


def _collect_web_credentials(vault_path: Path, *, ask: Ask, ask_secret: Ask) -> None:
    print()
    print("Get a Zotero API key at https://www.zotero.org/settings/keys")
    print("  - Grant it read/write access to the library you want to sync.")
    api_key = ask_secret("Zotero API key (input hidden): ").strip()
    library_id = ask("Zotero library id (the number in the library's URL): ").strip()
    library_type = ""
    while library_type not in ("user", "group"):
        library_type = ask('Library type — "user" (personal) or "group" [user]: ').strip() or "user"

    env_path(vault_path).write_text(
        f"ZOTERO_API_KEY={api_key}\n"
        f"ZOTERO_LIBRARY_ID={library_id}\n"
        f"ZOTERO_LIBRARY_TYPE={library_type}\n",
        encoding="utf-8",
    )
    _ensure_gitignored(vault_path, ENV_FILENAME, STATE_FILENAME)
    print(f"Wrote {env_path(vault_path)}")

    print("Verifying the key against Zotero...")
    if _verify_credentials(library_id, library_type, api_key):
        print("  key verified, library reachable.")
    else:
        print("  Couldn't verify yet — fix the values in .env and just re-run zotero-sync.")


def _verify_credentials(library_id: str, library_type: str, api_key: str) -> bool:
    try:
        web_api.configure(library_id, library_type, api_key)
        web_api.list_collections()
    except ZoteroSyncError:
        return False
    return True
