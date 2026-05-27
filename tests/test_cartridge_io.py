"""ZIP cartridge export/import and library CRUD API tests."""

import json
import zipfile

import pytest

from api import TomeWeaverAPI, get_adv_dir
from conftest import assert_cartridge_consistent, make_turn, write_json


class TestZipCartridgeRoundTrip:
    def test_export_import_preserves_history(self, library_cartridge, tmp_path):
        story_dir, name = library_cartridge("sandbox", "zip_roundtrip")
        setup = json.loads((story_dir / "setup.json").read_text(encoding="utf-8"))
        setup["title"] = "Zip Roundtrip"
        write_json(story_dir / "setup.json", setup)
        history = [
            make_turn(1, player_choice=None),
            make_turn(2, player_choice="Enter the cave", story_text="Deeper darkness."),
        ]
        write_json(story_dir / "history.json", history)

        zip_path = tmp_path / "cartridge.zip"
        ok, msg = TomeWeaverAPI.export_to_zip(name, zip_path)
        assert ok is True, msg

        ok, imported_name = TomeWeaverAPI.import_from_zip(str(zip_path))
        assert ok is True
        assert imported_name == "Zip Roundtrip"

        imported_dir = get_adv_dir() / imported_name
        reloaded = json.loads((imported_dir / "history.json").read_text(encoding="utf-8"))
        assert len(reloaded) == 2
        assert reloaded[1]["player_choice"] == "Enter the cave"

    def test_export_skips_index_json(self, library_cartridge, tmp_path):
        story_dir, name = library_cartridge("sandbox", "zip_no_index")
        write_json(story_dir / "index.json", {"stories": []})
        write_json(story_dir / "history.json", [make_turn(1)])

        zip_path = tmp_path / "out.zip"
        TomeWeaverAPI.export_to_zip(name, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            assert not any("index.json" in n for n in zf.namelist())

    def test_import_rejects_invalid_zip(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_text("not a zip", encoding="utf-8")
        ok, msg = TomeWeaverAPI.import_from_zip(str(bad))
        assert ok is False

    def test_import_collision_appends_counter(self, library_cartridge, tmp_path):
        story_dir, name = library_cartridge("sandbox", "CollisionStory")
        setup = json.loads((story_dir / "setup.json").read_text(encoding="utf-8"))
        setup["title"] = "CollisionStory"
        write_json(story_dir / "setup.json", setup)
        write_json(story_dir / "history.json", [make_turn(1)])

        zip_path = tmp_path / "dup.zip"
        TomeWeaverAPI.export_to_zip(name, zip_path)

        ok, imported = TomeWeaverAPI.import_from_zip(str(zip_path))
        assert ok is True
        assert imported == "CollisionStory (1)"


class TestLibraryCrud:
    def test_create_story_writes_boilerplate(self, set_adventures_dir):
        set_adventures_dir()
        ok, rel = TomeWeaverAPI.create_story("My Tale", "Author", "sandbox")
        assert ok is True
        story_dir = get_adv_dir() / rel
        assert (story_dir / "setup.json").exists()
        assert (story_dir / "system_prompt.txt").exists()
        setup = json.loads((story_dir / "setup.json").read_text(encoding="utf-8"))
        assert setup["title"] == "My Tale"

    def test_create_universe_writes_master_files(self, set_adventures_dir):
        set_adventures_dir()
        ok, rel = TomeWeaverAPI.create_universe("Shared World", "Author", "Epic", "Ancient lore")
        assert ok is True
        univ_dir = get_adv_dir() / rel
        assert (univ_dir / "master_setup.json").exists()
        assert (univ_dir / "shared_memory.json").exists()

    def test_rename_story_updates_folder_and_title(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "OldName")
        ok, new_rel = TomeWeaverAPI.rename_story(name, "Renamed Tale")
        assert ok is True
        assert new_rel == "Renamed Tale"
        setup = json.loads((get_adv_dir() / new_rel / "setup.json").read_text(encoding="utf-8"))
        assert setup["title"] == "Renamed Tale"
        assert not story_dir.exists()

    def test_move_story_into_subfolder(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "Movable")
        ok, new_rel = TomeWeaverAPI.move_story(name, "Archive")
        assert ok is True
        assert new_rel == "Archive/Movable"
        assert (get_adv_dir() / new_rel / "setup.json").exists()
        assert not story_dir.exists()

    def test_delete_story_removes_folder(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "ToDelete")
        ok, msg = TomeWeaverAPI.delete_story(name)
        assert ok is True
        assert not story_dir.exists()

    def test_create_story_in_universe_sets_thread_flag(self, set_adventures_dir):
        set_adventures_dir()
        TomeWeaverAPI.create_universe("Univ", "A", "Dark", "Lore")
        ok, rel = TomeWeaverAPI.create_story("Thread One", "A", "sandbox", parent_dir="Univ")
        assert ok is True
        setup = json.loads((get_adv_dir() / rel / "setup.json").read_text(encoding="utf-8"))
        assert setup.get("is_universe_thread") is True
