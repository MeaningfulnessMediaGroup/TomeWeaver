"""
Suite D: JSON Fortress — sanitize_json repair pipeline.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from llm import sanitize_json


def _parse_sanitized(raw):
    clean = sanitize_json(raw)
    return json.loads(clean, strict=False)


class TestSanitizerNakedValues:
    def test_sanitizer_naked_values(self):
        garbage = '{"key": Hello world, "key2": "value"}'
        data = _parse_sanitized(garbage)
        assert data["key"] == "Hello world"
        assert data["key2"] == "value"


class TestSanitizerStrayQuotes:
    def test_sanitizer_stray_quotes(self):
        garbage = '{"story": "He said "hello" today"}'
        data = _parse_sanitized(garbage)
        assert "hello" in data["story"]
        assert data["story"] == 'He said "hello" today'


class TestSanitizerArraySoup:
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
