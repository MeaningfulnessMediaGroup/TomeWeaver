"""Quick LLM spelling suggestions for prose lint (uses active API profile).

Optional right-click menu item: one small chat completion (~80 tokens) to suggest
replacements for a flagged word or grammar span. Uses the same API URL/model as
gameplay so local LM Studio stays local.
"""

from __future__ import annotations

import re
import time

import requests

from config import ENGINE_CONFIG, PROMPTS
from llm import enforce_rate_limit
from logger import log_llm_interaction


def extract_local_context(text, start, end, window=120):
    """Return a short snippet around char offsets *start*..*end* for the prompt."""
    if not text:
        return ""
    lo = max(0, int(start) - window)
    hi = min(len(text), int(end) + window)
    return text[lo:hi].strip()


def parse_ai_suggestion_lines(raw):
    """Parse up to five single-line suggestions from model output.

    Strips list markers (``1.``, ``-``, bullets) and ignores meta lines like
    ``NONE`` or ``Here are some suggestions``.
    """
    if not raw:
        return []
    text = str(raw).strip()
    if text.upper() in ("NONE", "N/A", "NA"):
        return []
    lines = []
    for line in text.splitlines():
        line = line.strip()
        line = re.sub(r"^[\-*•\d.)]+\s*", "", line)  # ``1. foo`` → ``foo``
        line = line.strip("\"'")
        if not line or line.upper() == "NONE" or line.upper().startswith("NONE "):
            continue
        if line.lower().startswith("here are"):
            continue
        lines.append(line)
    return lines[:5]


def fetch_ai_word_suggestions(
    word,
    context,
    locale="american",
    issue_hint="",
    adv_dir=None,
):
    """Call the configured LLM for quick replacement suggestions.

    Returns ``(True, [suggestions])`` or ``(False, error_message)``.
    Retries once on HTTP/network failure; logs to ``session_log`` when *adv_dir*
    is set (same as gameplay LLM calls).
    """
    api_url = (ENGINE_CONFIG.get("api_url") or "").strip()
    if not api_url:
        return False, "No LLM API configured. Set an active profile in Dashboard → Settings."

    sys_prompt = (
        PROMPTS.get("SYS_SPELL_AI", "").strip()
        or "You suggest spelling or wording fixes. Reply with up to 5 replacements, one per line, or NONE."
    )
    user_tpl = PROMPTS.get(
        "USER_SPELL_AI",
        'Flagged text: "{word}"\nNearby prose: "{context}"\nPreferred locale: {locale}',
    )
    user_prompt = (
        user_tpl.replace("{word}", word or "")
        .replace("{context}", (context or "")[:500])
        .replace("{locale}", locale or "american")
    )
    if issue_hint:
        user_prompt += f"\nLint note: {issue_hint}"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]
    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip():
        headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"

    payload = {
        "model": ENGINE_CONFIG.get("model", "loaded-model"),
        "messages": messages,
        "temperature": 0.2,  # Low variance — we want direct replacements, not prose.
        "max_tokens": 80,
    }

    last_err = "LLM request failed."
    for attempt in range(2):
        try:
            enforce_rate_limit()
            resp = requests.post(api_url, headers=headers, json=payload, timeout=20)
            if resp.status_code != 200:
                last_err = resp.text[:200] or f"HTTP {resp.status_code}"
                time.sleep(1)
                continue
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            if adv_dir:
                log_llm_interaction(adv_dir, messages, raw, attempt=attempt + 1)
            return True, parse_ai_suggestion_lines(raw)
        except requests.exceptions.RequestException as exc:
            last_err = str(exc)
            time.sleep(1)
        except (KeyError, IndexError, ValueError) as exc:
            last_err = f"Unexpected LLM response: {exc}"
            break
    return False, last_err


def spell_ai_enabled():
    """True when **AI Spelling Suggestions** is on in Prose Lint Settings."""
    return bool(ENGINE_CONFIG.get("spell_ai_suggestions", True))
