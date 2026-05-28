"""Offline synonym lookup for prose lint (WordNet via NLTK).

Phase 3 optional feature: right-click menus call :func:`fetch_synonyms` lazily
so there is no background scanning or UI clutter. WordNet data is loaded once
per process; if the corpus is missing, NLTK may download it on first use (~30MB).
"""

from __future__ import annotations

# Set after first successful WordNet probe; avoids repeated import/download work.
_WORDNET_READY = False
# Cached failure message when init/download fails (offline machine, bad install).
_WORDNET_ERROR = None


def synonyms_enabled():
    """True when **Offline Synonyms** is on in Prose Lint Settings."""
    from config import ENGINE_CONFIG

    return bool(ENGINE_CONFIG.get("offline_synonyms", False))


def wordnet_available():
    """Return True when WordNet data is loaded and usable."""
    return _ensure_wordnet()


def wordnet_error():
    """Last WordNet init error, if any (for empty-menu diagnostics)."""
    return _WORDNET_ERROR


def _ensure_wordnet():
    """Import NLTK WordNet once; download corpus if absent. Returns success flag."""
    global _WORDNET_READY, _WORDNET_ERROR
    if _WORDNET_READY:
        return True
    if _WORDNET_ERROR is not None:
        return False
    try:
        import nltk
        from nltk.corpus import wordnet as wn

        try:
            nltk.data.find("corpora/wordnet")
        except LookupError:
            # First run on a fresh install — needs network once, then cached locally.
            nltk.download("wordnet", quiet=True)
            try:
                nltk.download("omw-1.4", quiet=True)
            except Exception:
                pass  # OMW is optional; English WordNet alone is enough.
        wn.synsets("test")  # Probe load before marking ready.
        _WORDNET_READY = True
        return True
    except Exception as exc:
        _WORDNET_ERROR = str(exc)
        return False


def _synsets_for_word(lemma):
    """Thin wrapper so tests can monkeypatch WordNet lookups."""
    from nltk.corpus import wordnet as wn

    return wn.synsets(lemma)


def fetch_synonyms(word, limit=8):
    """Return up to *limit* synonym strings for *word* (offline WordNet).

    Skips single-character tokens, digits, and the source lemma. WordNet lemma
    names use underscores; we expose them as spaced prose (``take_off`` →
    ``take off``). Proper nouns and coinages usually return an empty list.
    """
    from spell_check import normalize_token

    token = normalize_token(word or "")
    if not token or len(token) < 2 or token.isdigit():
        return []
    if not _ensure_wordnet():
        return []

    lemma = token.lower()
    seen = {lemma}  # Never suggest the word the author already typed.
    results = []
    for syn in _synsets_for_word(lemma):
        for entry in syn.lemmas():
            name = entry.name().replace("_", " ")
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(name)
            if len(results) >= limit:
                return results
    return results
