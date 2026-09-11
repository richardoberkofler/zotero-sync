"""Covers #25/#31: the 3-way merge algorithm and the typo-check helper it's
paired with, tested in isolation from sync.py's orchestration."""

from __future__ import annotations

from zotero_sync.merge import find_close_match, three_way_merge


def test_three_way_merge_unchanged_stays():
    assert three_way_merge({"A"}, {"A"}, {"A"}) == {"A"}


def test_three_way_merge_added_in_vault_only_propagates():
    assert three_way_merge(set(), {"A"}, set()) == {"A"}


def test_three_way_merge_added_in_zotero_only_propagates():
    assert three_way_merge(set(), set(), {"A"}) == {"A"}


def test_three_way_merge_added_on_both_unions():
    assert three_way_merge(set(), {"A"}, {"B"}) == {"A", "B"}


def test_three_way_merge_removed_in_vault_untouched_in_zotero_propagates_removal():
    assert three_way_merge({"A"}, set(), {"A"}) == set()


def test_three_way_merge_removed_in_zotero_untouched_in_vault_propagates_removal():
    assert three_way_merge({"A"}, {"A"}, set()) == set()


def test_three_way_merge_removed_on_both_stays_removed():
    assert three_way_merge({"A"}, set(), set()) == set()


def test_three_way_merge_removed_on_one_side_kept_on_other_removal_wins():
    # #25's sole conflict tie-break: even though one side actively kept it,
    # the other side's removal takes precedence.
    assert three_way_merge({"A"}, set(), {"A"}) == set()
    assert three_way_merge({"A"}, {"A"}, set()) == set()


def test_three_way_merge_combines_multiple_elements_independently():
    snapshot = {"kept", "vault-removes", "zotero-removes", "both-remove"}
    vault = {"kept", "zotero-removes", "vault-adds"}
    zotero = {"kept", "vault-removes", "zotero-adds"}

    result = three_way_merge(snapshot, vault, zotero)

    assert result == {"kept", "vault-adds", "zotero-adds"}


def test_find_close_match_returns_the_likely_typo_source():
    assert find_close_match("Reserch", ["Research", "Teaching"]) == "Research"


def test_find_close_match_returns_none_for_a_genuinely_new_name():
    assert find_close_match("Astrophysics", ["Research", "Teaching"]) is None


def test_find_close_match_returns_none_for_empty_candidates():
    assert find_close_match("Research", []) is None
