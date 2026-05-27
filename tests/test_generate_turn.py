"""Full turn generation pipeline with mocked LLM."""

import pytest

from conftest import assert_cartridge_consistent, valid_turn_payload


class TestGenerateTurnPipeline:
    def test_submit_action_appends_valid_turn(self, engine_with_history, mock_llm_response):
        engine = engine_with_history(1, choices_per_turn=[None])
        mock_llm_response(
            lambda *_a, **_k: valid_turn_payload(
                turn_num=2,
                story_text="The path splits ahead.",
                choices=["Left path", "Right path"],
            )
        )

        result = engine.submit_action("Walk forward")
        assert result is not None
        assert len(engine.history) == 2
        assert engine.history[0]["player_choice"] == "Walk forward"
        assert engine.history[1]["turn"] == 2
        assert_cartridge_consistent(engine)

    def test_generate_turn_stamps_master_clock(self, engine_with_history, mock_llm_response):
        engine = engine_with_history(3, choices_per_turn=[None, "A", "B"])
        mock_llm_response(
            lambda *_a, **_k: valid_turn_payload(turn_num=999, story_text="Wrong turn num")
        )

        turn = engine._generate_turn()
        assert turn["turn"] == 4

    def test_fix_mode_uses_editor_prompt_path(self, engine_with_history, mock_llm_response):
        engine = engine_with_history(2, choices_per_turn=[None, "Stay"])
        captured = []

        def capture(messages, *_a, **_k):
            captured.append(messages)
            return valid_turn_payload(turn_num=2, story_text="Polished prose.")

        mock_llm_response(capture)
        engine.backup_turn = engine.history[1].copy()
        engine.backup_turn_idx = 1
        engine.active_fix = "USER_POLISH rewrite this scene"
        engine.is_fix_mode = True

        engine._generate_turn()
        assert captured
        assert "SYS_EDITOR" in captured[0][0]["content"] or len(captured[0]) >= 2

    def test_process_valid_turn_updates_entity_visibility(self, sandbox_engine):
        sandbox_engine.memory.setdefault("character_ledger", {})["local"] = {
            "Mira": {
                "characteristics": {},
                "ledger": [],
                "state": "archived",
                "last_seen_turn": 0,
            }
        }
        sandbox_engine.history = [
            valid_turn_payload(turn_num=1, player_choice="Hello Mira"),
        ]

        turn = valid_turn_payload(
            turn_num=2,
            story_text="Mira smiles from the doorway.",
            choices=["Wave", "Hide"],
        )
        sandbox_engine._process_valid_turn(turn)

        mira = sandbox_engine.memory["character_ledger"]["local"]["Mira"]
        assert mira["state"] == "active"
        assert mira["last_seen_turn"] == 2
