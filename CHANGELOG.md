# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-04

### Added

- Sync a Zotero library into an Obsidian vault as one Markdown note per paper, with frontmatter (title, authors, year, DOI, tags, etc.) and rendered annotations.
- Annotation extraction for highlight, note, image, and underline types, read from a temporary copy of `zotero.sqlite`.
- Collection index notes, cross-linked with paper notes.
- Citation keys sourced from Better BibTeX's JSON-RPC endpoint.
- Retire-on-delete: papers removed from Zotero (or from the synced collection) are moved to `.trash/` instead of being deleted outright.
- Skip-not-overwrite handling for case-insensitive citekey collisions (see `docs/adr/0002-citekey-collision-skip-not-overwrite.md`).
- `--vault`, `--collection`, `--include-auto-tags`, and `--dry-run` CLI flags; a `.zotero-sync.toml` config file written on first run and editable thereafter.
- `CONTEXT.md` domain glossary and `docs/adr/` architecture decision records.
- Unit and fixture-based integration test suite (fake Local API, fake Better BibTeX JSON-RPC, recorded `zotero.sqlite`).
- GitHub Actions CI (`windows-latest`, Python 3.11): lint (`ruff check`, `ruff format --check`) and test (`pytest`) on every push and PR to `master`.
