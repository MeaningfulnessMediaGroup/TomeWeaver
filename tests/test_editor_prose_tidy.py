"""Tests for optional Edit Scene prose tidying."""

from prose_utils import (
    DIRECTOR_BLANK_TURN_STORY_PLACEHOLDER,
    DIRECTOR_INSERT_CONTINUE_ACTION,
    clamp_single_turn_prose,
    clean_prose,
    editor_story_display_text,
    is_hidden_card_player_choice,
    tidy_editor_prose_text,
)


class TestHiddenCardPlayerChoices:
    def test_blank_turn_is_hidden(self):
        assert is_hidden_card_player_choice("[ Blank Turn ]")

    def test_continue_story_is_hidden(self):
        assert is_hidden_card_player_choice(DIRECTOR_INSERT_CONTINUE_ACTION)

    def test_real_player_choice_is_shown(self):
        assert not is_hidden_card_player_choice("Open the door.")


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

    def test_converts_escaped_dialogue_wrappers_on_save(self):
        raw = 'He said \\"hello\\".'
        assert tidy_editor_prose_text(raw) == "He said 'hello'."

    def test_promotes_single_newlines_to_paragraphs(self):
        raw = "Line one.\nLine two."
        assert tidy_editor_prose_text(raw) == "Line one.\n\nLine two."

    def test_strips_leading_whitespace_between_paragraphs(self):
        raw = "First paragraph.\n\n\tSecond has a tab.\n\n   Third has spaces."
        assert tidy_editor_prose_text(raw) == (
            "First paragraph.\n\nSecond has a tab.\n\nThird has spaces."
        )


class TestCleanProse:
    def test_strips_paragraph_indentation_after_blank_line(self):
        raw = "Opening line.\n\n    Indented second paragraph.\n\n\tTabbed third."
        assert clean_prose(raw) == "Opening line.\n\nIndented second paragraph.\n\nTabbed third."

    def test_flattens_single_newlines_and_trims_paragraphs(self):
        raw = "Line one\nLine two\n\n   New paragraph."
        assert clean_prose(raw) == "Line one Line two\n\nNew paragraph."

    def test_strips_trailing_backslash_and_escaped_quote(self):
        assert clean_prose("The door creaked.\\") == "The door creaked."
        assert clean_prose('The door creaked.\\"') == "The door creaked."
        assert clean_prose('The door creaked.\\"\\') == "The door creaked."

    def test_strips_trailing_garbage_per_paragraph(self):
        raw = "First para.\\\"\n\nSecond para.\\"
        assert clean_prose(raw) == "First para.\n\nSecond para."

    def test_converts_escaped_double_quote_wrappers_to_single_quotes(self):
        raw = 'He said \\"hello there\\" and left.'
        assert clean_prose(raw) == "He said 'hello there' and left."

    def test_converts_wrapped_paragraph_dialogue(self):
        raw = '\\"Get out of here.\\"'
        assert clean_prose(raw) == "'Get out of here.'"

    def test_multiple_wrappers_in_one_paragraph(self):
        raw = '\\"Hi,\\" she said. \\"Goodbye.\\"'
        assert clean_prose(raw) == "'Hi,' she said. 'Goodbye.'"


class TestClampSingleTurnProse:
    def test_strips_leading_turn_header(self):
        raw = "Turn 3: The hallway stretches ahead."
        assert clamp_single_turn_prose(raw, turn_num=3) == "The hallway stretches ahead."

    def test_truncates_at_second_turn_header(self):
        raw = (
            "Turn 4: First scene continues.\n\n"
            "Turn 5: The model tried to keep going.\n\n"
            "Turn 6: Even further."
        )
        assert clamp_single_turn_prose(raw) == "First scene continues."

    def test_leaves_clean_prose_unchanged(self):
        raw = "A single paragraph with no turn labels."
        assert clamp_single_turn_prose(raw) == raw
