"""Registry integrity: bundled prompts file vs code references."""
import re
from pathlib import Path

import pytest

from config import PROMPTS, PROMPT_KINDS, load_system_prompts, prompt_expects_json

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = ROOT / "configs" / "system_prompts.txt"


def _code_prompt_keys():
    keys = set()
    for py in (ROOT / "scripts").rglob("*.py"):
        if py.name.startswith("_"):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        keys.update(re.findall(r'PROMPTS\.get\(["\']([A-Z0-9_]+)["\']', text))
        keys.update(re.findall(r'require_prompt\(["\']([A-Z0-9_]+)["\']', text))
    return keys


def test_bundled_headers_have_json_or_text_suffix():
    raw = PROMPTS_FILE.read_text(encoding="utf-8")
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("[PROMPT:"):
            continue
        assert re.match(
            r"^\[PROMPT:[A-Z0-9_]+:(JSON|TEXT)\]\s*$", stripped, re.I
        ), f"Header missing :JSON or :TEXT suffix: {stripped}"


def test_every_code_reference_exists_in_registry():
    used = _code_prompt_keys()
    missing = sorted(k for k in used if k not in PROMPTS)
    assert not missing, f"PROMPTS missing keys: {missing}"


def test_kinds_match_suffixes_in_file():
    prompts, kinds = load_system_prompts()
    assert prompts == PROMPTS
    assert kinds == PROMPT_KINDS
    raw = PROMPTS_FILE.read_text(encoding="utf-8")
    for line in raw.splitlines():
        m = re.match(r"^\[PROMPT:([A-Z0-9_]+):(JSON|TEXT)\]\s*$", line.strip(), re.I)
        if not m:
            continue
        key, tag = m.group(1), m.group(2).lower()
        assert PROMPT_KINDS[key] == tag


def test_json_kind_helpers():
    assert prompt_expects_json("SYS_WORLD_GEN")
    assert not prompt_expects_json("SYS_RECAP")


def test_apply_json_response_format_openai_only(monkeypatch):
    from config import ENGINE_CONFIG
    from llm import apply_json_response_format, supports_openai_json_object_mode

    monkeypatch.setitem(ENGINE_CONFIG, "api_url", "http://localhost:1234/v1/chat/completions")
    assert not supports_openai_json_object_mode()
    payload = {"model": "x", "messages": []}
    apply_json_response_format(payload)
    assert "response_format" not in payload

    monkeypatch.setitem(ENGINE_CONFIG, "api_url", "https://api.openai.com/v1/chat/completions")
    assert supports_openai_json_object_mode()
    apply_json_response_format(payload)
    assert payload["response_format"] == {"type": "json_object"}
