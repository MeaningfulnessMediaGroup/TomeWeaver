"""Suite E: Dual-tiered RAG — local/global scope and memory decay janitor."""

import pytest

from conftest import make_turn, write_json


class TestRagLocalOverride:
    """Local entity buckets shadow global names without deleting shared data."""

    def test_rag_local_override_shadows_global_without_deleting(self, sandbox_engine):
        ledger = sandbox_engine.memory["character_ledger"]
        ledger["global"]["Marcus"] = {
            "characteristics": {"Role": "Antagonist"},
            "ledger": [],
            "state": "active",
            "last_seen_turn": 1,
        }
        ledger["local"]["Marcus"] = {
            "characteristics": {"Role": "Ally"},
            "ledger": ["Saved the party"],
            "state": "active",
            "last_seen_turn": 5,
        }

        combined = {**ledger["global"], **ledger["local"]}
        assert combined["Marcus"]["characteristics"]["Role"] == "Ally"
        assert ledger["global"]["Marcus"]["characteristics"]["Role"] == "Antagonist"

        traits = sandbox_engine.memory["character_ledger"]["local"]["Marcus"][
            "characteristics"
        ]
        sandbox_engine._smart_merge_traits(
            traits, {"Friends": "Elena", "Role": "Mentor"}
        )
        assert "Friends" in traits or "Friend" in traits
        assert "Elena" in str(traits.values())
        assert ledger["global"]["Marcus"]["characteristics"]["Role"] == "Antagonist"

    def test_prompt_builder_favors_local_entity(self, engine_with_history):
        engine = engine_with_history(
            2,
            choices_per_turn=[None, "Continue"],
        )
        engine.memory["character_ledger"]["global"]["Aria"] = {
            "characteristics": {"Mood": "Global cold"},
            "ledger": [],
            "state": "active",
            "last_seen_turn": 1,
        }
        engine.memory["character_ledger"]["local"]["Aria"] = {
            "characteristics": {"Mood": "Local warm"},
            "ledger": [],
            "state": "active",
            "last_seen_turn": 2,
        }

        messages = engine.build_messages(target_turn=2)
        system = messages[0]["content"]
        assert "Local warm" in system
        assert "Global cold" not in system


class TestRagAutoDecay:
    """Visibility janitor archives stale entities and revives on mention."""

    def test_rag_auto_decay_archives_stale_entities(self, engine_with_history, monkeypatch):
        monkeypatch.setitem(
            __import__("config", fromlist=["ENGINE_CONFIG"]).ENGINE_CONFIG,
            "memory_decay_threshold",
            5,
        )

        turn_count = 12
        engine = engine_with_history(turn_count, choices_per_turn=[None] + ["x"] * (turn_count - 1))
        engine.history[0]["story_text"] = "Sir Aldric greets the party."
        for i in range(1, turn_count):
            engine.history[i]["story_text"] = f"Turn {i + 1} with no named NPCs."

        engine.memory["character_ledger"]["local"]["Sir Aldric"] = {
            "characteristics": {"Role": "Knight"},
            "ledger": [],
            "state": "active",
            "last_seen_turn": 1,
        }

        engine._resync_all_visibility()

        entity = engine.memory["character_ledger"]["local"]["Sir Aldric"]
        assert entity["state"] == "archived"
        assert entity["last_seen_turn"] == 1

    def test_rag_revives_entity_when_mentioned_again(self, engine_with_history, monkeypatch):
        monkeypatch.setitem(
            __import__("config", fromlist=["ENGINE_CONFIG"]).ENGINE_CONFIG,
            "memory_decay_threshold",
            3,
        )

        engine = engine_with_history(6, choices_per_turn=[None] + ["go"] * 5)
        engine.memory["character_ledger"]["local"]["Lyra"] = {
            "characteristics": {},
            "ledger": [],
            "state": "archived",
            "last_seen_turn": 1,
        }
        engine.history[5]["story_text"] = "Lyra returns with news."

        engine._update_entity_visibility(6, engine.history[5]["story_text"])

        assert engine.memory["character_ledger"]["local"]["Lyra"]["state"] == "active"
        assert engine.memory["character_ledger"]["local"]["Lyra"]["last_seen_turn"] == 6
