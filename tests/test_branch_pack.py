"""Branch pack export/import for run-tree sharing."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from branch_pack import (
    compute_setup_fingerprint,
    export_branch_pack,
    import_branch_pack,
    inspect_zip_cartridge,
    list_importable_stories,
)
from conftest import make_turn, write_json
from run_tree import load_manifest, switch_run


class TestBranchPack:
    def test_export_import_round_trip(self, engine_with_history, tmp_path):
        engine = engine_with_history(5, choices_per_turn=[None, "a", "b", "c", "d"])
        engine.save_state()
        ok, _, branch_id = engine.fork_at_turn(2)
        assert ok is True

        engine.history[1]["player_choice"] = "friend-path"
        engine.history.append(make_turn(3, player_choice="only-on-branch"))
        engine.save_state()

        zip_path = tmp_path / "shared.zip"
        ok, msg = export_branch_pack(
            engine.adv_dir,
            [branch_id],
            zip_path,
            shared_by="Alice",
        )
        assert ok is True
        assert zip_path.exists()

        kind, pack = inspect_zip_cartridge(zip_path)
        assert kind == "branch_pack"
        assert pack["shared_by"] == "Alice"
        assert len(pack["nodes"]) == 2  # branch + parent ancestor

        import shutil

        recipient = engine.adv_dir.parent / "recipient_story"
        recipient.mkdir()
        for fname in ("setup.json", "system_prompt.txt", "history.json", "chapters.json", "memory.json"):
            src = engine.adv_dir / fname
            if src.exists():
                shutil.copy2(src, recipient / fname)
        write_json(
            recipient / "history.json",
            [make_turn(1), make_turn(2, player_choice="my-local-choice")],
        )

        ok, msg = import_branch_pack(recipient, zip_path, label_prefix="[Alice] ")
        assert ok is True

        manifest = load_manifest(recipient)
        assert len(manifest["runs"]) == 2
        labels = [r["label"] for r in manifest["runs"].values()]
        assert any(label.startswith("[Alice]") for label in labels)

        imported_branch = next(r for r in manifest["runs"].values() if r.get("run_kind") == "branch")
        snap_hist = json.loads(
            (recipient / "runs" / "snapshots" / imported_branch["id"] / "history.json").read_text(encoding="utf-8")
        )
        assert snap_hist[1]["player_choice"] == "friend-path"
        assert snap_hist[2]["player_choice"] == "only-on-branch"

    def test_switch_after_import_loads_shared_timeline(self, engine_with_history, tmp_path):
        engine = engine_with_history(4, choices_per_turn=[None, "a", "b", "c"])
        engine.save_state()
        ok, _, branch_id = engine.fork_at_turn(2)
        assert ok is True

        zip_path = tmp_path / "pack.zip"
        export_branch_pack(engine.adv_dir, [branch_id], zip_path, shared_by="Bob")

        recipient = engine.adv_dir.parent / "my_copy"
        recipient.mkdir()
        import shutil

        for fname in ("setup.json", "system_prompt.txt"):
            shutil.copy2(engine.adv_dir / fname, recipient / fname)
        write_json(recipient / "history.json", [make_turn(1), make_turn(2, player_choice="mine")])
        write_json(recipient / "chapters.json", [])
        write_json(recipient / "memory.json", {})

        ok, _ = import_branch_pack(recipient, zip_path)
        assert ok is True

        imported = next(r for r in load_manifest(recipient)["runs"].values() if r.get("run_kind") == "branch")
        ok, _ = switch_run(recipient, imported["id"])
        assert ok is True
        loaded = json.loads((recipient / "history.json").read_text(encoding="utf-8"))
        assert len(loaded) == 2
        assert loaded[1]["player_choice"] is None

    def test_inspect_full_cartridge(self, mock_adventure_dir, tmp_path):
        import zipfile

        zip_path = tmp_path / "full.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("setup.json", "{}")
            zf.writestr("system_prompt.txt", "prompt")

        kind, _ = inspect_zip_cartridge(zip_path)
        assert kind == "full"

    def test_setup_fingerprint_stable(self, mock_adventure_dir):
        from config import load_json_safely

        setup = load_json_safely(mock_adventure_dir / "setup.json", "setup.json")
        a = compute_setup_fingerprint(setup)
        b = compute_setup_fingerprint(setup)
        assert a["digest"] == b["digest"]

    def test_list_importable_stories_marks_compatible(self, engine_with_history, tmp_path, monkeypatch):
        from config import INSTANCE_CONFIG

        library = tmp_path / "library"
        library.mkdir()
        monkeypatch.setitem(INSTANCE_CONFIG, "adventures_dir", str(library))

        story_a = library / "StoryA"
        story_a.mkdir()
        import shutil

        for fname in ("setup.json", "system_prompt.txt"):
            shutil.copy2(engine_with_history(1).adv_dir / fname, story_a / fname)

        story_b = library / "StoryB"
        story_b.mkdir()
        shutil.copy2(story_a / "setup.json", story_b / "setup.json")
        setup = json.loads((story_b / "setup.json").read_text(encoding="utf-8"))
        setup["title"] = "Different Title"
        write_json(story_b / "setup.json", setup)

        fp = compute_setup_fingerprint(json.loads((story_a / "setup.json").read_text(encoding="utf-8")))
        stories = list_importable_stories(library, fp)
        assert len(stories) == 2
        compat = [s for s in stories if s["compatible"]]
        assert len(compat) == 1
        assert compat[0]["folder_name"] == "StoryA"
