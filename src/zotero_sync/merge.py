"""3-way merge for collections/tags conflict resolution (#25's design,
implemented in #31): reconciles independent edits made on the vault side and
the Zotero side since the last-synced snapshot."""

from __future__ import annotations

import difflib

# Chosen empirically (#25): tight enough that "Research" and "Research Notes"
# don't match each other, loose enough to catch a dropped/transposed letter.
TYPO_MATCH_CUTOFF = 0.8


def three_way_merge(snapshot: set[str], vault: set[str], zotero: set[str]) -> set[str]:
    """Git-style 3-way merge over a set of names/tags. For each element seen
    anywhere across the three sets:

    - New (absent from snapshot): kept if either side added it (union).
    - Known (present in snapshot): kept only if *both* sides still have it.
      Removed on one side while merely left untouched on the other still
      counts as a removal (propagate); removed on one side while the other
      re-added or kept it also drops it — removal wins, the sole conflict
      tie-break #25 settled on.
    """
    result: set[str] = set()
    for elem in snapshot | vault | zotero:
        in_snapshot = elem in snapshot
        in_vault = elem in vault
        in_zotero = elem in zotero
        if not in_snapshot:
            if in_vault or in_zotero:
                result.add(elem)
        elif in_vault and in_zotero:
            result.add(elem)
    return result


def find_close_match(
    name: str, candidates: list[str], cutoff: float = TYPO_MATCH_CUTOFF
) -> str | None:
    """Returns the closest existing name/tag if `name` looks like a typo of
    one of `candidates`, else None. Used to tell "the user meant an existing
    collection/tag but fat-fingered it" apart from "the user meant a
    genuinely new one" (#25's decision)."""
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None
