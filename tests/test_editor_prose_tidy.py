"""Tests for optional Edit Scene prose tidying."""

from prose_utils import (
    DIRECTOR_BLANK_TURN_STORY_PLACEHOLDER,
    editor_story_display_text,
    tidy_editor_prose_text,
)


class TestEditorStoryDisplayText:
    def test_blank_placeholder_opens_empty_in_editor(self):
        assert editor_story_display_text(DIRECTOR_BLANK_TURN_STORY_PLACEHOLDER) == ""

    def test_real_prose_is_unchanged(self):
        assert editor_story_display_text("Real story prose.") == "Real story prose."


class TestTidyEditorProseText:
    def test_strips_indented_line_breaks(self):
        raw = "First line.\n    Second paragraph."
        assert tidy_editor_prose_text(raw) == "First line.\n\nSecond paragraph."

    def test_collapses_tabs_and_spaces(self):
        raw = "Word\t\twith  extra   spaces"
        assert tidy_editor_prose_text(raw) == "Word with extra spaces"

    def test_unescapes_json_quotes(self):
        raw = 'He said \\"hello\\".'
        assert tidy_editor_prose_text(raw) == 'He said "hello".'

    def test_promotes_single_newlines_to_paragraphs(self):
        raw = "Line one.\nLine two."
        assert tidy_editor_prose_text(raw) == "Line one.\n\nLine two."
