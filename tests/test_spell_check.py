"""Tests for offline spell checking."""

import json

import pytest

from spell_check import (
    OfflineSpellChecker,
    add_user_lexicon_word,
    collect_story_lexicon,
    iter_words,
    load_user_lexicon,
)


def test_iter_words_skips_acronyms():
    words = [w for w, _, _ in iter_words("NASA landed near Kaelen")]
    assert "NASA" not in words
    assert "Kaelen" in words


def test_offline_spell_checker_flags_obvious_typo():
    checker = OfflineSpellChecker()
    issues = checker.scan_text("The teh door creaked open.")
    flagged = {issue["word"].lower() for issue in issues}
    assert "teh" in flagged


def test_custom_lexicon_accepts_story_names(tmp_path):
    adv_dir = tmp_path / "story"
    adv_dir.mkdir()
    add_user_lexicon_word(adv_dir, "Kaelen")

    checker = OfflineSpellChecker()
    checker.load_extra_words(load_user_lexicon(adv_dir))
    assert checker.is_correct("Kaelen")
    assert checker.scan_text("Kaelen waited.") == []


def test_collect_story_lexicon_from_engine(sandbox_engine):
    sandbox_engine.setup_data["main_character"] = "Lyra Moonwhisper"
    sandbox_engine.memory.setdefault("character_ledger", {})["local"] = {
        "Captain Vance": {"characteristics": {}, "ledger": [], "state": "active"},
    }
    lexicon = collect_story_lexicon(sandbox_engine)
    assert "lyra" in lexicon
    assert "moonwhisper" in lexicon
    assert "vance" in lexicon


def test_user_lexicon_persists(tmp_path):
    adv_dir = tmp_path / "adv"
    adv_dir.mkdir()
    add_user_lexicon_word(adv_dir, "NeonBasin")
    path = adv_dir / "spelling_lexicon.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "neonbasin" in data["words"]


def test_iter_words_ignores_surrounding_quotes():
    words = [w for w, _, _ in iter_words("'Yes, mister' 'Got it Alan',")]
    assert words == ["Yes", "mister", "Got", "it", "Alan"]
    assert "'Yes" not in words
    assert "Alan'" not in words


def test_plural_s_is_accepted_when_singular_known():
    checker = OfflineSpellChecker()
    assert checker.is_correct("availables")
    assert checker.scan_text("All are availables.") == []


@pytest.mark.parametrize(
    "plural",
    [
        "cats",
        "stories",
        "parties",
        "boxes",
        "churches",
        "dishes",
        "classes",
        "heroes",
        "bridges",
        "wolves",
    ],
)
def test_common_plural_patterns_accepted(plural):
    checker = OfflineSpellChecker()
    assert checker.is_correct(plural), f"{plural} should match a known singular stem"
    assert checker.scan_text(f"Many {plural} here.") == []


def test_singular_candidates_cover_basic_rules():
    from spell_check import singular_candidates

    assert "story" in singular_candidates("stories")
    assert "box" in singular_candidates("boxes")
    assert "church" in singular_candidates("churches")
    assert "cat" in singular_candidates("cats")
    assert "available" in singular_candidates("availables")


@pytest.mark.parametrize(
    "text",
    [
        "You're late.",
        "We're ready.",
        "They've gone.",
        "I don't know.",
        "It won't work.",
        "She's here.",
        "Let's go.",
        "We can't stay.",
        "He'd said so.",
        "You'll see.",
    ],
)
def test_common_contractions_accepted(text):
    checker = OfflineSpellChecker()
    assert checker.scan_text(text) == [], f"Unexpected flags in: {text!r}"


def test_contraction_expansion_lookup():
    from spell_check import contraction_expansions

    assert "you are" in contraction_expansions("you're")
    assert contraction_expansions("We're") == ()  # needs lower case
    assert "we are" in contraction_expansions("we're")


def test_scan_prose_combines_spelling_and_grammar():
    checker = OfflineSpellChecker()
    issues = checker.scan_prose("He don't know teh way.")
    kinds = {i.get("kind") for i in issues}
    assert "spelling" in kinds
    assert "grammar" in kinds


def test_add_to_lexicon_strips_quotes(tmp_path):
    adv_dir = tmp_path / "adv"
    adv_dir.mkdir()
    add_user_lexicon_word(adv_dir, "'Kaelen'")
    assert "kaelen" in load_user_lexicon(adv_dir)
