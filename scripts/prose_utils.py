"""Pure-text prose normalization helpers (no UI dependencies)."""

import re

DIRECTOR_BLANK_TURN_STORY_PLACEHOLDER = (
    "[ Blank Turn inserted by Director. Click 'Edit Scene' to write content. ]"
)

# Director Insert Turn (Generate — continue story): not a player choice from the card.
DIRECTOR_INSERT_CONTINUE_ACTION = "[ Continue the story ]"

# Meta-actions stored on prior turns but not shown on timeline cards.
HIDDEN_CARD_PLAYER_CHOICES = frozenset(
    {
        "[ Blank Turn ]",
        DIRECTOR_INSERT_CONTINUE_ACTION,
    }
)


def is_hidden_card_player_choice(player_choice):
    return (player_choice or "").strip() in HIDDEN_CARD_PLAYER_CHOICES


def is_director_blank_turn_placeholder(story_text):
    return (story_text or "").strip() == DIRECTOR_BLANK_TURN_STORY_PLACEHOLDER


def editor_story_display_text(story_text):
    """Story text shown in Edit Scene; blank placeholder opens as empty."""
    if is_director_blank_turn_placeholder(story_text):
        return ""
    return story_text or ""


# LLM JSON/prose leak: dialogue wrapped as \" ... \" (backslash-double-quote).
_ESCAPED_DOUBLE_QUOTE_WRAP = re.compile(r'\\"\s*(.*?)\s*\\"', re.DOTALL)


def _strip_trailing_llm_escape_garbage(para: str) -> str:
    """Remove stray trailing \\, \\", or \\\"\\\\ artifacts at a paragraph end."""
    para = (para or "").rstrip()
    while para:
        if para.endswith('\\"\\'):
            para = para[:-3].rstrip()
            continue
        if para.endswith('\\"'):
            para = para[:-2].rstrip()
            continue
        if para.endswith("\\"):
            para = para[:-1].rstrip()
            continue
        break
    return para


def sanitize_llm_prose_artifacts(text):
    """
    Prose sanitizer (Fortress pipeline via :func:`clean_prose`).

    - Converts mistaken \\\" dialogue wrappers to single-quoted '...'.
    - Strips paragraph-ending \\\\, \\\", and \\\"\\\\ leakage from JSON encoding.
    """
    if not text:
        return ""
    text = str(text)

    def _wrap_to_single_quote(match):
        inner = match.group(1).strip()
        return f"'{inner}'" if inner else ""

    text = _ESCAPED_DOUBLE_QUOTE_WRAP.sub(_wrap_to_single_quote, text)
    return text


def strip_paragraph_indentation(text):
    """Remove leading spaces/tabs at the start of each paragraph (blocks separated by blank lines)."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    paragraphs = re.split(r"\n\n+", text.strip())
    cleaned = []
    for para in paragraphs:
        if not para:
            continue
        lines = [line.lstrip(" \t") for line in para.split("\n")]
        block = "\n".join(lines).strip()
        block = _strip_trailing_llm_escape_garbage(block)
        if block:
            cleaned.append(block)
    return "\n\n".join(cleaned)


def clean_prose(text):
    """
    Format story/bridge prose for display and storage: flatten AI hard wraps,
    normalize paragraph breaks, trim paragraph whitespace, and run the prose
    sanitizer for LLM escape/dialogue artifacts.
    """
    if not text:
        return ""
    text = text.replace("\\n", "\n").replace("\r", "")
    text = sanitize_llm_prose_artifacts(text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = strip_paragraph_indentation(text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def tidy_editor_prose_text(text):
    """Optional Edit Scene save cleanup for pasted JSON artifacts and stray whitespace."""
    if not text:
        return ""
    text = text.strip()
    text = sanitize_llm_prose_artifacts(text)
    text = text.replace('\\"', '"')
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Indented line after a single newline → new paragraph (pasted layout cleanup)
    text = re.sub(r"\n[ \t]+(?=\S)", "\n\n", text)
    text = re.sub(r"^[ \t]+", "", text)

    while "\t" in text:
        text = text.replace("\t", " ")
    while "  " in text:
        text = text.replace("  ", " ")

    if "\n" in text and "\n\n" not in text:
        text = text.replace("\n", "\n\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return strip_paragraph_indentation(text)


_TURN_HEADER_RE = re.compile(r"^\s*Turn\s+(\d+)\s*:\s*", re.IGNORECASE | re.MULTILINE)


def clamp_single_turn_prose(story_text, turn_num=None):
    """Drop accidental multi-turn batching the LLM sometimes writes into story_text."""
    text = (story_text or "").strip()
    if not text:
        return text

    if turn_num is not None:
        text = re.sub(rf"^\s*Turn\s*{int(turn_num)}\s*:\s*", "", text, count=1, flags=re.IGNORECASE)

    headers = list(_TURN_HEADER_RE.finditer(text))
    if len(headers) > 1:
        text = text[: headers[1].start()].rstrip()
        headers = list(_TURN_HEADER_RE.finditer(text))

    if headers and (turn_num is None or headers[0].start() == 0):
        text = text[headers[0].end():].lstrip()

    return text
