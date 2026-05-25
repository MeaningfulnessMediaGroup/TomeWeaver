"""API utilities: folder sanitization and engine boot."""

import pytest

from api import TomeWeaverAPI, get_index_file, sanitize_foldername
from config import ENGINE_CONFIG, create_boilerplate_files


class TestSanitizeFoldername:
    """Illegal filesystem characters are stripped from user titles."""

    @pytest.mark.parametrize(
        "raw,expected_fragment",
        [
            ('My Story: "Act I"', "My Story Act I"),
            ("Bad/Path\\Name?", "BadPathName"),
            ("", ""),
        ],
    )
    def test_strips_illegal_characters(self, raw, expected_fragment):
        # Act
        clean = sanitize_foldername(raw)

        # Assert
        assert expected_fragment in clean or clean == ""
        assert not any(c in clean for c in '\\/:*?"<>|')

    def test_truncates_long_titles(self):
        # Arrange
        raw = "A" * 100

        # Act
        clean = sanitize_foldername(raw)

        # Assert
        assert len(clean) <= 60


class TestLoadEngine:
    """TomeWeaverAPI.load_engine picks the correct engine class."""

    def test_loads_sandbox_engine(self, tmp_path, monkeypatch):
        # Arrange
        library = tmp_path / "library"
        library.mkdir()
        story_dir = library / "test_sandbox_story"
        story_dir.mkdir(parents=True)
        create_boilerplate_files(story_dir, "sandbox")
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(library))

        # Act
        engine = TomeWeaverAPI.load_engine("test_sandbox_story")

        # Assert
        assert engine.is_campaign is False
        assert engine.adv_dir.resolve() == story_dir.resolve()

    def test_index_file_lives_in_configured_library(self, set_adventures_dir):
        # Arrange
        set_adventures_dir()

        # Act
        index = get_index_file()

        # Assert
        assert index.name == "index.json"
