"""Offline spell checking for prose editors (no network)."""

from __future__ import annotations

import json
import re
import tkinter as tk
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

QUOTE_CHARS = "'\"‘’“”`"

IGNORE_WORDS = frozenset(
    {
        "i",
        "a",
        "ok",
        "etc",
        "vs",
        "ya",
        "nah",
        "hmm",
        "uh",
        "um",
        "mr",
        "ms",
        "dr",
        "st",
        "nd",
        "rd",
        "th",
    }
)

from grammar_lint import GRAMMAR_ERROR_TAG, is_noun_possessive, scan_grammar

_SPELL_TAG = "spell_error"

# American → British spelling pairs (common prose vocabulary).
_LOCALE_PAIRS = (
    ("color", "colour"),
    ("colored", "coloured"),
    ("honor", "honour"),
    ("honored", "honoured"),
    ("behavior", "behaviour"),
    ("favorite", "favourite"),
    ("favorites", "favourites"),
    ("center", "centre"),
    ("centers", "centres"),
    ("theater", "theatre"),
    ("theaters", "theatres"),
    ("meter", "metre"),
    ("meters", "metres"),
    ("liter", "litre"),
    ("liters", "litres"),
    ("defense", "defence"),
    ("offense", "offence"),
    ("license", "licence"),
    ("analyze", "analyse"),
    ("analyzed", "analysed"),
    ("organize", "organise"),
    ("organized", "organised"),
    ("recognize", "recognise"),
    ("recognized", "recognised"),
    ("traveling", "travelling"),
    ("traveled", "travelled"),
    ("jewelry", "jewellery"),
    ("gray", "grey"),
    ("catalog", "catalogue"),
    ("skeptic", "sceptic"),
    ("fulfill", "fulfil"),
    ("enrollment", "enrolment"),
    ("pajamas", "pyjamas"),
    ("aluminum", "aluminium"),
)
_AMERICAN_TO_BRITISH = {a: b for a, b in _LOCALE_PAIRS}
_BRITISH_TO_AMERICAN = {b: a for a, b in _LOCALE_PAIRS}
_BRITISH_FORMS = frozenset(_BRITISH_TO_AMERICAN.keys())
_AMERICAN_FORMS = frozenset(_AMERICAN_TO_BRITISH.keys())


def normalize_token(token):
    """Strip whitespace and surrounding quote characters from a token."""
    if not token:
        return ""
    return str(token).strip().strip(QUOTE_CHARS)


# Basic plural → singular stem rules (not full grammar). Each entry is
# (plural_suffix, singular_tail). Candidate stem = word[:-len(suffix)] + tail.
# Order: longer / more specific suffixes first; all matching rules are tried.
PLURAL_STEM_RULES = (
    ("ies", "y"),    # stories → story, parties → party
    ("ives", "ife"), # knives → knife
    ("ves", "f"),    # wolves → wolf, shelves → shelf (approx)
    ("ches", "ch"),  # churches → church
    ("shes", "sh"),  # dishes → dish
    ("sses", "ss"),  # classes → class, passes → pass
    ("xes", "x"),    # boxes → box
    ("zes", "z"),    # quizzes → quiz
    ("oes", "o"),    # heroes → hero, potatoes → potato
    ("es", ""),      # bridges → bridge, watches → watch
    ("s", ""),       # cats → cat, availables → available
)

# Skip naive -s stripping when the word already looks like a singular mass noun.
_S_SKIP_S_STRIP = frozenset({"ss", "us", "is", "as", "os"})

# Common contractions → one or more expanded forms (any match accepts the token).
# Covers ~90% of dialogue prose; not full grammar.
CONTRACTIONS = {
    "i'm": ("i am",),
    "you're": ("you are",),
    "we're": ("we are",),
    "they're": ("they are",),
    "you've": ("you have",),
    "we've": ("we have",),
    "they've": ("they have",),
    "i've": ("i have",),
    "you'll": ("you will",),
    "we'll": ("we will",),
    "they'll": ("they will",),
    "he'll": ("he will",),
    "she'll": ("she will",),
    "it'll": ("it will",),
    "that'll": ("that will",),
    "there'll": ("there will",),
    "i'll": ("i will",),
    "you'd": ("you would", "you had"),
    "we'd": ("we would", "we had"),
    "they'd": ("they would", "they had"),
    "he'd": ("he would", "he had"),
    "she'd": ("she would", "she had"),
    "it'd": ("it would", "it had"),
    "i'd": ("i would", "i had"),
    "that'd": ("that would", "that had"),
    "there'd": ("there would", "there had"),
    "he's": ("he is", "he has"),
    "she's": ("she is", "she has"),
    "it's": ("it is", "it has"),
    "that's": ("that is", "that has"),
    "there's": ("there is", "there has"),
    "here's": ("here is",),
    "what's": ("what is", "what has"),
    "who's": ("who is", "who has"),
    "where's": ("where is",),
    "when's": ("when is",),
    "how's": ("how is",),
    "why's": ("why is",),
    "let's": ("let us",),
    "don't": ("do not",),
    "doesn't": ("does not",),
    "didn't": ("did not",),
    "won't": ("will not",),
    "wouldn't": ("would not",),
    "couldn't": ("could not",),
    "shouldn't": ("should not",),
    "can't": ("can not",),
    "cannot": ("can not",),
    "isn't": ("is not",),
    "aren't": ("are not",),
    "wasn't": ("was not",),
    "weren't": ("were not",),
    "hasn't": ("has not",),
    "haven't": ("have not",),
    "hadn't": ("had not",),
    "mustn't": ("must not",),
    "needn't": ("need not",),
    "mightn't": ("might not",),
    "shan't": ("shall not",),
    "ain't": ("am not",),
    "y'all": ("you all",),
    "ma'am": ("madam",),
    "o'clock": ("of the clock",),
    "c'mon": ("come on",),
    "d'you": ("do you",),
    "'em": ("them",),
}


def normalize_apostrophe(text):
    return (text or "").replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")


def contraction_expansions(lower):
    """Return expansion phrases for a lowercased contraction token."""
    key = normalize_apostrophe(lower)
    return CONTRACTIONS.get(key, ())


def singular_candidates(lower):
    """Return possible singular forms for a lowercased token."""
    if not lower or len(lower) < 3:
        return ()

    candidates = []
    seen = set()

    def add(stem):
        stem = (stem or "").strip()
        if len(stem) < 2 or stem in seen:
            return
        seen.add(stem)
        candidates.append(stem)

    for suffix, tail in PLURAL_STEM_RULES:
        if not lower.endswith(suffix):
            continue
        if suffix == "s" and lower.endswith("ss"):
            continue
        if suffix == "s" and any(lower.endswith(end) for end in _S_SKIP_S_STRIP):
            continue
        if len(lower) <= len(suffix) + 1:
            continue
        add(lower[: -len(suffix)] + tail)

    return tuple(candidates)


def iter_words(text):
    """Yield (word, start_char, end_char) for spell-checkable tokens."""
    for match in WORD_RE.finditer(text or ""):
        word = match.group(0)
        if len(word) < 2 and word.lower() not in IGNORE_WORDS:
            continue
        if word.lower() in IGNORE_WORDS:
            continue
        if word.isupper() and len(word) > 1:
            continue
        yield word, match.start(), match.end()


def split_name_tokens(name):
    """Split entity names into likely spell-check tokens."""
    if not name:
        return []
    parts = re.split(r"[\s\-_/]+", str(name).strip())
    tokens = []
    for part in parts:
        part = part.strip("'\"")
        if not part:
            continue
        if len(part) >= 2:
            tokens.append(part)
        camel = re.sub(r"([a-z])([A-Z])", r"\1 \2", part)
        for piece in camel.split():
            if len(piece) >= 2:
                tokens.append(piece)
    return tokens


def collect_story_lexicon(engine):
    """Build allowlist from story setup, local+universe RAG, aliases, and turns."""
    words = set()
    _collect_setup_lexicon(words, getattr(engine, "setup_data", {}) or {})
    _collect_setup_lexicon(words, getattr(engine, "master_setup_data", {}) or {})
    _collect_memory_lexicon(words, getattr(engine, "memory", {}) or {})
    for turn in getattr(engine, "history", []) or []:
        words.update(split_name_tokens(turn.get("location", "")))
        words.update(split_name_tokens(turn.get("pov_character", "")))
    return {w.lower() for w in words if w}


def _collect_setup_lexicon(words, setup):
    if not isinstance(setup, dict):
        return
    for key in (
        "main_character",
        "title",
        "author",
        "setting",
        "universe_title",
        "tone",
    ):
        words.update(split_name_tokens(setup.get(key, "")))


def _collect_memory_lexicon(words, memory):
    if not isinstance(memory, dict):
        return
    for ledger_key in (
        "character_ledger",
        "location_ledger",
        "artifact_ledger",
        "faction_ledger",
    ):
        ledger = memory.get(ledger_key, {})
        if not isinstance(ledger, dict):
            continue
        for scope in ("local", "global"):
            bucket = ledger.get(scope, {})
            if isinstance(bucket, dict):
                for name in bucket.keys():
                    words.update(split_name_tokens(name))

    aliases = memory.get("aliases", {})
    if isinstance(aliases, dict):
        for scope in ("local", "global"):
            scope_aliases = aliases.get(scope, {})
            if not isinstance(scope_aliases, dict):
                continue
            for alias_map in scope_aliases.values():
                if isinstance(alias_map, dict):
                    for alias in alias_map.keys():
                        words.update(split_name_tokens(alias))


# ---------------------------------------------------------
# Persistent lexicon files (story / universe / global)
#
# JSON shape: {"words": [...], "ignored": [...], "ignored_grammar": [...]}
# Legacy cartridges may still be a plain JSON array (words only).
# All layers merge when checking; writes use custom_dictionary_scope.
# ---------------------------------------------------------


def global_lexicon_path():
    """Library-wide lexicon path under the adventures directory."""
    from config import get_adventures_dir

    return get_adventures_dir() / "spelling_lexicon_global.json"


def story_lexicon_path(adv_dir):
    """Per-cartridge lexicon beside setup.json and history.json."""
    return Path(adv_dir) / "spelling_lexicon.json"


def universe_lexicon_path(adv_dir):
    """Shared Universe root lexicon, or None when the story is standalone."""
    from config import find_universe_root

    root = find_universe_root(adv_dir)
    if root:
        return root / "spelling_lexicon.json"
    return None


def load_user_lexicon_file(path):
    """Load only the ``words`` set from a lexicon file (backward compatible)."""
    return load_lexicon_document(path)["words"]


def load_lexicon_document(path):
    """Load ``words``, ``ignored``, and ``ignored_grammar`` from a lexicon file."""
    empty = {"words": set(), "ignored": set(), "ignored_grammar": set()}
    path = Path(path) if path else None
    if not path or not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty

    if isinstance(data, list):
        # Pre–Phase 3 cartridges: bare word list on disk.
        return {
            "words": {str(w).lower() for w in data if w},
            "ignored": set(),
            "ignored_grammar": set(),
        }

    def _word_set(key):
        raw = data.get(key, [])
        if not isinstance(raw, list):
            return set()
        return {str(w).lower() for w in raw if w}

    grammar_raw = data.get("ignored_grammar", [])
    if not isinstance(grammar_raw, list):
        grammar_raw = []

    return {
        "words": _word_set("words"),
        "ignored": _word_set("ignored"),
        "ignored_grammar": {str(k) for k in grammar_raw if k},
    }


def save_lexicon_document(path, doc):
    """Write lexicon JSON; omit empty keys to keep files small."""
    path = Path(path)
    payload = {}
    words = sorted({str(w).lower() for w in doc.get("words", ()) if w})
    ignored = sorted({str(w).lower() for w in doc.get("ignored", ()) if w})
    ignored_grammar = sorted({str(k) for k in doc.get("ignored_grammar", ()) if k})
    if words:
        payload["words"] = words
    if ignored:
        payload["ignored"] = ignored
    if ignored_grammar:
        payload["ignored_grammar"] = ignored_grammar
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_user_lexicon_file(path, words):
    """Replace ``words`` in a file while preserving ignore lists."""
    doc = load_lexicon_document(path)
    doc["words"] = {str(w).lower() for w in words if w}
    save_lexicon_document(path, doc)


def grammar_ignore_key(issue, text):
    """Stable key for ignoring one grammar hit: ``rule_id|flagged_span`` (lower).

    Same rule on different spans stays distinct; re-linting the same span with
    the same rule_id is suppressed after **Ignore this issue**.
    """
    start = int(issue.get("start", 0))
    end = int(issue.get("end", 0))
    span = (text or "")[start:end].lower()
    rule_id = issue.get("rule_id") or issue.get("kind") or "grammar"
    return f"{rule_id}|{span}"


def _merge_lexicon_layers(engine, key):
    """Union one lexicon key across global → universe → story files."""
    adv_dir = getattr(engine, "adv_dir", None)
    if not adv_dir:
        return set()
    merged = set()
    merged.update(load_lexicon_document(global_lexicon_path())[key])
    univ_path = universe_lexicon_path(adv_dir)
    if univ_path:
        merged.update(load_lexicon_document(univ_path)[key])
    merged.update(load_lexicon_document(story_lexicon_path(adv_dir))[key])
    return merged


def load_merged_user_lexicon(engine):
    """Load user-added words from global, universe, and story lexicon files."""
    return _merge_lexicon_layers(engine, "words")


def load_merged_ignored_lexicon(engine):
    """Load ignored spelling tokens from all lexicon layers."""
    return _merge_lexicon_layers(engine, "ignored")


def load_merged_grammar_ignore(engine):
    """Load ignored grammar rule keys from all lexicon layers."""
    return _merge_lexicon_layers(engine, "ignored_grammar")


def resolve_lexicon_save_path(engine):
    """Path where Add / Ignore / Ignore-this-issue write (custom_dictionary_scope)."""
    from config import ENGINE_CONFIG

    adv_dir = getattr(engine, "adv_dir", None)
    if not adv_dir:
        return None
    scope = (ENGINE_CONFIG.get("custom_dictionary_scope") or "story").strip().lower()
    if scope == "global":
        return global_lexicon_path()
    if scope == "universe":
        path = universe_lexicon_path(adv_dir)
        if path:
            return path
    return story_lexicon_path(adv_dir)


def add_user_lexicon_word(engine, word):
    """Add *word* to ``words`` at the configured save scope.

    *engine* may be a live engine object or a bare ``adv_dir`` path (tests).
    """
    w = normalize_token(word)
    if isinstance(engine, (str, Path)) and not hasattr(engine, "adv_dir"):
        adv_dir = Path(engine)
        if not w or len(w) < 2:
            return load_user_lexicon(adv_dir)
        doc = load_lexicon_document(story_lexicon_path(adv_dir))
        doc["words"].add(w.lower())
        save_lexicon_document(story_lexicon_path(adv_dir), doc)
        return doc["words"]

    if not w or len(w) < 2:
        return load_merged_user_lexicon(engine)
    path = resolve_lexicon_save_path(engine)
    if not path:
        return load_merged_user_lexicon(engine)
    doc = load_lexicon_document(path)
    doc["words"].add(w.lower())
    save_lexicon_document(path, doc)
    return load_merged_user_lexicon(engine)


def add_ignored_word(engine, word):
    """Add a spelling token to ``ignored`` (suppress underline, not dictionary)."""
    w = normalize_token(word)
    if isinstance(engine, (str, Path)) and not hasattr(engine, "adv_dir"):
        adv_dir = Path(engine)
        if not w:
            return load_lexicon_document(story_lexicon_path(adv_dir))["ignored"]
        doc = load_lexicon_document(story_lexicon_path(adv_dir))
        doc["ignored"].add(w.lower())
        save_lexicon_document(story_lexicon_path(adv_dir), doc)
        return doc["ignored"]

    if not w:
        return load_merged_ignored_lexicon(engine)
    path = resolve_lexicon_save_path(engine)
    if not path:
        return load_merged_ignored_lexicon(engine)
    doc = load_lexicon_document(path)
    doc["ignored"].add(w.lower())
    save_lexicon_document(path, doc)
    return load_merged_ignored_lexicon(engine)


def add_ignored_grammar(engine, issue, text):
    """Persist a grammar-ignore key at the configured save scope."""
    key = grammar_ignore_key(issue, text)
    if not key:
        return load_merged_grammar_ignore(engine)
    path = resolve_lexicon_save_path(engine)
    if not path:
        return load_merged_grammar_ignore(engine)
    doc = load_lexicon_document(path)
    doc["ignored_grammar"].add(key)
    save_lexicon_document(path, doc)
    return load_merged_grammar_ignore(engine)


# Backward-compatible helpers (tests / direct path access)
def _lexicon_path(adv_dir):
    return story_lexicon_path(adv_dir)


def load_user_lexicon(adv_dir):
    return load_user_lexicon_file(story_lexicon_path(adv_dir))


def save_user_lexicon(adv_dir, words):
    save_user_lexicon_file(story_lexicon_path(adv_dir), words)


class OfflineSpellChecker:
    """Lazy wrapper around pyspellchecker with custom lexicon support."""

    def __init__(self, language="en", locale="american"):
        from spellchecker import SpellChecker

        self._locale = (locale or "american").strip().lower()
        if self._locale not in ("american", "british", "both"):
            self._locale = "american"
        self._spell = SpellChecker(language=language)
        self._extra = set()
        if self._locale in ("british", "both"):
            self._extra.update(_BRITISH_FORMS)

    def load_extra_words(self, words):
        merged = {w.lower() for w in (words or []) if w}
        if self._locale in ("british", "both"):
            merged.update(_BRITISH_FORMS)
        self._extra = merged
        if self._extra:
            self._spell.word_frequency.load_words(list(self._extra))

    def _locale_mismatch(self, lower):
        if self._locale == "both":
            return None
        if self._locale == "british" and lower in _AMERICAN_TO_BRITISH:
            return _AMERICAN_TO_BRITISH[lower]
        if self._locale == "american" and lower in _BRITISH_TO_AMERICAN:
            return _BRITISH_TO_AMERICAN[lower]
        return None

    def _base_known(self, lower):
        if not lower:
            return True
        if lower in IGNORE_WORDS or lower in self._extra:
            return True
        if self._locale_mismatch(lower):
            return False
        if len(self._spell.unknown([lower])) == 0:
            return True
        for stem in singular_candidates(lower):
            if stem in self._extra:
                return True
            if len(self._spell.unknown([stem])) == 0:
                return True
        return False

    def _contraction_valid(self, lower):
        expansions = contraction_expansions(lower)
        if not expansions:
            return False
        for phrase in expansions:
            parts = phrase.split()
            if parts and all(self._base_known(part) for part in parts):
                return True
        return False

    def _possessive_valid(self, lower):
        """Accept men's, Carl's, etc. when the stem is a known word."""
        if not is_noun_possessive(lower):
            return False
        stem = normalize_apostrophe(lower)[:-2]
        if self._base_known(stem):
            return True
        for candidate in singular_candidates(stem):
            if self._base_known(candidate):
                return True
        return False

    def is_correct(self, word):
        token = normalize_token(word)
        if not token:
            return True
        lower = normalize_apostrophe(token.lower())
        if self._contraction_valid(lower):
            return True
        if self._possessive_valid(lower):
            return True
        if self._base_known(lower):
            return True
        return False

    def suggestions(self, word, limit=8):
        token = normalize_token(word).lower()
        if not token:
            return []
        preferred = self._locale_mismatch(token)
        if preferred:
            return [preferred]
        candidates = self._spell.candidates(token) or set()
        if not candidates:
            for stem in singular_candidates(token):
                candidates = self._spell.candidates(stem) or set()
                if candidates:
                    break
        return sorted(candidates)[:limit]

    def scan_text(self, text):
        issues = []
        for word, start, end in iter_words(text):
            if self.is_correct(word):
                continue
            issues.append(
                {
                    "word": word,
                    "start": start,
                    "end": end,
                    "suggestions": self.suggestions(word),
                    "kind": "spelling",
                }
            )
        return issues

    def scan_prose(self, text, grammar=True):
        """Return spelling + optional grammar/style issues sorted by offset."""
        issues = self.scan_text(text)
        if grammar:
            issues.extend(scan_grammar(text))
        issues.sort(key=lambda item: (item["start"], item["end"]))
        return issues


class SpellCheckService:
    """Caches checker + lexicon per adventure directory and locale."""

    def __init__(self):
        self._checker = None
        self._adv_dir = None
        self._locale = None

    def _current_locale(self):
        from config import ENGINE_CONFIG

        return (ENGINE_CONFIG.get("spelling_locale") or "american").strip().lower()

    def get_checker(self, engine):
        adv_dir = getattr(engine, "adv_dir", None)
        locale = self._current_locale()
        if (
            self._checker is None
            or self._adv_dir != adv_dir
            or self._locale != locale
        ):
            self._checker = OfflineSpellChecker(locale=locale)
            self._adv_dir = adv_dir
            self._locale = locale
        if adv_dir:
            lexicon = collect_story_lexicon(engine)
            lexicon.update(load_merged_user_lexicon(engine))
            # Ignored tokens behave like allowlist for underlines only.
            lexicon.update(load_merged_ignored_lexicon(engine))
            self._checker.load_extra_words(lexicon)
        return self._checker

    def scan_prose(self, engine, text, grammar=None):
        """Spell + optional grammar scan, minus persisted grammar-ignore keys."""
        checker = self.get_checker(engine)
        if grammar is None:
            from config import ENGINE_CONFIG

            grammar = bool(ENGINE_CONFIG.get("offline_grammar_check", True))
        issues = checker.scan_prose(text, grammar=grammar)
        if grammar and getattr(engine, "adv_dir", None):
            ignored = load_merged_grammar_ignore(engine)
            if ignored:
                issues = [
                    i
                    for i in issues
                    if i.get("kind") != "grammar"
                    or grammar_ignore_key(i, text) not in ignored
                ]
        return issues

    def add_word(self, engine, word):
        """Persist to lexicon and invalidate cached checker."""
        if not getattr(engine, "adv_dir", None):
            return
        add_user_lexicon_word(engine, word)
        self._checker = None
        self.get_checker(engine)

    def ignore_word(self, engine, word):
        """Persist spelling ignore and invalidate cached checker."""
        if not getattr(engine, "adv_dir", None):
            return
        add_ignored_word(engine, word)
        self._checker = None
        self.get_checker(engine)

    def ignore_grammar(self, engine, issue, text):
        """Persist grammar-ignore key (no checker rebuild — filtered in scan_prose)."""
        if not getattr(engine, "adv_dir", None):
            return
        add_ignored_grammar(engine, issue, text)


def char_offset_to_index(text_widget, offset):
    return text_widget.index(f"1.0 + {int(offset)} chars")


def index_to_char_offset(text_widget, index):
    return len(text_widget.get("1.0", index))


def word_at_index(text_widget, index):
    """Return (word, start_index, end_index) for the token at index, or None."""
    line = index.split(".")[0]
    line_start = f"{line}.0"
    line_end = f"{line}.end"
    line_text = text_widget.get(line_start, line_end)
    col = int(index.split(".")[1])
    best = None
    for match in WORD_RE.finditer(line_text):
        if match.start() <= col <= match.end():
            best = match
            break
        if match.start() > col:
            break
    if not best:
        return None
    word = best.group(0)
    start = f"{line}.{best.start()}"
    end = f"{line}.{best.end()}"
    return word, start, end


def word_at_entry_index(entry_widget, event):
    """Return ``(word, start_col, end_col)`` for the token under a right-click in Entry."""
    try:
        col = int(entry_widget.index(f"@{event.x},{event.y}"))
    except tk.TclError:
        return None
    text = entry_widget.get()
    for match in WORD_RE.finditer(text):
        if match.start() <= col <= match.end():
            return match.group(0), match.start(), match.end()
        if match.start() > col:
            break
    return None


SPELL_ERROR_TAG = _SPELL_TAG
