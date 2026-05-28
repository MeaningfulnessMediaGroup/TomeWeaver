"""Tests for LLM spell suggestion parsing."""

from spell_ai import extract_local_context, parse_ai_suggestion_lines


def test_parse_ai_suggestion_lines():
    raw = "ecstasy\nextasy\n\nNONE extra"
    assert parse_ai_suggestion_lines(raw) == ["ecstasy", "extasy"]

    assert parse_ai_suggestion_lines("NONE") == []
    assert parse_ai_suggestion_lines("1. colour\n2. gray") == ["colour", "gray"]


def test_extract_local_context():
    text = "She felt a wave of extacy wash over her as the music swelled."
    idx = text.index("extacy")
    ctx = extract_local_context(text, idx, idx + len("extacy"))
    assert "extacy" in ctx
    assert "music" in ctx
