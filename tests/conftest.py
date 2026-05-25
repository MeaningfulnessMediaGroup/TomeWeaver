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
    """Write JSON to a path using the same atomic helper as production code.

    Args:
        path: Destination file path.
        data: JSON-serializable object.
    """
    save_json_atomically(data, path)


@pytest.fixture
def mock_adventure_dir(tmp_path):
    """Temporary sandbox cartridge with boilerplate setup + system prompt."""
    adv = tmp_path / "mock_adventure"
    adv.mkdir()
    create_boilerplate_files(adv, "sandbox")
    return adv


@pytest.fixture
def sandbox_engine(mock_adventure_dir):
    """Empty SandboxEngine on a disposable adventure folder."""
    setup = load_json_safely(mock_adventure_dir / "setup.json", "setup.json")
    return SandboxEngine(mock_adventure_dir, setup)


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

        write_json(mock_adventure_dir / "history.json", history)

        if chapters is not None:
            write_json(mock_adventure_dir / "chapters.json", chapters)
        else:
            write_json(
                mock_adventure_dir / "chapters.json",
                [
                    {
                        "chapter_number": 1,
                        "title": "Chapter One",
                        "start_turn": 1,
                        "end_turn": turn_count if turn_count else None,
                    }
                ],
            )

        if memory_flat is not None:
            write_json(mock_adventure_dir / "memory.json", memory_flat)

        setup = load_json_safely(mock_adventure_dir / "setup.json", "setup.json")
        return SandboxEngine(mock_adventure_dir, setup)

    return _factory
