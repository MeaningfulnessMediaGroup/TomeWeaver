"""Additional tests for Phase 3 prose lint (lexicon scope, locale)."""

import json

import pytest

from spell_check import (
    OfflineSpellChecker,
    add_user_lexicon_word,
    collect_story_lexicon,
    global_lexicon_path,
    load_merged_user_lexicon,
    load_user_lexicon_file,
    resolve_lexicon_save_path,
    story_lexicon_path,
)


def test_british_locale_accepts_colour():
    checker = OfflineSpellChecker(locale="british")
    assert checker.is_correct("colour")
    assert not checker.is_correct("color")
    assert checker.suggestions("color") == ["colour"]


def test_american_locale_flags_colour():
    checker = OfflineSpellChecker(locale="american")
    assert checker.is_correct("color")
    assert not checker.is_correct("colour")
    assert checker.suggestions("colour") == ["color"]


def test_both_locale_accepts_either_spelling():
    checker = OfflineSpellChecker(locale="both")
    assert checker.is_correct("color")
    assert checker.is_correct("colour")
    assert checker.scan_text("The gray colour was honor.") == []


def test_merged_user_lexicon_layers(tmp_path, monkeypatch):
    from config import ENGINE_CONFIG

    library = tmp_path / "library"
    library.mkdir()
    universe = library / "MyUniverse"
    universe.mkdir()
    (universe / "master_setup.json").write_text("{}", encoding="utf-8")
    story = universe / "ThreadA"
    story.mkdir()

    monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(library))

    save_path = global_lexicon_path()
    save_path.write_text(json.dumps({"words": ["globalword"]}), encoding="utf-8")
    (universe / "spelling_lexicon.json").write_text(
        json.dumps({"words": ["universeword"]}), encoding="utf-8"
    )
    (story / "spelling_lexicon.json").write_text(
        json.dumps({"words": ["storyword"]}), encoding="utf-8"
    )

    class FakeEngine:
        adv_dir = story
        setup_data = {}
        master_setup_data = {"universe_title": "My Universe"}
        memory = {"character_ledger": {"local": {}, "global": {"Star King": {}}}}
        history = []

    merged = load_merged_user_lexicon(FakeEngine())
    assert "globalword" in merged
    assert "universeword" in merged
    assert "storyword" in merged

    rag = collect_story_lexicon(FakeEngine())
    assert "star" in rag
    assert "king" in rag


def test_custom_dictionary_scope_global(tmp_path, monkeypatch):
    from config import ENGINE_CONFIG

    story = tmp_path / "story"
    story.mkdir()
    monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(tmp_path))
    monkeypatch.setitem(ENGINE_CONFIG, "custom_dictionary_scope", "global")

    class FakeEngine:
        adv_dir = story

    add_user_lexicon_word(FakeEngine(), "NeonBasin")
    assert "neonbasin" in load_user_lexicon_file(global_lexicon_path())
    assert "neonbasin" not in load_user_lexicon_file(story_lexicon_path(story))


def test_custom_dictionary_scope_universe(tmp_path, monkeypatch):
    from config import ENGINE_CONFIG

    universe = tmp_path / "U"
    universe.mkdir()
    (universe / "master_setup.json").write_text("{}", encoding="utf-8")
    story = universe / "S"
    story.mkdir()
    monkeypatch.setitem(ENGINE_CONFIG, "custom_dictionary_scope", "universe")

    class FakeEngine:
        adv_dir = story

    path = resolve_lexicon_save_path(FakeEngine())
    assert path == universe / "spelling_lexicon.json"
    add_user_lexicon_word(FakeEngine(), "Shardfall")
    assert "shardfall" in load_user_lexicon_file(path)


def test_add_ignored_word_uses_scope_and_suppresses_flag(tmp_path, monkeypatch):
    from config import ENGINE_CONFIG
    from spell_check import (
        SpellCheckService,
        add_ignored_word,
        load_lexicon_document,
    )

    universe = tmp_path / "U"
    universe.mkdir()
    (universe / "master_setup.json").write_text("{}", encoding="utf-8")
    story = universe / "S"
    story.mkdir()
    monkeypatch.setitem(ENGINE_CONFIG, "custom_dictionary_scope", "universe")

    class FakeEngine:
        adv_dir = story

    add_ignored_word(FakeEngine(), "Kaelen")
    doc = load_lexicon_document(universe / "spelling_lexicon.json")
    assert "kaelen" in doc["ignored"]
    assert "kaelen" not in doc["words"]

    service = SpellCheckService()
    issues = service.scan_prose(FakeEngine(), "Kaelen waited.", grammar=False)
    assert issues == []


def test_add_word_preserves_ignored_list(tmp_path):
    from spell_check import add_user_lexicon_word, load_lexicon_document, story_lexicon_path

    adv_dir = tmp_path / "adv"
    adv_dir.mkdir()
    path = story_lexicon_path(adv_dir)
    path.write_text(
        json.dumps({"ignored": ["kaelen"], "words": ["existing"]}),
        encoding="utf-8",
    )
    add_user_lexicon_word(adv_dir, "NeonBasin")
    doc = load_lexicon_document(path)
    assert "kaelen" in doc["ignored"]
    assert "neonbasin" in doc["words"]
    assert "existing" in doc["words"]


def test_grammar_ignore_filters_scan(tmp_path, monkeypatch):
    from config import ENGINE_CONFIG
    from spell_check import SpellCheckService, add_ignored_grammar

    story = tmp_path / "story"
    story.mkdir()
    monkeypatch.setitem(ENGINE_CONFIG, "custom_dictionary_scope", "story")

    class FakeEngine:
        adv_dir = story

    text = "He don't know teh way."
    service = SpellCheckService()
    before = service.scan_prose(FakeEngine(), text, grammar=True)
    grammar_hits = [i for i in before if i.get("kind") == "grammar"]
    assert grammar_hits

    add_ignored_grammar(FakeEngine(), grammar_hits[0], text)
    after = service.scan_prose(FakeEngine(), text, grammar=True)
    ignored_keys = {
        (i.get("rule_id"), text[i["start"] : i["end"]].lower())
        for i in grammar_hits
    }
    for issue in after:
        if issue.get("kind") != "grammar":
            continue
        key = (issue.get("rule_id"), text[issue["start"] : issue["end"]].lower())
        assert key not in ignored_keys
