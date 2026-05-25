"""Storybook export compiler (TXT / MD / HTML)."""

from pathlib import Path

import pytest

from conftest import make_turn
from exporter import export_story


@pytest.fixture
def sample_cartridge(tmp_path):
    """Minimal history + chapters for export tests."""
    history = [
        make_turn(1, player_choice=None),
        make_turn(
            2,
            story_text="Inside the tavern, smoke hangs low.",
            player_choice="Order an ale",
            narrative_bridge="",
        ),
        make_turn(
            3,
            story_text="The bartender slides a mug across the bar.",
            player_choice="Ask about the missing lord",
            narrative_bridge="",
        ),
        make_turn(
            4,
            story_text="The bartender leans in with a guarded look.",
            player_choice=None,
            narrative_bridge="He nodded and poured the ale without a word.",
        ),
    ]
    chapters = [
        {
            "chapter_number": 1,
            "title": "The Tavern",
            "start_turn": 1,
            "end_turn": 4,
        }
    ]
    setup = {"title": "Export Test Tale"}
    return tmp_path, setup, history, chapters


class TestExportStory:
    """Chronological game log compiles into readable storybook files."""

    @pytest.mark.parametrize("export_type,expected_suffix", [(1, ".txt"), (2, ".md"), (3, ".html")])
    def test_writes_requested_format(self, sample_cartridge, export_type, expected_suffix):
        # Arrange
        adv_dir, setup, history, chapters = sample_cartridge
        out_path = adv_dir / f"book{expected_suffix}"

        # Act
        result = export_story(
            adv_dir, setup, history, chapters, export_type, custom_path=out_path
        )

        # Assert
        assert result == out_path
        assert out_path.exists()
        body = out_path.read_text(encoding="utf-8")
        assert "Export Test Tale" in body
        assert "Inside the tavern" in body

    def test_novelization_prefers_bridge_over_raw_action(self, sample_cartridge):
        # Arrange
        adv_dir, setup, history, chapters = sample_cartridge
        out_path = adv_dir / "novel.txt"

        # Act
        export_story(
            adv_dir, setup, history, chapters, 1, use_novelization=True, custom_path=out_path
        )
        body = out_path.read_text(encoding="utf-8")

        # Assert
        assert "He nodded and poured the ale" in body
        assert "[ Action: Ask about the missing lord ]" not in body

    def test_non_novelized_export_shows_player_actions(self, sample_cartridge):
        # Arrange
        adv_dir, setup, history, chapters = sample_cartridge
        out_path = adv_dir / "raw.txt"

        # Act
        export_story(
            adv_dir, setup, history, chapters, 1, use_novelization=False, custom_path=out_path
        )
        body = out_path.read_text(encoding="utf-8")

        # Assert
        assert "[ Action: Ask about the missing lord ]" in body

    def test_skips_ui_meta_commands_in_export(self, sample_cartridge):
        # Arrange
        adv_dir, setup, history, chapters = sample_cartridge
        history[1]["player_choice"] = "Undo"
        out_path = adv_dir / "meta.txt"

        # Act
        export_story(
            adv_dir, setup, history, chapters, 1, use_novelization=False, custom_path=out_path
        )
        body = out_path.read_text(encoding="utf-8")

        # Assert
        assert "[ Action: Undo ]" not in body
