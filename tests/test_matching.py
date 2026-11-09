"""The name matching that pairs an output channel with its virtual input
channel for the full-travel cover commands."""
from __future__ import annotations

from custom_components.innoxel import _fuzzy_match, _normalize_tokens


def test_tokens_are_normalised():
    assert _normalize_tokens("Büro OG Store") == ["buro", "og", "store"]
    assert _normalize_tokens("Küche1") == ["kuche", "1"]
    assert _normalize_tokens("Zimmer 2b") == ["zimmer", "2", "b"]
    assert _normalize_tokens("Wohnen (Süd)") == ["wohnen", "sud"]
    assert _normalize_tokens("") == []


def test_exact_and_partial_matches():
    assert _fuzzy_match("Büro OG Store", "Buero OG Store") < 1.0  # "buro" vs "buero" is only a prefix match
    assert _fuzzy_match("Büro OG Store", "Büro OG Store") == 1.0
    assert _fuzzy_match("Kueche Store", "Kueche Storen") == 0.9  # one exact token, one prefix match
    assert _fuzzy_match("Bad", "Bad OG") == 1.0  # every output token found
    assert _fuzzy_match("Bad OG", "Bad") == 0.5
    assert _fuzzy_match("Garage", "Keller") == 0.0
    assert _fuzzy_match("", "Keller") == 0.0
