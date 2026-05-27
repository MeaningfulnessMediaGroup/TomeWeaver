"""Deep entity rename analyze/execute and legacy run-tree migration."""

import json

import pytest

from conftest import build_engine, make_turn, write_json
from run_tree import archive_current_run, load_manifest, migrate_legacy_fork_state, save_manifest


class TestDeepRename:
    def test_analyze_finds_name_in_history(self, engine_with_history):
        engine = engine_with_history(2, choices_per_turn=[None, "Visit Aldric"])
        engine.history[1]["story_text"] = "Aldric waits by the gate."

        affected = engine.analyze_deep_rename("Aldric", scope="local")
        assert affected["ram"] is True
        assert affected["files"] == []

    def test_execute_rename_updates_history_on_disk(self, engine_with_history):
        engine = engine_with_history(2, choices_per_turn=[None, "Talk to Aldric"])
        engine.history[1]["story_text"] = "Aldric speaks softly."

        engine.execute_deep_rename("Aldric", "Baldric", scope="local", authorized_ram=True, authorized_files=[])

        assert "Baldric" in engine.history[1]["story_text"]
        assert "Aldric" not in engine.history[1]["story_text"]

        disk = json.loads((engine.adv_dir / "history.json").read_text(encoding="utf-8"))
        assert "Baldric" in disk[1]["story_text"]

    def test_execute_rename_updates_memory_ledger_strings(self, sandbox_engine):
        sandbox_engine.memory.setdefault("character_ledger", {})["local"] = {
            "Elena": {
                "characteristics": {"Role": "Scout"},
                "ledger": ["Elena found the trail"],
                "state": "active",
            }
        }
        sandbox_engine.execute_deep_rename(
            "Elena", "Helena", scope="local", authorized_ram=True, authorized_files=[]
        )
        local = sandbox_engine.memory["character_ledger"]["local"]
        assert "Elena" in local
        assert "Helena found the trail" in local["Elena"]["ledger"][0]


class TestLegacyRunTreeMigration:
    def test_migrate_live_branch_creates_branch_snapshot(self, mock_adventure_dir):
        write_json(
            mock_adventure_dir / "history.json",
            [make_turn(1), make_turn(2, player_choice="path")],
        )
        parent_id, _ = __import__("run_tree").archive_current_run(
            mock_adventure_dir, label="Parent"
        )
        write_json(
            mock_adventure_dir / "history.json",
            [make_turn(1), make_turn(2, player_choice="branch")],
        )
        manifest = load_manifest(mock_adventure_dir)
        manifest["live_branch"] = {
            "forked_from_run_id": parent_id,
            "forked_at_turn": 2,
        }
        manifest["active_run_id"] = None
        save_manifest(mock_adventure_dir, manifest)

        migrate_legacy_fork_state(mock_adventure_dir)

        migrated = load_manifest(mock_adventure_dir)
        assert "live_branch" not in migrated
        assert migrated.get("active_run_id") is not None
        assert any(
            r.get("run_kind") == "branch" and r.get("fork_at_turn") == 2
            for r in migrated.get("runs", {}).values()
        )

    def test_migrate_links_existing_branch_node(self, mock_adventure_dir):
        from run_tree import archive_current_run

        write_json(
            mock_adventure_dir / "history.json",
            [make_turn(1), make_turn(2, player_choice="x")],
        )
        parent_id, _ = archive_current_run(mock_adventure_dir, label="Parent")
        branch_id, _ = archive_current_run(
            mock_adventure_dir,
            label="Existing branch",
            parent_id=parent_id,
            fork_at_turn=2,
            run_kind="branch",
        )

        manifest = load_manifest(mock_adventure_dir)
        manifest["live_branch"] = {
            "forked_from_run_id": parent_id,
            "forked_at_turn": 2,
        }
        manifest["active_run_id"] = None
        save_manifest(mock_adventure_dir, manifest)

        migrate_legacy_fork_state(mock_adventure_dir)
        migrated = load_manifest(mock_adventure_dir)
        assert migrated.get("active_run_id") == branch_id
