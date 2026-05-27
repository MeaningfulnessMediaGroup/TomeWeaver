"""Multi-step timeline surgery chains and cartridge invariant checks."""

import json

import pytest

from conftest import assert_cartridge_consistent, build_engine, make_turn, write_json
from test_run_tree import reload_engine
from run_tree import load_manifest, switch_run


def _choices(n):
    return [None if i == 0 else f"choice-{i}" for i in range(n)]


class TestTimelineInvariantChains:
    def test_fork_delete_insert_resync(self, engine_with_history):
        engine = engine_with_history(6, choices_per_turn=_choices(6))
        engine.save_state()

        ok, _, _ = engine.fork_at_turn(3)
        assert ok is True
        assert_cartridge_consistent(engine)

        assert engine.delete_turn(1) is True
        assert_cartridge_consistent(engine)

        assert engine.insert_blank_turn(1) is True
        engine.resync_master_clock()
        assert_cartridge_consistent(engine)

    def test_import_then_split_chapter(self, engine_with_history):
        chapters = [
            {"chapter_number": 1, "title": "Act One", "start_turn": 1, "end_turn": None},
        ]
        engine = engine_with_history(2, chapters=chapters, choices_per_turn=[None, "Go"])
        raw = "> Strike the bell\n\nThe echo rolls across the valley.\n"
        ok, _ = engine.import_turns(raw, insert_after_idx=1)
        assert ok is True

        assert engine.split_chapter(2) is True
        assert_cartridge_consistent(engine)
        assert len(engine.chapters) == 2

    def test_bridge_convert_then_merge_chapter(self, engine_with_history):
        chapters = [
            {"chapter_number": 1, "title": "One", "start_turn": 1, "end_turn": 4},
            {"chapter_number": 2, "title": "Two", "start_turn": 5, "end_turn": None},
        ]
        engine = engine_with_history(
            5,
            chapters=chapters,
            choices_per_turn=_choices(5),
        )
        assert engine.convert_turn_to_bridge(1) is True
        assert_cartridge_consistent(engine)

        assert engine.merge_chapter_up(2) is True
        assert_cartridge_consistent(engine)

    def test_fork_switch_round_trip(self, engine_with_history):
        engine = engine_with_history(5, choices_per_turn=_choices(5))
        engine.save_state()

        ok, _, branch_id = engine.fork_at_turn(2)
        assert ok is True
        engine.history[1]["story_text"] = "Live edit on branch"
        engine.save_state()

        manifest = __import__("run_tree").load_manifest(engine.adv_dir)
        original_id = next(
            rid
            for rid, node in manifest["runs"].items()
            if node.get("run_kind") == "original"
        )

        ok, _ = switch_run(engine.adv_dir, original_id)
        assert ok is True
        engine = reload_engine(engine.adv_dir)
        assert len(engine.history) == 5

        ok, _ = switch_run(engine.adv_dir, branch_id)
        assert ok is True
        engine = reload_engine(engine.adv_dir)
        assert len(engine.history) == 2
        assert engine.history[1]["story_text"] == "Live edit on branch"
        assert_cartridge_consistent(engine)

    def test_delete_turn_migrates_player_choice(self, engine_with_history):
        engine = engine_with_history(4, choices_per_turn=_choices(4))
        before = engine.history[2]["player_choice"]
        assert engine.delete_turn(1) is True
        assert engine.history[1]["player_choice"] == before
        assert_cartridge_consistent(engine)

    def test_on_disk_matches_memory_after_save(self, engine_with_history):
        engine = engine_with_history(3, choices_per_turn=_choices(3))
        engine.save_state()
        assert_cartridge_consistent(engine, check_disk=True)

        disk = json.loads((engine.adv_dir / "history.json").read_text(encoding="utf-8"))
        assert disk == engine.history
