"""Shared universe propagation, slice_thread, and migration API."""

import json

import pytest

from api import TomeWeaverAPI, get_adv_dir
from conftest import assert_cartridge_consistent, build_engine, make_turn, write_json


class TestUniversePromptMerge:
    def test_build_messages_merges_global_lore(self, universe_library):
        _, _univ, thread, _rel = universe_library()
        engine = build_engine(thread, mode="sandbox")
        write_json(
            thread / "history.json",
            [make_turn(1, player_choice=None), make_turn(2, player_choice="Investigate")],
        )
        engine = build_engine(thread, mode="sandbox")

        messages = engine.build_messages(target_turn=3)
        blob = messages[0]["content"]
        assert "GLOBAL UNIVERSE LORE" in blob or "city never sleeps" in blob

    def test_global_entity_in_prompt_when_active(self, universe_library):
        _, universe, thread, _rel = universe_library()
        engine = build_engine(
            thread,
            history=[make_turn(1, player_choice=None), make_turn(2, player_choice="Go")],
            mode="sandbox",
        )
        engine.memory["location_ledger"]["global"] = {
            "The Gilded Tankard": {
                "characteristics": {"Status": "intact"},
                "ledger": [],
                "state": "active",
                "last_seen_turn": 2,
            }
        }
        engine.memory["global_states"] = {
            "The Gilded Tankard": {"state": "active", "last_seen_turn": 2},
        }

        messages = engine.build_messages(target_turn=3)
        content = " ".join(m.get("content", "") for m in messages)
        assert "Gilded Tankard" in content or "Tankard" in content


class TestSliceThread:
    def _seed_two_chapter_story(self, adv_dir):
        history = []
        for i in range(1, 7):
            history.append(
                make_turn(
                    i,
                    player_choice=None if i == 1 else f"act-{i}",
                    story_text=f"Chapter prose {i}",
                )
            )
        chapters = [
            {"chapter_number": 1, "title": "Ch1", "start_turn": 1, "end_turn": 3},
            {"chapter_number": 2, "title": "Ch2", "start_turn": 4, "end_turn": 6},
        ]
        memory = {
            "plot_ledger": [
                {"chapter_number": 1, "start_turn": 1, "end_turn": 3, "summary": "Turn 1 to Turn 3"},
                {"chapter_number": 2, "start_turn": 4, "end_turn": 6, "summary": "Turn 4 events"},
            ],
            "chapter_ledger": [],
            "character_ledger": {"local": {}, "global": {}},
        }
        write_json(adv_dir / "history.json", history)
        write_json(adv_dir / "chapters.json", chapters)
        write_json(adv_dir / "memory.json", memory)

    def test_slice_thread_extracts_chapter_and_heals_source(self, library_cartridge):
        story_dir, name = library_cartridge("sandbox", "SourceStory")
        self._seed_two_chapter_story(story_dir)

        ok, rel = TomeWeaverAPI.slice_thread(name, [2], "Extracted Thread", "Author")
        assert ok is True, msg

        extracted = get_adv_dir() / rel
        assert extracted.exists()
        new_history = json.loads((extracted / "history.json").read_text(encoding="utf-8"))
        assert len(new_history) == 3
        assert new_history[0]["turn"] == 1

        source_history = json.loads((story_dir / "history.json").read_text(encoding="utf-8"))
        assert len(source_history) == 3
        assert all(t["turn"] == i + 1 for i, t in enumerate(source_history))


class TestUniverseMigration:
    def test_analyze_migration_detects_collision(self, universe_library):
        _, universe, thread, rel = universe_library()
        setup = json.loads((thread / "setup.json").read_text(encoding="utf-8"))
        setup["is_universe_thread"] = False
        write_json(thread / "setup.json", setup)
        write_json(
            thread / "memory.json",
            {
                "character_ledger": {
                    "Marcus": {"characteristics": {}, "ledger": [], "state": "active"}
                },
            },
        )
        write_json(
            universe / "shared_memory.json",
            {
                "character_ledger": {
                    "Marcus": {"characteristics": {"Role": "Villain"}, "ledger": [], "state": "active"}
                },
                "location_ledger": {},
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

        needs, univ_root, conflicts = TomeWeaverAPI.analyze_migration(rel)
        assert needs is True
        assert univ_root == universe
        assert any(c["entity"] == "Marcus" for c in conflicts)

    def test_commit_migration_merge_keeps_shared_entity(self, universe_library):
        _, universe, thread, rel = universe_library()
        setup = json.loads((thread / "setup.json").read_text(encoding="utf-8"))
        setup["is_universe_thread"] = False
        write_json(thread / "setup.json", setup)
        write_json(
            thread / "memory.json",
            {
                "character_ledger": {
                    "Marcus": {
                        "characteristics": {"Ally": "Hero"},
                        "ledger": ["Saved the day"],
                        "state": "active",
                    }
                },
            },
        )
        write_json(
            universe / "shared_memory.json",
            {
                "character_ledger": {
                    "Marcus": {
                        "characteristics": {"Role": "Villain"},
                        "ledger": ["Old grudge"],
                        "state": "active",
                    }
                },
                "location_ledger": {},
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

        resolutions = {"character_ledger::Marcus": {"action": "merge"}}
        ok, msg = TomeWeaverAPI.commit_migration(rel, universe, "append", resolutions)
        assert ok is True, msg

        shared = json.loads((universe / "shared_memory.json").read_text(encoding="utf-8"))
        assert "Marcus" in shared["character_ledger"]
        assert "Saved the day" in shared["character_ledger"]["Marcus"]["ledger"]

        setup = json.loads((thread / "setup.json").read_text(encoding="utf-8"))
        assert setup.get("is_universe_thread") is True
