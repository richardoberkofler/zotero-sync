from __future__ import annotations

import argparse
import sys
from pathlib import Path

from zotero_sync import sync
from zotero_sync.config import apply_overrides, config_path, load_or_init_config
from zotero_sync.errors import ZoteroSyncError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zotero-sync",
        description="Sync a Zotero library into an Obsidian vault as an interconnected note graph.",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Path to the Obsidian vault (default: current directory).",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Restrict the sync to one Zotero collection (default: whole library).",
    )
    parser.add_argument(
        "--include-auto-tags",
        dest="include_auto_tags",
        action="store_true",
        default=None,
        help="Include Zotero's automatically-derived tags in keyword index notes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    vault_path = (args.vault or Path.cwd()).resolve()

    try:
        config, generated = load_or_init_config(vault_path)
        if generated:
            print(f"No config found — wrote defaults to {config_path(vault_path)}")
        config = apply_overrides(
            config,
            collection=args.collection,
            include_auto_tags=args.include_auto_tags,
            dry_run=args.dry_run,
        )

        counts = sync.run(config)
    except ZoteroSyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    label = "Would sync" if args.dry_run else "Synced"
    print(f"{label}: {counts.summary_line()}")
    for citekey in counts.retired:
        print(f"  retired: {citekey}")
    for error in counts.errors:
        print(f"  error: {error}")

    return 1 if counts.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
