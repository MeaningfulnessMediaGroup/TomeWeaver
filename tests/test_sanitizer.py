"""Suite D: JSON Fortress — ``sanitize_json`` repair pipeline tests."""

import json

import pytest

from llm import sanitize_json


def _parse_sanitized(raw):
    """Run ``sanitize_json`` and parse the repaired payload.

    Args:
        raw: Malformed LLM JSON string.

    Returns:
        dict: Parsed JSON object.
    """
    clean = sanitize_json(raw)
    return json.loads(clean, strict=False)


class TestSanitizerNakedValues:
    """Unquoted scalar values are wrapped as JSON strings."""

    def test_sanitizer_naked_values(self):
        garbage = '{"key": Hello world, "key2": "value"}'
        data = _parse_sanitized(garbage)
        assert data["key"] == "Hello world"
        assert data["key2"] == "value"


class TestSanitizerStrayQuotes:
    """Interior double quotes inside string values are escaped."""

    def test_sanitizer_stray_quotes(self):
        garbage = '{"story": "He said "hello" today"}'
        data = _parse_sanitized(garbage)
        assert "hello" in data["story"]
        assert data["story"] == 'He said "hello" today'


class TestSanitizerArraySoup:
    """Markdown-style ``choices`` arrays normalize to string lists."""

    def test_sanitizer_array_soup(self):
        garbage = """{
  "story_text": "You stand at a crossroads.",
  "choices": [
    - "Go north"
    'Take the "hidden" path'
    "Wait here",
  ]
}"""
        data = _parse_sanitized(garbage)
        assert isinstance(data["choices"], list)
        assert len(data["choices"]) == 3
        assert "Go north" in data["choices"][0]
        assert "hidden" in data["choices"][1]
        assert data["choices"][2] == "Wait here"


class TestSanitizerTrailingCommas:
    """Trailing commas before closing braces are stripped."""

    def test_strips_trailing_comma_before_closing_brace(self):
        # Arrange
        garbage = '{"story_text": "Done.", "choices": [],}'

        # Act
        data = _parse_sanitized(garbage)

        # Assert
        assert data["story_text"] == "Done."
        assert data["choices"] == []


class TestSanitizerSingleQuotedKeys:
    """Single-quoted JSON keys and values are normalized."""

    def test_converts_single_quoted_pairs(self):
        # Arrange
        garbage = "{'story_text': 'A quiet room.', 'choices': []}"

        # Act
        data = _parse_sanitized(garbage)

        # Assert
        assert data["story_text"] == "A quiet room."
        assert data["choices"] == []


class TestSanitizerMarkdownWrapper:
    """Prose wrappers around JSON blocks are ignored."""

    def test_extracts_json_from_markdown_fence(self):
        # Arrange
        garbage = """Here is the turn:
```json
{"story_text": "Wrapped output.", "choices": ["Continue"]}
```
Thanks."""

        # Act
        data = _parse_sanitized(garbage)

        # Assert
        assert data["story_text"] == "Wrapped output."
        assert "Continue" in data["choices"][0]
