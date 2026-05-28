"""Tests for offline grammar/style linting (Phase 2)."""

import pytest

from grammar_lint import grammar_issue_at_offset, scan_grammar


def test_repeated_word():
    issues = scan_grammar("The the door opened.")
    assert any(i["rule_id"] == "repeat_word" for i in issues)


def test_double_space():
    issues = scan_grammar("Hello  world.")
    assert any(i["rule_id"] == "double_space" for i in issues)


def test_space_before_comma():
    issues = scan_grammar("Yes , please.")
    assert any(i["rule_id"] == "space_before_punct" for i in issues)


def test_missing_space_after_period():
    issues = scan_grammar("Done.Next line.")
    assert any(i["rule_id"] == "missing_space_after_punct" for i in issues)


def test_subject_verb_he_dont():
    issues = scan_grammar("He don't know.")
    assert any(i["rule_id"] == "subject_verb" for i in issues)


def test_subject_verb_subjunctive_allowed():
    issues = scan_grammar("If he were taller, he would reach.")
    assert not any(i["rule_id"] == "subject_verb" for i in issues)


def test_a_vs_an():
    issues = scan_grammar("It was a apple.")
    assert any(i["rule_id"] == "a_before_vowel" for i in issues)
    assert scan_grammar("It was an hour later.") == []


def test_your_youre():
    issues = scan_grammar("Your going to regret this.")
    assert any(i["rule_id"] == "your_youre" for i in issues)


def test_clean_prose_has_no_issues():
    assert scan_grammar("She closed the door and walked away.") == []


def test_grammar_issue_at_offset():
    issues = scan_grammar("The the end.")
    hit = grammar_issue_at_offset(issues, 4)
    assert hit is not None
    assert hit["rule_id"] == "repeat_word"


@pytest.mark.parametrize(
    "text,rule",
    [
        ("Wait!!", "repeat_punct"),
        ("Line\tbreak", "tab_char"),
        ("End. the next", "lowercase_after_sentence"),
    ],
)
def test_misc_rules(text, rule):
    issues = scan_grammar(text)
    assert any(i["rule_id"] == rule for i in issues), f"Expected {rule} in {issues!r}"


def test_fiction_dialogue_punct_before_closing_quote_allowed():
    text = "'Dialog,' she said. 'we will do it.' she continue."
    issues = scan_grammar(text)
    assert not any(i["rule_id"] == "missing_space_after_punct" for i in issues)


def test_lowercase_after_ellipsis_allowed():
    text = "This was only the beginning... a first step"
    issues = scan_grammar(text)
    assert not any(i["rule_id"] == "lowercase_after_sentence" for i in issues)


def test_prose_with_quoted_dialogue_and_ellipsis():
    text = (
        "'Good morning,' she purred over her shoulder. I hope you're ready... "
        "we've got quite the crowd coming.' Still... there was more to say."
    )
    issues = scan_grammar(text)
    assert not any(i["rule_id"] == "missing_space_after_punct" for i in issues)
    assert not any(i["rule_id"] == "lowercase_after_sentence" for i in issues)


def test_real_sentence_end_still_flags_lowercase():
    issues = scan_grammar("End. the next")
    assert any(i["rule_id"] == "lowercase_after_sentence" for i in issues)
