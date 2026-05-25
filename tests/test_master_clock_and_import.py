"""Master Clock resync, bulk import, and timeline edge cases."""

import json

import pytest

from conftest import build_engine, make_turn, write_json


class TestResyncMasterClock:
    """Manual history edits are healed into a sequential Master Clock."""

    def test_resync_fixes_gaps_and_duplicates(self, mock_adventure_dir):
        # Arrange
        history = [
            make_turn(1, player_choice=None),
            make_turn(5, player_choice="Jump"),
            make_turn(5, player_choice="Duplicate"),
        ]
        engine = build_engine(mock_adventure_dir, history=history)
        engine.history[0]["turn"] = 10

        # Act
        engine.resync_master_clock()

        # Assert
        assert [t["turn"] for t in engine.history] == [10, 11, 12]
        reloaded = json.loads((mock_adventure_dir / "history.json").read_text(encoding="utf-8"))
        assert [t["turn"] for t in reloaded] == [10, 11, 12]


class TestImportTurns:
    """Bulk prose import splices structured turns into the timeline."""

    def test_import_turns_parses_action_markers(self, engine_with_history):
        # Arrange
        engine = engine_with_history(2, choices_per_turn=[None, "Original choice"])
        raw = """Opening scene in the rain.

> Duck into the alley

Shadows swallow the hero whole.

> Knock on the rusted door
"""
        # Act
        ok, msg = engine.import_turns(raw, insert_after_idx=1)

        # Assert
        assert ok is True
        assert "2 turns" in msg
        assert len(engine.history) == 4
        assert engine.history[1]["player_choice"] == "[ Imported Text ]"
        assert "Opening scene" in engine.history[2]["story_text"]
        assert engine.history[2]["player_choice"] == "Duck into the alley"
        assert engine.history[3]["player_choice"] == "Knock on the rusted door"
        assert [t["turn"] for t in engine.history] == [1, 2, 3, 4]

    def test_import_turns_rejects_empty_payload(self, engine_with_history):
        # Arrange
        engine = engine_with_history(2)

        # Act
        ok, msg = engine.import_turns("   \n  ", insert_after_idx=0)

        # Assert
        assert ok is False
        assert "No valid content" in msg


class TestTimelineGuardRails:
    """Invalid surgery indices fail safely without corrupting state."""

    def test_insert_blank_turn_rejects_out_of_range(self, engine_with_history):
        # Arrange
        engine = engine_with_history(3)
        before = len(engine.history)

        # Act / Assert
        assert engine.insert_blank_turn(-1) is False
        assert engine.insert_blank_turn(before + 1) is False
        assert len(engine.history) == before

    def test_delete_turn_rejects_out_of_range(self, engine_with_history):
        # Arrange
        engine = engine_with_history(3)

        # Act / Assert
        assert engine.delete_turn(-1) is False
        assert engine.delete_turn(99) is False
        assert len(engine.history) == 3

    def test_convert_turn_to_bridge_requires_following_turn(self, engine_with_history):
        # Arrange
        engine = engine_with_history(2)

        # Act / Assert
        assert engine.convert_turn_to_bridge(1) is False

    def test_convert_bridge_to_turn_rejects_empty_bridge(self, engine_with_history):
        # Arrange
        engine = engine_with_history(3)
        engine.history[1]["narrative_bridge"] = ""

        # Act / Assert
        assert engine.convert_bridge_to_turn(1) is False
        assert len(engine.history) == 3

    def test_turn_to_bridge_skips_ok_failed_tokens(self, engine_with_history):
        # Arrange
        engine = engine_with_history(3)
        engine.history[0]["story_text"] = "Core scene."
        engine.history[1]["narrative_bridge"] = "[OK]"

        # Act
        assert engine.convert_turn_to_bridge(0) is True

        # Assert
        assert "[OK]" not in engine.history[0]["narrative_bridge"]
        assert "Core scene." in engine.history[0]["narrative_bridge"]

    def test_split_chapter_rejects_invalid_indices(self, engine_with_history):
        # Arrange
        engine = engine_with_history(4)

        # Act / Assert
        assert engine.split_chapter(0) is False
        assert engine.split_chapter(len(engine.history)) is False

    def test_merge_chapter_rejects_first_chapter(self, engine_with_history):
        # Arrange
        engine = engine_with_history(
            4,
            chapters=[
                {"chapter_number": 1, "title": "A", "start_turn": 1, "end_turn": 4},
            ],
        )

        # Act / Assert
        assert engine.merge_chapter_up(1) is False


class TestStatePersistence:
    """save_state round-trips critical cartridge files."""

    def test_save_state_persists_history_and_memory(self, mock_adventure_dir, engine_with_history):
        # Arrange
        engine = engine_with_history(2)
        engine.history[0]["story_text"] = "Persisted mutation."
        engine.memory["plot_ledger"] = [{"chapter_number": 1, "summary": "Cached"}]

        # Act
        engine.save_state()
        reloaded = build_engine(mock_adventure_dir, mode="sandbox")

        # Assert
        assert reloaded.history[0]["story_text"] == "Persisted mutation."
        assert reloaded.memory["plot_ledger"][0]["summary"] == "Cached"

    def test_manual_edit_turn_updates_field_on_disk(self, engine_with_history, mock_adventure_dir):
        # Arrange
        engine = engine_with_history(2)

        # Act
        assert engine.manual_edit_turn(1, "location", "Roof") is True
        reloaded = build_engine(mock_adventure_dir, mode="sandbox")

        # Assert
        assert reloaded.history[1]["location"] == "Roof"
