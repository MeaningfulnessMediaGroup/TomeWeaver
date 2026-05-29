"""Draft editing pipeline: expand/commit/cancel and undo."""

import pytest

from conftest import assert_cartridge_consistent, make_turn, valid_turn_payload, write_json


class TestDraftPipeline:
    def test_commit_draft_preserves_player_choice(self, engine_with_history, mock_llm_response):
        engine = engine_with_history(2, choices_per_turn=[None, "Original choice"])
        original_choice = engine.history[1]["player_choice"]
        original_bridge = engine.history[1].get("narrative_bridge", "")

        engine.backup_turn = engine.history[1].copy()
        engine.backup_turn_idx = 1
        engine.is_fix_mode = True

        draft = valid_turn_payload(
            turn_num=2,
            story_text="Expanded prose with more detail.",
            player_choice="SHOULD NOT STICK",
        )
        committed = engine.commit_draft(draft)

        assert committed["story_text"] == "Expanded prose with more detail."
        assert engine.history[1]["player_choice"] == original_choice
        assert engine.history[1].get("narrative_bridge", "") == original_bridge
        assert not hasattr(engine, "backup_turn_idx")
        assert engine.is_fix_mode is False
        assert_cartridge_consistent(engine)

    def test_cancel_draft_clears_fix_mode(self, engine_with_history):
        engine = engine_with_history(2, choices_per_turn=[None, "Keep me"])

        engine.backup_turn = engine.history[1].copy()
        engine.backup_turn_idx = 1
        engine.is_fix_mode = True

        engine.cancel_draft()
        assert engine.is_fix_mode is False
        assert engine.backup_turn is None
        assert not hasattr(engine, "backup_turn_idx")

    def test_request_expansion_with_mocked_llm(self, engine_with_history, mock_llm_response):
        engine = engine_with_history(2, choices_per_turn=[None, "Look around"])
        mock_llm_response(
            lambda *_a, **_k: valid_turn_payload(
                turn_num=2,
                story_text="Much longer descriptive expansion.",
            )
        )

        draft = engine.request_expansion(turn_idx=1)
        assert draft is not None
        assert "expansion" in draft["story_text"].lower() or len(draft["story_text"]) > 10
        assert engine.is_fix_mode is True
        assert engine.backup_turn_idx == 1

    def test_request_expansion_selection_includes_rag_and_length_target(
        self, engine_with_history, mock_llm_response
    ):
        engine = engine_with_history(2, choices_per_turn=[None, "Look around"])
        engine.memory.setdefault("character_ledger", {})["local"] = {
            "Hero": {
                "state": "active",
                "characteristics": {"Role": "protagonist"},
                "ledger": ["Opened the door"],
            }
        }
        selection = "She stepped into the cold room."
        mock_llm_response(
            lambda *_a, **_k: valid_turn_payload(
                turn_num=2,
                story_text="Paragraph one.\n\nShe stepped into the freezing room, frost biting her skin.\n\nParagraph three.",
            )
        )

        draft = engine.request_expansion(turn_idx=1, selection_text=selection)
        assert draft is not None
        fix = engine.active_fix
        assert "LONG-TERM MEMORY" in fix
        assert "LOCAL RAG" in fix
        assert "CURRENT TURN" in fix
        assert selection in fix
        assert "SELECTION EXPANSION" in fix
        assert "substantially longer" in fix
        assert "Hero" in fix

    def test_request_polish_with_selection_scopes_prompt(self, engine_with_history, mock_llm_response):
        engine = engine_with_history(2, choices_per_turn=[None, "Look around"])
        mock_llm_response(
            lambda *_a, **_k: valid_turn_payload(
                turn_num=2,
                story_text="The polished sentence gleamed.",
            )
        )

        draft = engine.request_polish(turn_idx=1, selection_text="A short sentence.")
        assert draft is not None
        assert "SELECTION SCOPE" in engine.active_fix
        assert "A short sentence." in engine.active_fix

    def test_apply_draft_inheritance_keeps_choices(self, sandbox_engine):
        sandbox_engine.history = [
            make_turn(1, player_choice=None),
            {
                **make_turn(2, player_choice="Go north"),
                "choices": ["Go north", "Go south"],
            },
        ]
        sandbox_engine.backup_turn = sandbox_engine.history[1].copy()

        draft = valid_turn_payload(turn_num=2, choices=["Hallucinated A", "Hallucinated B"])
        sandbox_engine._apply_draft_inheritance(draft)
        assert draft["choices"] == ["Go north", "Go south"]

    def test_undo_removes_tail_and_clears_choice(self, engine_with_history):
        engine = engine_with_history(3, choices_per_turn=[None, "A", "B"])
        tail = engine.undo()
        assert len(engine.history) == 2
        assert engine.history[-1]["player_choice"] is None
        assert tail["turn"] == 2
