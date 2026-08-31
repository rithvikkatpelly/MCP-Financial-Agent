"""The shared series catalog: precise resolve, looser search."""

import catalog


def test_resolve_is_precise_about_core_vs_headline():
    assert catalog.resolve("give me core cpi from 2019 to 2024") == ["CPILFESL"]
    assert catalog.resolve("headline cpi since 2020") == ["CPIAUCSL"]


def test_resolve_keeps_both_when_the_user_contrasts_them():
    got = set(catalog.resolve("compare core inflation and headline cpi"))
    assert got == {"CPILFESL", "CPIAUCSL"}


def test_resolve_returns_multiple_in_first_seen_order():
    assert catalog.resolve("unemployment vs the fed funds rate") == ["UNRATE", "FEDFUNDS"]


def test_resolve_ignores_loose_words_that_are_only_search_terms():
    # "borrowing" is a search term for FEDFUNDS, not an alias — an agent
    # shouldn't act on it directly, it should search first.
    assert catalog.resolve("how expensive has borrowing gotten") == []


def test_search_ranks_the_right_series_first_for_a_loose_query():
    assert catalog.search("how expensive has borrowing gotten")[0] == "FEDFUNDS"


def test_search_never_returns_the_injection_probe_series():
    for q in ("inflation", "test", "series", "index"):
        assert "INJTEST" not in catalog.search(q)


def test_every_catalog_entry_is_self_consistent():
    for sid, s in catalog.CATALOG.items():
        assert s.id == sid
        assert s.aliases  # every series is nameable
        assert s.notes
