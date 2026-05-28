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
    """Patch INSTANCE_CONFIG adventures_dir to a disposable library root."""

    def _apply(custom_path=None):
        from config import INSTANCE_CONFIG

        if custom_path is None:
            custom_path = tmp_path / "library"
            custom_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setitem(INSTANCE_CONFIG, "adventures_dir", str(Path(custom_path).resolve()))

    return _apply


@pytest.fixture
def library_cartridge(tmp_path, monkeypatch):
    """Factory: disposable story folder registered in a patched adventures library."""

    def _make(mode="sandbox", folder_name=None):
        from config import INSTANCE_CONFIG, create_boilerplate_files

        library = tmp_path / "library"
        library.mkdir(parents=True, exist_ok=True)
        name = folder_name or f"test_{mode}"
        story_dir = library / name
        story_dir.mkdir(parents=True, exist_ok=True)
        create_boilerplate_files(story_dir, mode)
        monkeypatch.setitem(INSTANCE_CONFIG, "adventures_dir", str(library.resolve()))
        return story_dir, name

    return _make


def valid_turn_payload(turn_num=1, **overrides):
    """Minimal turn dict that satisfies ``validate_turn_schema``."""
    base = {
        "turn": turn_num,
        "story_text": f"Story prose for turn {turn_num}.",
        "pov_character": "Hero",
        "location": "Test Loc",
        "input_type": "choice",
        "choices": ["Option A", "Option B"],
        "text_prompt": None,
        "is_game_over": False,
        "player_choice": None,
        "narrative_bridge": "",
    }
    base.update(overrides)
    return base


def assert_cartridge_consistent(engine, *, check_disk=True):
    """Assert Master Clock, chapter bounds, and optional on-disk parity."""
    history = engine.history or []
    turn_set = set()
    if history:
        turns = [int(t.get("turn", 0)) for t in history]
        expected = list(range(turns[0], turns[0] + len(turns)))
        assert turns == expected, f"Non-contiguous Master Clock: {turns}"
        assert engine.get_next_turn_number() == turns[-1] + 1
        turn_set = set(turns)

    max_turn = max(turn_set, default=0)
    for chap in engine.chapters:
        start = chap.get("start_turn")
        end = chap.get("end_turn")
        if start is not None:
            start = int(start)
            if turn_set:
                assert start in turn_set, (
                    f"Chapter {chap.get('chapter_number')} start_turn {start} "
                    f"not in history turns {sorted(turn_set)}"
                )
        if end is not None and start is not None:
            end = int(end)
            assert end >= start
            if history:
                assert end <= max_turn
                assert end in turn_set, (
                    f"Chapter {chap.get('chapter_number')} end_turn {end} "
                    f"not in history turns {sorted(turn_set)}"
                )

    if check_disk and (engine.adv_dir / "history.json").exists():
        disk = load_json_safely(engine.adv_dir / "history.json", "history.json")
        assert disk == history

    if check_disk and (engine.adv_dir / "chapters.json").exists():
        disk_chapters = load_json_safely(engine.adv_dir / "chapters.json", "chapters.json")
        assert disk_chapters == engine.chapters


@pytest.fixture
def mock_llm_response(monkeypatch):
    """Patch ``get_llm_response`` on engine modules (imported at module level)."""

    def _apply(payload_factory=None):
        import base_engine
        import campaign
        import llm
        import sandbox

        def factory(*_args, **_kwargs):
            if callable(payload_factory):
                turn = payload_factory(*_args, **_kwargs)
            else:
                turn = payload_factory or valid_turn_payload(turn_num=99)
            return turn, None, json.dumps(turn)

        for mod in (llm, base_engine, campaign):
            if hasattr(mod, "get_llm_response"):
                monkeypatch.setattr(mod, "get_llm_response", factory)
        return factory

    return _apply


@pytest.fixture
def universe_library(tmp_path, monkeypatch):
    """Shared universe + thread story under a patched adventures library."""

    def _make(*, thread_name="DetectiveThread"):
        from config import INSTANCE_CONFIG, create_boilerplate_files

        library = tmp_path / "library"
        universe = library / "NeonBasin"
        thread = universe / thread_name
        universe.mkdir(parents=True)
        thread.mkdir(parents=True)

        write_json(
            universe / "master_setup.json",
            {
                "universe_title": "Neon Basin",
                "tone": "Cyberpunk noir",
                "lore_and_rules": "Global canon: the city never sleeps.",
            },
        )
        write_json(
            universe / "shared_memory.json",
            {
                "character_ledger": {},
                "location_ledger": {
                    "The Gilded Tankard": {
                        "characteristics": {"Status": "intact"},
                        "ledger": [],
                        "state": "active",
                        "last_seen_turn": 1,
                    }
                },
                "artifact_ledger": {},
                "faction_ledger": {},
                "aliases": {
                    "character_ledger": {},
                    "location_ledger": {},
                    "artifact_ledger": {},
                    "faction_ledger": {},
                },
            },
        )

        create_boilerplate_files(thread, "sandbox")
        setup = load_json_safely(thread / "setup.json", "setup.json")
        setup["is_universe_thread"] = True
        setup["title"] = "The Detective"
        write_json(thread / "setup.json", setup)

        monkeypatch.setitem(INSTANCE_CONFIG, "adventures_dir", str(library.resolve()))
        rel = f"NeonBasin/{thread_name}"
        return library, universe, thread, rel

    return _make
