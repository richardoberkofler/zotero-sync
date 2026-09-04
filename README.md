# zotero-sync

Sync a [Zotero](https://www.zotero.org/) library into an [Obsidian](https://obsidian.md/) vault as an interconnected note graph — one note per paper, plus index notes for collections, authors, and keywords, all cross-linked.

## How it works

`zotero-sync` reads directly from a running Zotero instance:

- **Zotero Local API** (`http://127.0.0.1:23119/api`) for item metadata, collections, and tags.
- **Better BibTeX**'s JSON-RPC endpoint for citation keys (the one fact BBT is authoritative for).
- A temporary copy of `zotero.sqlite` for PDF annotations/highlights, since these aren't exposed by either API.

For every top-level bibliographic item it writes a Markdown note under `Papers/<citekey>.md` with frontmatter (title, authors, year, DOI, tags, etc.) and any highlighted annotations, and keeps index notes for collections up to date. Papers removed from Zotero (or from the synced collection) are moved to `.trash/` instead of being deleted outright. Notes are updated in place on re-sync, and existing edits below the generated frontmatter are preserved.

## Requirements

- Zotero, running locally, with:
  - Settings → Advanced → **"Allow other applications on this computer to communicate with Zotero"** enabled.
  - The [Better BibTeX](https://retorque.re/zotero-better-bibtex/) plugin installed (used for citation keys).
- Python ≥ 3.11

## Install

```sh
pip install -e .
```

## Usage

```sh
zotero-sync --vault /path/to/obsidian/vault
```

Run from inside the vault to sync to the current directory, or pass `--vault`. Other flags:

| Flag | Description |
| --- | --- |
| `--vault PATH` | Obsidian vault path (default: current directory) |
| `--collection NAME` | Restrict the sync to one Zotero collection (default: whole library) |
| `--include-auto-tags` | Include Zotero's automatically-derived tags in keyword index notes |
| `--dry-run` | Report what would change without writing anything |

The first run writes a `.zotero-sync.toml` config file into the vault with the same settings (plus a `frontmatter` option controlling which fields are written: `"slim"`, `"full"`, or an explicit list). CLI flags override the config file for a single run.

## Project layout

```
src/zotero_sync/
├── cli.py           entry point (`zotero-sync`)
├── config.py         .zotero-sync.toml loading/defaults
├── local_api.py       Zotero Local API client
├── bbt_client.py     Better BibTeX JSON-RPC client (citation keys)
├── annotations.py    zotero.sqlite copy + annotation extraction
├── sync.py            orchestrates a sync run
├── vault.py            note read/write, retire-on-delete
├── model.py            Paper / Annotation data model
├── filenames.py         filename sanitization
└── notes/               note templates (paper notes, index notes)
```
