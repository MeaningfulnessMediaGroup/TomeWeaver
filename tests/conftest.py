"""
Pytest fixtures for headless BaseEngine / SandboxEngine tests.

Uses tempfile-backed adventure directories so real /adventures/ cartridges are never touched.

Run from repo root with the project venv (same as Start_TomeWeaver.bat):
  venv\\Scripts\\python.exe -m pytest tests/ -v
  or: Run_Tests.bat
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from campaign import CampaignEngine
from config import create_boilerplate_files, load_json_safely, save_json_atomically
from sandbox import SandboxEngine


def make_turn(
    turn_num,
    *,
    story_text=None,
    player_choice=None,
    narrative_bridge="",
    location="Test Loc",
    pov_character="Hero",
):
    """Minimal valid history turn for timeline surgery tests."""
    return {
        "turn": turn_num,
        "story_text": story_text or f"Story prose for turn {turn_num}.",
        "pov_character": pov_character,
        "location": location,
        "input_type": "choice",
        "choices": ["Option A", "Option B"],
        "text_prompt": None,
        "is_game_over": False,
        "player_choice": player_choice,
        "narrative_bridge": narrative_bridge,
    }


def write_json(path, data):
    """Write JSON atomically (same helper the engine uses on disk)."""
    save_json_atomically(data, path)


def build_engine(adv_dir, *, history=None, chapters=None, memory_flat=None, mode="sandbox"):
    """Construct a fresh engine from on-disk cartridge files."""
    if history is not None:
        write_json(adv_dir / "history.json", history)
    if chapters is not None:
        write_json(adv_dir / "chapters.json", chapters)
    if memory_flat is not None:
        write_json(adv_dir / "memory.json", memory_flat)

    setup = load_json_safely(adv_dir / "setup.json", "setup.json")
    if mode == "campaign":
        return CampaignEngine(adv_dir, setup)
    return SandboxEngine(adv_dir, setup)


@pytest.fixture
def mock_adventure_dir(tmp_path):
    """Temporary sandbox cartridge with boilerplate setup + system prompt."""
    adv = tmp_path / "mock_adventure"
    adv.mkdir()
    create_boilerplate_files(adv, "sandbox")
    return adv


@pytest.fixture
def mock_campaign_dir(tmp_path):
    """Temporary campaign cartridge with plot_outline from template."""
    adv = tmp_path / "mock_campaign"
    adv.mkdir()
    create_boilerplate_files(adv, "campaign")
    return adv


@pytest.fixture
def sandbox_engine(mock_adventure_dir):
    """Empty SandboxEngine on a disposable adventure folder."""
    setup = load_json_safely(mock_adventure_dir / "setup.json", "setup.json")
    return SandboxEngine(mock_adventure_dir, setup)


@pytest.fixture
def campaign_engine(mock_campaign_dir):
    """Empty CampaignEngine on a disposable campaign folder."""
    setup = load_json_safely(mock_campaign_dir / "setup.json", "setup.json")
    return CampaignEngine(mock_campaign_dir, setup)


@pytest.fixture
def engine_with_history(mock_adventure_dir):
    """
    Factory: build a SandboxEngine with N turns, optional chapters, and memory.

    Usage:
        engine = engine_with_history(turn_count=5, chapters=[...], memory={...})
    """

    def _factory(
        turn_count=5,
        *,
        chapters=None,
        memory_flat=None,
        choices_per_turn=None,
    ):
        history = []
        for i in range(1, turn_count + 1):
            pc = None if i == 1 else f"Chose path at turn {i - 1}"
            if choices_per_turn and i - 1 < len(choices_per_turn):
                pc = choices_per_turn[i - 1]
            history.append(make_turn(i, player_choice=pc))

        return build_engine(
            mock_adventure_dir,
            history=history,
            chapters=chapters,
            memory_flat=memory_flat,
            mode="sandbox",
        )

    return _factory


@pytest.fixture
def set_decay_threshold(monkeypatch):
    """Patch ENGINE_CONFIG memory_decay_threshold for RAG visibility tests."""

    def _apply(threshold):
        from config import ENGINE_CONFIG

        monkeypatch.setitem(ENGINE_CONFIG, "memory_decay_threshold", threshold)

    return _apply


@pytest.fixture
def set_adventures_dir(monkeypatch, tmp_path):
    """Patch ENGINE_CONFIG adventures_dir to a disposable library root."""

    def _apply(custom_path=None):
        from config import ENGINE_CONFIG

        if custom_path is None:
            custom_path = tmp_path / "library"
            custom_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(Path(custom_path).resolve()))

    return _apply


@pytest.fixture
def library_cartridge(tmp_path, monkeypatch):
    """Factory: disposable story folder registered in a patched adventures library."""

    def _make(mode="sandbox", folder_name=None):
        from config import ENGINE_CONFIG, create_boilerplate_files

        library = tmp_path / "library"
        library.mkdir(parents=True, exist_ok=True)
        name = folder_name or f"test_{mode}"
        story_dir = library / name
        story_dir.mkdir(parents=True, exist_ok=True)
        create_boilerplate_files(story_dir, mode)
        monkeypatch.setitem(ENGINE_CONFIG, "adventures_dir", str(library.resolve()))
        return story_dir, name

    return _make
