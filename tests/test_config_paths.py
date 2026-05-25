"""Configurable adventures library path and universe root discovery."""

import json

import pytest

from config import (
    ENGINE_CONFIG,
    find_universe_root,
    get_adventures_dir,
    get_default_adventures_dir,
)
from api import get_adv_dir, get_index_file


class TestAdventuresDirResolution:
    """``adventures_dir`` in engine_config resolves to a usable library root."""

    def test_default_adventures_dir_when_unset(self, monkeypatch):
        # Arrange
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", "")

        # Act
        resolved = get_adventures_dir()

        # Assert
        assert resolved == get_default_adventures_dir()
        assert resolved.is_dir()

    def test_custom_absolute_adventures_dir(self, monkeypatch, tmp_path):
        # Arrange
        custom = tmp_path / "my_real_stories"
        custom.mkdir()
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(custom))

        # Act
        resolved = get_adventures_dir()

        # Assert
        assert resolved == custom.resolve()
        assert get_adv_dir() == custom.resolve()
        assert get_index_file() == custom.resolve() / "index.json"

    def test_relative_adventures_dir_resolves_against_user_root(self, monkeypatch, tmp_path):
        # Arrange
        from config import USER_ROOT

        rel_name = "custom_library"
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", rel_name)

        # Act
        resolved = get_adventures_dir()

        # Assert
        assert resolved == (USER_ROOT / rel_name).resolve()
        assert resolved.is_dir()


class TestFindUniverseRoot:
    """Universe detection walks up to the configured adventures library root."""

    def test_finds_master_setup_in_nested_thread(self, monkeypatch, tmp_path):
        # Arrange
        library = tmp_path / "library"
        universe = library / "SharedWorld"
        thread = universe / "DetectiveThread"
        thread.mkdir(parents=True)
        (universe / "master_setup.json").write_text(
            json.dumps({"universe_title": "Shared World"}), encoding="utf-8"
        )
        (thread / "setup.json").write_text("{}", encoding="utf-8")
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(library))

        # Act
        root = find_universe_root(thread)

        # Assert
        assert root == universe.resolve()

    def test_returns_none_when_no_master_setup_in_tree(self, monkeypatch, tmp_path):
        # Arrange
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(tmp_path / "library"))
        orphan = tmp_path / "elsewhere" / "story"
        orphan.mkdir(parents=True)
        (orphan / "setup.json").write_text("{}", encoding="utf-8")

        # Act
        root = find_universe_root(orphan)

        # Assert
        assert root is None
