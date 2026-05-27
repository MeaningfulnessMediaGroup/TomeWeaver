"""Pure-text prose normalization helpers (no UI dependencies)."""

import re

DIRECTOR_BLANK_TURN_STORY_PLACEHOLDER = (
    "[ Blank Turn inserted by Director. Click 'Edit Scene' to write content. ]"
)


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
