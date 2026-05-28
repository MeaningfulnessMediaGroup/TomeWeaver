"""Offline grammar and style linting for prose editors (no network).

Phase 2: conservative rule-based checks — not a full NLP grammar engine.
"""

from __future__ import annotations

import re

GRAMMAR_ERROR_TAG = "grammar_error"

# Words allowed after "an" even when consonant-initial (silent h, etc.)
_AN_EXCEPTIONS = frozenset(
    {
        "hour",
        "hours",
        "honest",
        "honor",
        "honour",
        "heir",
        "heirs",
        "herb",
        "herbs",
    }
)

# Skip repeated-word lint for intentional stutter / emphasis.
_REPEAT_ALLOW = frozenset({"ha", "la", "na", "oh", "um", "uh"})

_CLOSING_QUOTES = "'\"\u2019\u201d"


def _issue(start, end, message, replacement=None, rule_id=""):
    return {
        "start": int(start),
        "end": int(end),
        "message": message,
        "replacement": replacement,
        "rule_id": rule_id,
        "kind": "grammar",
    }


def _add_issues(issues, seen, start, end, message, replacement=None, rule_id=""):
    if start >= end:
        return
    key = (start, end, rule_id)
    if key in seen:
        return
    seen.add(key)
    issues.append(_issue(start, end, message, replacement, rule_id))


def _is_ellipsis_period(text, period_index):
    """True when *period_index* is the last dot of a fiction ellipsis (...)."""
    if period_index < 2 or text[period_index] != ".":
        return False
    return text[period_index - 1] == "." and text[period_index - 2] == "."


def _rule_repeated_words(text, issues, seen):
    for match in re.finditer(r"(?i)\b([a-z']{2,})\s+\1\b", text):
        word = match.group(1).lower()
        if word in _REPEAT_ALLOW:
            continue
        span = match.group(0)
        _add_issues(
            issues,
            seen,
            match.start(),
            match.end(),
            f'Repeated word "{match.group(1)}"',
            replacement=match.group(1),
            rule_id="repeat_word",
        )


def _rule_double_spaces(text, issues, seen):
    for match in re.finditer(r" {2,}", text):
        _add_issues(
            issues,
            seen,
            match.start(),
            match.end(),
            "Extra space between words",
            replacement=" ",
            rule_id="double_space",
        )


def _rule_space_before_punct(text, issues, seen):
    for match in re.finditer(r"\s+([,.;:!?])", text):
        punct = match.group(1)
        _add_issues(
            issues,
            seen,
            match.start(),
            match.end(),
            f"Remove space before “{punct}”",
            replacement=punct,
            rule_id="space_before_punct",
        )


def _rule_missing_space_after_punct(text, issues, seen):
    for match in re.finditer(r'([,.;:!?])(?=[A-Za-z"\'])', text):
        punct = match.group(1)
        nxt = text[match.end()]
        # Fiction: comma/period before closing quote — 'Dialog,' she said.
        if nxt in _CLOSING_QUOTES:
            continue
        _add_issues(
            issues,
            seen,
            match.start(),
            match.end() + 1,
            f"Add a space after “{punct}”",
            replacement=f"{punct} {nxt}",
            rule_id="missing_space_after_punct",
        )


def _rule_lowercase_after_sentence_end(text, issues, seen):
    for match in re.finditer(r'(?<=[.!?])\s+([a-z])', text):
        period_index = match.start() - 1
        if _is_ellipsis_period(text, period_index):
            continue
        letter = match.group(1)
        _add_issues(
            issues,
            seen,
            match.start(1),
            match.end(1),
            "Sentence may need a capital letter after end punctuation",
            replacement=letter.upper(),
            rule_id="lowercase_after_sentence",
        )


def _rule_multiple_punctuation(text, issues, seen):
    for match in re.finditer(r"!{2,}|\?{2,}|\.{4,}", text):
        normalized = match.group(0)[0]
        if match.group(0).startswith("."):
            normalized = "..."
        _add_issues(
            issues,
            seen,
            match.start(),
            match.end(),
            "Repeated punctuation — consider a single mark or an ellipsis",
            replacement=normalized,
            rule_id="repeat_punct",
        )


def _rule_tab_characters(text, issues, seen):
    for match in re.finditer(r"\t+", text):
        _add_issues(
            issues,
            seen,
            match.start(),
            match.end(),
            "Tab character in prose — use spaces instead",
            replacement=" ",
            rule_id="tab_char",
        )


def _rule_a_vs_an(text, issues, seen):
    for match in re.finditer(r"\ba ([A-Za-z][A-Za-z'-]*)", text):
        word = match.group(1)
        if word[0].lower() in "aeiou":
            _add_issues(
                issues,
                seen,
                match.start(),
                match.end(),
                f'Use “an {word}” before a vowel sound',
                replacement=f"an {word}",
                rule_id="a_before_vowel",
            )
    for match in re.finditer(r"\ban ([A-Za-z][A-Za-z'-]*)", text):
        word = match.group(1)
        lower = word.lower()
        if lower in _AN_EXCEPTIONS:
            continue
        if word[0].lower() not in "aeiou":
            _add_issues(
                issues,
                seen,
                match.start(),
                match.end(),
                f'Use “a {word}” before this consonant sound',
                replacement=f"a {word}",
                rule_id="an_before_consonant",
            )


def _rule_subject_verb_agreement(text, issues, seen):
    agreement = (
        (r"\b(he|she|it) don't\b", "Use “doesn't” with he/she/it"),
        (r"\b(they|we|you) doesn't\b", "Use “don't” with they/we/you"),
        (r"\b(they|we|you) was\b", "Use “were” with they/we/you"),
        (r"\b(he|she|it) are\b", "Use “is” with he/she/it"),
        (r"\b(they|we|you) is\b", "Use “are” with they/we/you"),
        (r"\bI is\b", "Use “am” with I"),
        (r"\bI are\b", "Use “am” with I"),
        (r"\b(he|she|it) were\b", "Use “was” with he/she/it (unless subjunctive)"),
    )
    for pattern, message in agreement:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if " were" in pattern.lower():
                window = text[max(0, match.start() - 12) : match.start()]
                if re.search(r"\bif\s*$", window, flags=re.IGNORECASE):
                    continue
            _add_issues(
                issues,
                seen,
                match.start(),
                match.end(),
                message,
                rule_id="subject_verb",
            )


def _rule_your_vs_youre(text, issues, seen):
    for match in re.finditer(
        r"(?i)\byour (going|coming|not|being|getting|trying|welcome|right|wrong|"
        r"finished|done|lost|here|there|still|already|never|always)\b",
        text,
    ):
        rest = match.group(0)[5:]  # drop "your"
        _add_issues(
            issues,
            seen,
            match.start(),
            match.end(),
            "Did you mean “you're” (you are)?",
            replacement=f"you're{rest}",
            rule_id="your_youre",
        )


def scan_grammar(text):
    """Return grammar/style issues as dicts with char offsets into *text*.

    Each issue includes ``start``, ``end``, ``message``, optional ``replacement``,
    ``rule_id``, and ``kind="grammar"``. Rules are applied in fixed order; *seen*
    prevents duplicate spans from overlapping patterns.
    """
    if not text or not str(text).strip():
        return []

    text = str(text)
    issues = []
    seen = set()

    # Fiction-safe ordering: dialogue/ellipsis exceptions live inside each rule.
    _rule_repeated_words(text, issues, seen)
    _rule_double_spaces(text, issues, seen)
    _rule_space_before_punct(text, issues, seen)
    _rule_missing_space_after_punct(text, issues, seen)
    _rule_lowercase_after_sentence_end(text, issues, seen)
    _rule_multiple_punctuation(text, issues, seen)
    _rule_tab_characters(text, issues, seen)
    _rule_a_vs_an(text, issues, seen)
    _rule_subject_verb_agreement(text, issues, seen)
    _rule_your_vs_youre(text, issues, seen)

    issues.sort(key=lambda i: (i["start"], i["end"]))
    return issues


def grammar_issue_at_offset(issues, offset):
    """Return the grammar issue covering *offset*, if any."""
    for issue in issues or []:
        if issue["start"] <= offset < issue["end"]:
            return issue
    return None
