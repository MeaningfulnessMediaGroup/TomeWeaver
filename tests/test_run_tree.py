"""
Run tree manifest, snapshot I/O, and Phase 1 checklist integration tests.

Automates checklist items 1–11 from the Phase 1 QA doc. Item 12 (Story Mode
busy guard blocking switch/restart) is GUI-only and stays manual.
"""

import json

import pytest

from api import TomeWeaverAPI
from conftest import build_engine, make_turn, write_json
from run_tree import (
    archive_current_run,
    auto_fork_archive_label,
    auto_run_label,
    delete_run,
    has_saveable_state,
    headless_restart_wipe,
    list_runs,
    load_manifest,
    prepare_restart,
    rename_run,
    switch_run,
    turn_count_from_history,
)


def seed_history(adv_dir, turn_count, *, marker=""):
    """Write a minimal played timeline to disk (turn 1..turn_count)."""
    history = []
    for i in range(1, turn_count + 1):
        pc = None if i == 1 else f"{marker}choice at {i}"
        history.append(make_turn(i, player_choice=pc, story_text=f"Prose {marker}{i}"))
    write_json(adv_dir / "history.json", history)
    return history


def seed_local_memory(adv_dir, tag):
    write_json(
        adv_dir / "memory.json",
        {
            "plot_ledger": [{"event": tag}],
            "chapter_ledger": [],
            "character_ledger": {},
        },
    )


def reload_engine(adv_dir, mode="sandbox"):
    """Simulate closing and reopening the workspace (fresh engine from disk)."""
    from config import load_json_safely

    setup = load_json_safely(adv_dir / "setup.json", "setup.json")
    return build_engine(adv_dir, mode=mode)


# ---------------------------------------------------------------------------
# Unit tests (fast, targeted)
# ---------------------------------------------------------------------------


class TestArchiveAndManifest:
    def test_empty_history_cannot_archive(self, mock_adventure_dir):
        run_id, msg = archive_current_run(mock_adventure_dir)
        assert run_id is None
        assert "Nothing to archive" in msg
        assert not (mock_adventure_dir / "runs" / "manifest.json").exists()

    def test_archive_creates_snapshot_and_manifest(self, engine_with_history):
        engine = engine_with_history(3)
        engine.save_state()

        run_id, msg = archive_current_run(engine.adv_dir, label="Test Run A")
        assert run_id is not None
        assert "Test Run A" in msg

        snap = engine.adv_dir / "runs" / "snapshots" / run_id
        assert (snap / "history.json").exists()
        assert (snap / "chapters.json").exists()
        assert (snap / "memory.json").exists()
        assert (snap / "meta.json").exists()

        manifest = load_manifest(engine.adv_dir)
        assert run_id in manifest["runs"]
        assert manifest["runs"][run_id]["turn_count"] == 3

        snap_history = json.loads((snap / "history.json").read_text(encoding="utf-8"))
        assert len(snap_history) == 3

    def test_auto_run_label_uses_turn_count_and_timestamp(self):
        history = [make_turn(1), make_turn(7, player_choice="done")]
        label = auto_run_label(history)
        assert "Turn 7" in label
        assert "—" in label

    def test_auto_fork_archive_label(self):
        assert "Original timeline" in auto_fork_archive_label(5)
        assert "fork @ turn 5" in auto_fork_archive_label(5)


class TestSwitchRun:
    def test_switch_loads_target_without_auto_stash(self, mock_adventure_dir):
        history_a = [make_turn(1, player_choice=None), make_turn(2, player_choice="Path A")]
        write_json(mock_adventure_dir / "history.json", history_a)
        write_json(mock_adventure_dir / "memory.json", {"plot_ledger": [{"tag": "A"}]})

        run_a, _ = archive_current_run(mock_adventure_dir, label="Run A")

        history_b = [
            make_turn(1, player_choice=None),
            make_turn(2, player_choice="Path B"),
            make_turn(3, player_choice="Go"),
        ]
        write_json(mock_adventure_dir / "history.json", history_b)
        write_json(mock_adventure_dir / "memory.json", {"plot_ledger": [{"tag": "B"}]})

        run_b, _ = archive_current_run(mock_adventure_dir, label="Run B")
        assert run_b

        ok, msg = switch_run(mock_adventure_dir, run_a)
        assert ok is True
        assert "Run A" in msg

        manifest = load_manifest(mock_adventure_dir)
        assert manifest["active_run_id"] == run_a
        assert len(manifest["runs"]) == 2  # A and B only — no auto-stash

        loaded = json.loads((mock_adventure_dir / "history.json").read_text(encoding="utf-8"))
        assert loaded[1]["player_choice"] == "Path A"

    def test_switch_rejects_already_active_timeline(self, mock_adventure_dir):
        from run_tree import can_switch_to_run, get_active_playback_id

        history = [make_turn(1, player_choice=None), make_turn(2, player_choice="Only")]
        write_json(mock_adventure_dir / "history.json", history)
        run_id, _ = archive_current_run(mock_adventure_dir, label="Saved")

        ok, _ = switch_run(mock_adventure_dir, run_id)
        assert ok is True
        assert get_active_playback_id(mock_adventure_dir) == run_id

        ok, msg = switch_run(mock_adventure_dir, run_id)
        assert ok is False
        assert "already" in msg.lower()

        ok_can, err = can_switch_to_run(mock_adventure_dir, run_id)
        assert ok_can is False
        assert err

    def test_switch_persists_active_slot_before_loading_target(self, mock_adventure_dir):
        history_a = [make_turn(1, player_choice=None), make_turn(2, player_choice="Path A")]
        write_json(mock_adventure_dir / "history.json", history_a)
        run_a, _ = archive_current_run(mock_adventure_dir, label="Run A")

        write_json(
            mock_adventure_dir / "history.json",
            [make_turn(1), make_turn(2, player_choice="Path B"), make_turn(3, player_choice="Go")],
        )
        run_b, _ = archive_current_run(mock_adventure_dir, label="Run B")

        from run_tree import set_active_run_id

        set_active_run_id(mock_adventure_dir, run_b)
        write_json(
            mock_adventure_dir / "history.json",
            [
                make_turn(1),
                make_turn(2, player_choice="Path B"),
                make_turn(3, player_choice="Go"),
                make_turn(4, player_choice="extra"),
            ],
        )

        ok, _ = switch_run(mock_adventure_dir, run_a)
        assert ok is True
        assert len(load_manifest(mock_adventure_dir)["runs"]) == 2

        snap_b = json.loads(
            (mock_adventure_dir / "runs" / "snapshots" / run_b / "history.json").read_text(encoding="utf-8")
        )
        assert len(snap_b) == 4
        assert snap_b[3]["player_choice"] == "extra"

    def test_switch_with_stash_current_still_archives(self, mock_adventure_dir):
        history_a = [make_turn(1, player_choice=None), make_turn(2, player_choice="Path A")]
        write_json(mock_adventure_dir / "history.json", history_a)
        run_a, _ = archive_current_run(mock_adventure_dir, label="Run A")

        write_json(
            mock_adventure_dir / "history.json",
            [make_turn(1), make_turn(2, player_choice="live"), make_turn(3, player_choice="x")],
        )
        run_b, _ = archive_current_run(mock_adventure_dir, label="Run B")

        ok, _ = switch_run(mock_adventure_dir, run_a, stash_current=True)
        assert ok is True
        assert len(load_manifest(mock_adventure_dir)["runs"]) == 3  # A, B, explicit stash

    def test_switch_from_empty_root_skips_stash(self, mock_adventure_dir):
        history = [make_turn(1, player_choice=None), make_turn(2, player_choice="Only")]
        write_json(mock_adventure_dir / "history.json", history)
        run_id, _ = archive_current_run(mock_adventure_dir, label="Saved")

        write_json(mock_adventure_dir / "history.json", [])
        assert has_saveable_state(mock_adventure_dir) is False

        ok, _ = switch_run(mock_adventure_dir, run_id)
        assert ok is True
        assert len(load_manifest(mock_adventure_dir)["runs"]) == 1


class TestRenameAndDelete:
    def test_rename_persists_in_manifest_and_meta(self, engine_with_history):
        engine = engine_with_history(2)
        engine.save_state()
        run_id, _ = archive_current_run(engine.adv_dir, label="Old Name")

        ok, _ = rename_run(engine.adv_dir, run_id, "New Name")
        assert ok is True

        manifest = load_manifest(engine.adv_dir)
        assert manifest["runs"][run_id]["label"] == "New Name"

        meta = json.loads(
            (engine.adv_dir / "runs" / "snapshots" / run_id / "meta.json").read_text(encoding="utf-8")
        )
        assert meta["label"] == "New Name"

    def test_delete_removes_snapshot_folder(self, engine_with_history):
        engine = engine_with_history(2)
        engine.save_state()
        run_id, _ = archive_current_run(engine.adv_dir)
        snap = engine.adv_dir / "runs" / "snapshots" / run_id
        assert snap.exists()

        ok, _ = delete_run(engine.adv_dir, run_id)
        assert ok is True
        assert not snap.exists()
        assert run_id not in load_manifest(engine.adv_dir)["runs"]


class TestRestartHelpers:
    def test_prepare_restart_archives_when_requested(self, engine_with_history):
        engine = engine_with_history(4)
        engine.save_state()

        ok, _ = prepare_restart(engine.adv_dir, save_run=True)
        assert ok is True
        manifest = load_manifest(engine.adv_dir)
        assert len(manifest["runs"]) == 1
        assert manifest["active_run_id"] is None

    def test_prepare_restart_discard_skips_archive(self, engine_with_history):
        engine = engine_with_history(4)
        engine.save_state()

        ok, _ = prepare_restart(engine.adv_dir, save_run=False)
        assert ok is True
        assert not (engine.adv_dir / "runs" / "manifest.json").exists()

    def test_headless_restart_wipe_clears_history(self, mock_adventure_dir):
        from config import load_json_safely

        write_json(mock_adventure_dir / "history.json", [make_turn(1), make_turn(2, player_choice="x")])
        setup = load_json_safely(mock_adventure_dir / "setup.json", "setup.json")

        headless_restart_wipe(mock_adventure_dir, setup)
        history = json.loads((mock_adventure_dir / "history.json").read_text(encoding="utf-8"))
        assert history == []


class TestTurnCount:
    def test_turn_count_uses_max_turn_number(self):
        history = [make_turn(1), make_turn(5, player_choice="jump")]
        assert turn_count_from_history(history) == 5


# ---------------------------------------------------------------------------
# Phase 1 checklist (integration via API + engine reload)
# ---------------------------------------------------------------------------


class TestPhase1Checklist:
    """Maps 1:1 to the manual Phase 1 QA checklist (except GUI busy guard)."""

    def test_01_fresh_story_has_no_runs_until_save(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "fresh")

        assert not (story_dir / "runs").exists()
        ok, payload = TomeWeaverAPI.list_runs(name)
        assert ok is True
        assert payload["runs"] == []
        assert payload["active_run_id"] is None

    def test_02_restart_save_archives_then_clears_root(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "restart_save")
        seed_history(story_dir, 5, marker="A-")
        seed_local_memory(story_dir, "mem-A")

        ok, _ = TomeWeaverAPI.restart_story(name, save_before=True)
        assert ok is True

        root_history = json.loads((story_dir / "history.json").read_text(encoding="utf-8"))
        assert root_history == []

        manifest = load_manifest(story_dir)
        assert len(manifest["runs"]) == 1
        assert manifest["active_run_id"] is None

        run_id = next(iter(manifest["runs"]))
        snap = story_dir / "runs" / "snapshots" / run_id
        snap_history = json.loads((snap / "history.json").read_text(encoding="utf-8"))
        assert len(snap_history) == 5
        assert snap_history[4]["story_text"] == "Prose A-5"

        snap_mem = json.loads((snap / "memory.json").read_text(encoding="utf-8"))
        assert snap_mem["plot_ledger"][0]["event"] == "mem-A"

    def test_03_restart_discard_does_not_add_snapshot(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "restart_discard")
        seed_history(story_dir, 3, marker="B-")

        ok, _ = TomeWeaverAPI.restart_story(name, save_before=False)
        assert ok is True
        assert not (story_dir / "runs").exists()

        root_history = json.loads((story_dir / "history.json").read_text(encoding="utf-8"))
        assert root_history == []

    def test_04_and_05_switch_round_trip_preserves_both_runs(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "switch_roundtrip")

        seed_history(story_dir, 2, marker="OLD-")
        run_old, _ = archive_current_run(story_dir, label="Old Line")

        seed_history(story_dir, 4, marker="NEW-")
        run_new, _ = archive_current_run(story_dir, label="New Line")

        ok, _ = TomeWeaverAPI.switch_run(name, run_old)
        assert ok is True
        loaded = json.loads((story_dir / "history.json").read_text(encoding="utf-8"))
        assert loaded[1]["player_choice"] == "OLD-choice at 2"

        manifest = load_manifest(story_dir)
        assert manifest["active_run_id"] == run_old
        assert run_old in manifest["runs"]
        assert run_new in manifest["runs"]
        assert len(manifest["runs"]) == 2  # no auto-stash on switch

        ok, _ = TomeWeaverAPI.switch_run(name, run_new)
        assert ok is True
        loaded = json.loads((story_dir / "history.json").read_text(encoding="utf-8"))
        assert "NEW-choice at 4" in loaded[3]["player_choice"]

    def test_06_rename_survives_engine_reload(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "rename_reload")
        seed_history(story_dir, 2)
        run_id, _ = archive_current_run(story_dir, label="Before")

        ok, _ = TomeWeaverAPI.rename_run(name, run_id, "After Reload")
        assert ok is True

        engine = reload_engine(story_dir)
        assert len(engine.history) == 2  # root still has live line

        ok, payload = TomeWeaverAPI.list_runs(name)
        labels = [r["label"] for r in payload["runs"]]
        assert "After Reload" in labels

    def test_07_delete_prevents_switch_to_removed_run(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "delete_run")
        seed_history(story_dir, 2)
        run_id, _ = archive_current_run(story_dir, label="Doomed")

        ok, _ = TomeWeaverAPI.delete_run(name, run_id)
        assert ok is True
        assert not (story_dir / "runs" / "snapshots" / run_id).exists()

        ok, msg = TomeWeaverAPI.switch_run(name, run_id)
        assert ok is False
        assert "not found" in msg.lower()

    def test_08_dashboard_api_restart_save_and_discard(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "api_restart")

        seed_history(story_dir, 3, marker="save-")
        ok, _ = TomeWeaverAPI.restart_story(name, save_before=True)
        assert ok is True
        assert len(load_manifest(story_dir)["runs"]) == 1

        seed_history(story_dir, 2, marker="discard-")
        before = len(load_manifest(story_dir)["runs"])
        ok, _ = TomeWeaverAPI.restart_story(name, save_before=False)
        assert ok is True
        assert len(load_manifest(story_dir)["runs"]) == before

    def test_09_reopen_engine_matches_disk_after_switch(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "reopen")
        seed_history(story_dir, 2, marker="X-")
        run_id, _ = archive_current_run(story_dir, label="Saved")

        seed_history(story_dir, 5, marker="Y-")
        ok, _ = TomeWeaverAPI.switch_run(name, run_id)
        assert ok is True

        engine = reload_engine(story_dir)
        assert len(engine.history) == 2
        assert engine.history[1]["player_choice"] == "X-choice at 2"

        engine_again = reload_engine(story_dir)
        assert engine_again.history == engine.history

        manifest = load_manifest(story_dir)
        assert manifest["active_run_id"] == run_id

    def test_10_campaign_restart_and_switch_restore_chapters(self, library_cartridge):
        story_dir, name = library_cartridge("campaign", "campaign_runtree")
        seed_history(story_dir, 6, marker="C-")

        chapters = [
            {
                "chapter_number": 1,
                "title": "Chapter 1",
                "start_turn": 1,
                "end_turn": 3,
                "objectives": [{"goal": "Escape", "status": "COMPLETED"}],
            },
            {
                "chapter_number": 2,
                "title": "Chapter 2",
                "start_turn": 4,
                "end_turn": None,
                "objectives": [{"goal": "Find the key", "status": "ACTIVE"}],
            },
        ]
        write_json(story_dir / "chapters.json", chapters)
        run_id, _ = archive_current_run(story_dir, label="Campaign arc")

        ok, _ = TomeWeaverAPI.restart_story(name, save_before=False)
        assert ok is True

        reset = json.loads((story_dir / "chapters.json").read_text(encoding="utf-8"))
        assert len(reset) == 1
        assert reset[0]["chapter_number"] == 1
        assert reset[0]["start_turn"] == 1
        assert reset[0]["end_turn"] is None

        ok, _ = TomeWeaverAPI.switch_run(name, run_id)
        assert ok is True

        restored = json.loads((story_dir / "chapters.json").read_text(encoding="utf-8"))
        assert len(restored) == 2
        assert restored[1]["title"] == "Chapter 2"

        engine = reload_engine(story_dir, mode="campaign")
        assert engine.is_campaign is True
        assert len(engine.chapters) == 2

    def test_11_universe_switch_swaps_local_memory_not_shared(self, library_cartridge, monkeypatch, tmp_path):
        library = tmp_path / "library"
        universe = library / "SharedWorld"
        thread = universe / "DetectiveThread"
        thread.mkdir(parents=True)
        monkeypatch.setitem(__import__("config").INSTANCE_CONFIG, "adventures_dir", str(library.resolve()))

        from config import create_boilerplate_files, load_json_safely

        create_boilerplate_files(thread, "sandbox")
        setup = load_json_safely(thread / "setup.json", "setup.json")
        setup["is_universe_thread"] = True
        write_json(thread / "setup.json", setup)

        (universe / "master_setup.json").write_text(
            json.dumps({"universe_title": "Shared World"}), encoding="utf-8"
        )
        shared_payload = {
            "character_ledger": {"GlobalHero": {"ledger": [{"event": "universe-wide"}]}},
            "aliases": {},
        }
        write_json(universe / "shared_memory.json", shared_payload)

        seed_history(thread, 2, marker="localA-")
        seed_local_memory(thread, "local-A")
        run_a, _ = archive_current_run(thread, label="Thread run A")

        seed_history(thread, 3, marker="localB-")
        seed_local_memory(thread, "local-B")

        shared_before = json.loads((universe / "shared_memory.json").read_text(encoding="utf-8"))

        ok, _ = switch_run(thread, run_a)
        assert ok is True

        local_after = json.loads((thread / "memory.json").read_text(encoding="utf-8"))
        assert local_after["plot_ledger"][0]["event"] == "local-A"

        shared_after = json.loads((universe / "shared_memory.json").read_text(encoding="utf-8"))
        assert shared_after == shared_before

        engine = reload_engine(thread)
        assert engine.is_universe_thread is True
        assert "GlobalHero" in engine.memory["character_ledger"]["global"]
        assert engine.memory["plot_ledger"][0]["event"] == "local-A"


class TestForkAtTurn:
    """Phase 2: fork @ turn N archives, truncates, and heals chapters/RAG."""

    def test_can_fork_requires_committed_choice_and_future(self, engine_with_history):
        engine = engine_with_history(4, choices_per_turn=[None, "A", "B", "C"])

        assert engine.can_fork_at_turn(1) == (False, "This turn has no committed choice yet.")
        assert engine.can_fork_at_turn(4) == (False, "Cannot fork from the live timeline tail.")
        assert engine.can_fork_at_turn(2) == (True, "")
        assert engine.can_fork_at_turn(99) == (False, "Turn not found.")

    def test_fork_creates_parent_and_branch_snapshots(self, engine_with_history):
        engine = engine_with_history(5, choices_per_turn=[None, "A", "B", "C", "D"])
        engine.save_state()

        ok, msg, branch_id = engine.fork_at_turn(3)
        assert ok is True
        assert branch_id is not None
        assert "Turn 3" in msg

        assert len(engine.history) == 3
        assert [t["turn"] for t in engine.history] == [1, 2, 3]
        assert engine.history[2]["player_choice"] is None

        manifest = load_manifest(engine.adv_dir)
        assert len(manifest["runs"]) == 2
        assert manifest["active_run_id"] == branch_id
        assert "live_branch" not in manifest

        branch = manifest["runs"][branch_id]
        original_id = branch["parent_id"]
        original = manifest["runs"][original_id]
        assert original["run_kind"] == "original"
        assert branch["run_kind"] == "branch"
        assert original["fork_at_turn"] == 3
        assert branch["fork_at_turn"] == 3

        original_history = json.loads(
            (engine.adv_dir / "runs" / "snapshots" / original_id / "history.json").read_text(encoding="utf-8")
        )
        branch_history = json.loads(
            (engine.adv_dir / "runs" / "snapshots" / branch_id / "history.json").read_text(encoding="utf-8")
        )
        assert len(original_history) == 5
        assert len(branch_history) == 3
        assert branch_history[2]["player_choice"] is None

    def test_fork_truncates_without_renumbering(self, engine_with_history):
        engine = engine_with_history(5, choices_per_turn=[None, "A", "B", "C", "D"])
        engine.save_state()

        ok, msg, branch_id = engine.fork_at_turn(3)
        assert ok is True
        assert branch_id is not None
        assert "Turn 3" in msg

        assert len(engine.history) == 3
        assert [t["turn"] for t in engine.history] == [1, 2, 3]
        assert engine.history[2]["player_choice"] is None
        assert engine.history[1]["player_choice"] == "A"

        manifest = load_manifest(engine.adv_dir)
        original_id = manifest["runs"][branch_id]["parent_id"]
        node = manifest["runs"][original_id]
        assert node["fork_at_turn"] == 3
        assert manifest["active_run_id"] == branch_id

        snap_history = json.loads(
            (engine.adv_dir / "runs" / "snapshots" / original_id / "history.json").read_text(encoding="utf-8")
        )
        assert len(snap_history) == 5

    def test_fork_heals_chapters_and_plot_ledger(self, engine_with_history):
        engine = engine_with_history(
            6,
            choices_per_turn=[None, "a", "b", "c", "d", "e"],
            chapters=[
                {"chapter_number": 1, "title": "Act I", "start_turn": 1, "end_turn": 3},
                {"chapter_number": 2, "title": "Act II", "start_turn": 4, "end_turn": None},
            ],
            memory_flat={
                "plot_ledger": [
                    {"chapter_number": 1, "start_turn": 1, "end_turn": 3, "summary": "Part 1"},
                    {"chapter_number": 2, "start_turn": 4, "end_turn": 6, "summary": "Part 2"},
                ],
                "chapter_ledger": [{"chapter_number": 2, "summary": "Ch 2 summary"}],
            },
        )
        engine.save_state()

        ok, _, _ = engine.fork_at_turn(3)
        assert ok is True

        assert len(engine.chapters) == 1
        assert engine.chapters[0]["end_turn"] == 3
        assert len(engine.memory["plot_ledger"]) == 1
        assert engine.memory["plot_ledger"][0]["chapter_number"] == 1
        assert engine.memory["chapter_ledger"] == []

    def test_fork_clamps_entity_last_seen_turn(self, engine_with_history):
        engine = engine_with_history(5, choices_per_turn=[None, "a", "b", "c", "d"])
        engine.memory["character_ledger"]["local"]["Hero"] = {
            "characteristics": {},
            "ledger": [],
            "last_seen_turn": 5,
        }
        engine.save_state()

        ok, _, _ = engine.fork_at_turn(2)
        assert ok is True
        assert engine.memory["character_ledger"]["local"]["Hero"]["last_seen_turn"] == 2

    def test_api_fork_at_turn(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "api_fork")
        seed_history(story_dir, 4, marker="x-")

        ok, msg = TomeWeaverAPI.fork_at_turn(name, 2)
        assert ok is True
        assert "Forked" in msg

        history = json.loads((story_dir / "history.json").read_text(encoding="utf-8"))
        assert len(history) == 2
        assert history[1]["player_choice"] is None
        manifest = load_manifest(story_dir)
        assert len(manifest["runs"]) == 2
        assert manifest["active_run_id"] is not None

    def test_reloaded_engine_reflects_fork(self, engine_with_history):
        engine = engine_with_history(4, choices_per_turn=[None, "A", "B", "C"])
        engine.save_state()
        engine.fork_at_turn(2)

        reloaded = reload_engine(engine.adv_dir)
        assert len(reloaded.history) == 2
        assert reloaded.history[1]["player_choice"] is None
        assert reloaded.can_fork_at_turn(2) == (False, "This turn has no committed choice yet.")


class TestPhase3RestoreAndFork:
    def test_list_fork_points_from_snapshot(self, engine_with_history):
        engine = engine_with_history(5, choices_per_turn=[None, "a", "b", "c", "d"])
        engine.save_state()
        run_id, _ = archive_current_run(engine.adv_dir, label="Archive")

        ok, points = __import__("run_tree").list_fork_points_for_run(engine.adv_dir, run_id)
        assert ok is True
        assert points == [2, 3, 4]

    def test_runs_for_tree_display_nests_children(self, mock_adventure_dir):
        from run_tree import format_run_tree_line, runs_for_tree_display

        write_json(mock_adventure_dir / "history.json", [make_turn(1), make_turn(2, player_choice="x")])
        parent_id, _ = archive_current_run(mock_adventure_dir, label="Root")
        write_json(
            mock_adventure_dir / "history.json",
            [make_turn(1), make_turn(2, player_choice="a"), make_turn(3, player_choice="b")],
        )
        child_id, _ = archive_current_run(
            mock_adventure_dir,
            label="Child",
            parent_id=parent_id,
            fork_at_turn=2,
        )

        tree = runs_for_tree_display(mock_adventure_dir)
        assert len(tree) == 2
        child = next(r for r in tree if r["id"] == child_id)
        assert child["_depth"] == 1
        assert "↳" in format_run_tree_line(child)

    def test_restore_and_fork_loads_and_truncates_without_stash(self, engine_with_history):
        from run_tree import restore_and_fork

        engine = engine_with_history(5, choices_per_turn=[None, "a", "b", "c", "d"])
        engine.save_state()
        run_id, _ = archive_current_run(engine.adv_dir, label="Old path")

        write_json(
            engine.adv_dir / "history.json",
            [make_turn(i, player_choice=(None if i == 1 else "live")) for i in range(1, 4)],
        )

        ok, msg = restore_and_fork(engine.adv_dir, run_id, 3)
        assert ok is True
        assert "Turn 3" in msg

        history = json.loads((engine.adv_dir / "history.json").read_text(encoding="utf-8"))
        assert len(history) == 3
        assert history[2]["player_choice"] is None

        manifest = load_manifest(engine.adv_dir)
        assert len(manifest["runs"]) == 3  # saved archive + fork parent + fork branch

    def test_api_restore_and_fork(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "restore_fork")
        seed_history(story_dir, 4, marker="z-")
        run_id, _ = archive_current_run(story_dir, label="Saved")

        seed_history(story_dir, 2, marker="live-")
        ok, msg = TomeWeaverAPI.restore_and_fork(name, run_id, 2)
        assert ok is True

        history = json.loads((story_dir / "history.json").read_text(encoding="utf-8"))
        assert len(history) == 2
        assert history[1]["player_choice"] is None

    def test_get_run_tree_rows_marks_active_fork_branch(self, engine_with_history):
        from run_tree import get_run_tree_rows

        engine = engine_with_history(5, choices_per_turn=[None, "a", "b", "c", "d"])
        engine.save_state()
        ok, _, branch_id = engine.fork_at_turn(2)
        assert ok is True

        rows, default_id = get_run_tree_rows(engine.adv_dir)
        assert len(rows) == 2
        assert default_id == branch_id
        active_rows = [r for r in rows if r["is_live"]]
        assert len(active_rows) == 1
        assert active_rows[0]["id"] == branch_id
        assert "playing now" in active_rows[0]["line"]

    def test_get_run_tree_rows_defaults_to_active_archive(self, engine_with_history):
        from run_tree import get_run_tree_rows

        engine = engine_with_history(3, choices_per_turn=[None, "a", "b"])
        engine.save_state()
        run_id, _ = archive_current_run(engine.adv_dir, label="Saved line")
        switch_run(engine.adv_dir, run_id)

        rows, default_id = get_run_tree_rows(engine.adv_dir)
        assert default_id == run_id
        assert sum(1 for r in rows if r["is_live"]) == 1
        assert next(r for r in rows if r["is_live"])["id"] == run_id

    def test_switch_between_fork_branches_preserves_progress(self, engine_with_history):
        from run_tree import switch_run

        engine = engine_with_history(5, choices_per_turn=[None, "a", "b", "c", "d"])
        engine.save_state()
        ok, _, branch_id = engine.fork_at_turn(2)
        assert ok is True

        original_id = load_manifest(engine.adv_dir)["runs"][branch_id]["parent_id"]

        engine.history[1]["player_choice"] = "alt-path"
        engine.history.append(make_turn(3, player_choice="branch-3", story_text="Branch turn 3"))
        engine.save_state()

        ok, _ = switch_run(engine.adv_dir, original_id)
        assert ok is True
        assert load_manifest(engine.adv_dir)["active_run_id"] == original_id

        engine = reload_engine(engine.adv_dir)
        engine.history.append(make_turn(6, player_choice="orig-6", story_text="Original turn 6"))
        engine.save_state()

        ok, _ = switch_run(engine.adv_dir, branch_id)
        assert ok is True

        branch_snap = json.loads(
            (engine.adv_dir / "runs" / "snapshots" / branch_id / "history.json").read_text(encoding="utf-8")
        )
        assert len(branch_snap) == 3
        assert branch_snap[1]["player_choice"] == "alt-path"
        assert branch_snap[2]["player_choice"] == "branch-3"

        reloaded = reload_engine(engine.adv_dir)
        assert len(reloaded.history) == 3
        assert reloaded.history[2]["player_choice"] == "branch-3"

        original_snap = json.loads(
            (engine.adv_dir / "runs" / "snapshots" / original_id / "history.json").read_text(encoding="utf-8")
        )
        assert len(original_snap) == 6
        assert original_snap[5]["player_choice"] == "orig-6"
