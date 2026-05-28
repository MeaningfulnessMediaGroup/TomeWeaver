"""Tests for offline WordNet synonyms."""

from synonyms import fetch_synonyms, synonyms_enabled


class _FakeLemma:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _FakeSynset:
    def __init__(self, names):
        self._names = names

    def lemmas(self):
        return [_FakeLemma(n) for n in self._names]


def test_synonyms_enabled_reads_config(monkeypatch):
    from config import ENGINE_CONFIG

    monkeypatch.setitem(ENGINE_CONFIG, "offline_synonyms", True)
    assert synonyms_enabled() is True
    monkeypatch.setitem(ENGINE_CONFIG, "offline_synonyms", False)
    assert synonyms_enabled() is False


def test_fetch_synonyms_dedupes_and_excludes_source(monkeypatch):
    monkeypatch.setattr("synonyms._ensure_wordnet", lambda: True)

    def fake_synsets(lemma):
        if lemma == "walk":
            return [
                _FakeSynset(["walk", "stroll", "walk"]),
                _FakeSynset(["hike", "stroll"]),
            ]
        return []

    monkeypatch.setattr("synonyms._synsets_for_word", fake_synsets)
    result = fetch_synonyms("walk", limit=8)
    assert result == ["stroll", "hike"]
    assert "walk" not in [r.lower() for r in result]


def test_fetch_synonyms_respects_limit(monkeypatch):
    monkeypatch.setattr("synonyms._ensure_wordnet", lambda: True)
    monkeypatch.setattr(
        "synonyms._synsets_for_word",
        lambda lemma: [_FakeSynset([f"word{i}" for i in range(12)])],
    )
    assert len(fetch_synonyms("test", limit=5)) == 5


def test_fetch_synonyms_skips_short_and_numeric():
    assert fetch_synonyms("a") == []
    assert fetch_synonyms("123") == []
