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


def tidy_editor_prose_text(text):
    """Optional Edit Scene save cleanup for pasted JSON artifacts and stray whitespace."""
    if not text:
        return ""
    text = text.strip()
    text = text.replace('\\"', '"')
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Drop useless indentation at line starts (e.g. "\n    TEXT" -> "\n\nTEXT")
    text = re.sub(r"\n[ \t]+(?=\S)", "\n\n", text)
    text = re.sub(r"^[ \t]+", "", text)

    while "\t" in text:
        text = text.replace("\t", " ")
    while "  " in text:
        text = text.replace("  ", " ")

    if "\n" in text and "\n\n" not in text:
        text = text.replace("\n", "\n\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


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
