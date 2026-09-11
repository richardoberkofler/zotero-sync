# zotero-sync

Sync a [Zotero](https://www.zotero.org/) library into an [Obsidian](https://obsidian.md/) vault as an interconnected Markdown note graph.

For each top-level Zotero reference, `zotero-sync` writes `Papers/<citekey>.md`, updates generated metadata/links/annotation blocks on every run, and preserves your freeform notes below those generated blocks.

## What it syncs

- **Reference notes**: one note per bibliographic item, keyed by Better BibTeX citekey.
- **Collection index notes**: regenerated under `Collections/`, including parent/ancestor links for nested collections.
- **Links in paper notes**:
  - `Collections: [[...]]`
  - `Authors: [[...]]`
  - `Keywords: [[...]]`
  - Author/keyword index notes are **not** generated.
- **Annotations** from PDFs in Zotero: highlight, underline, note, and image annotations.

If a paper disappears from the synced scope, its note is moved to `.trash/` instead of being deleted.

## Data sources and modes

`zotero-sync` always uses:

- **Better BibTeX JSON-RPC** for citekeys.
- A temporary copy of **`zotero.sqlite`** for annotations.

For Zotero metadata (items, collections, tags), it supports:

- **`mode = "local"`** (default): reads from Zotero Local API (`http://127.0.0.1:23119/api`), no write-back to Zotero.
- **`mode = "web"`**: reads from Zotero Web API (`https://api.zotero.org`) and writes merged collection/tag edits back to Zotero.

## Requirements

- Python >= 3.11
- Zotero desktop installed and run at least once
- Better BibTeX installed in Zotero
- For local mode: Zotero running with Settings → Advanced → **Allow other applications on this computer to communicate with Zotero**
- For web mode: Zotero API key + library id/type

## Install

```sh
pip install -e .
```

## Usage

```sh
zotero-sync --vault /path/to/obsidian/vault
```

Run inside the vault (or pass `--vault`) and optionally:

| Flag | Description |
| --- | --- |
| `--vault PATH` | Vault path (default: current directory) |
| `--collection NAME` | Sync only one Zotero collection |
| `--include-auto-tags` | Include Zotero automatic tags |
| `--dry-run` | Show what would change without writing files or web updates |

### First run behavior

- On first run, `.zotero-sync.toml` is created in the vault.
- In an interactive terminal, a setup wizard asks for local vs web mode.
- If web mode is selected, `.env` credentials are written and verified.
- `.env` and `.zotero-sync-state.json` are added to `.gitignore` as a safety net.

### Config

Main settings in `.zotero-sync.toml`:

- `collection`
- `include_auto_tags`
- `frontmatter` (`"slim"`, `"full"`, or explicit field list)
- `zotero_dir` (optional Zotero data dir override)
- `mode` (`"local"` or `"web"`)

CLI flags override config for a single run.

In web mode, a state snapshot is stored in `.zotero-sync-state.json` to track last-synced versions and support safe merge/write-back of collections and tags.

## Notes on scope

- Retire-to-`.trash/` runs only for full-library syncs (not `--collection` scoped runs).
- Collection/tag write-back to Zotero happens only in web mode.

## Project layout

```
src/zotero_sync/
├── cli.py          CLI entrypoint and first-run onboarding gate
├── onboarding.py   interactive first-run setup
├── config.py       .zotero-sync.toml/.env loading and defaults
├── local_api.py    Zotero Local API read client
├── web_api.py      Zotero Web API read/write client
├── bbt_client.py   Better BibTeX JSON-RPC client
├── annotations.py  zotero.sqlite discovery/copy + annotation extraction
├── sync.py         sync orchestration + merge/reconcile logic
├── sync_state.py   web-mode sync snapshot state file
├── vault.py        paper/index note writes and retire-to-trash behavior
├── model.py        data model types
└── notes/          note rendering/parsing helpers
```
