"""Prompt assembly snapshots and import evaluation context."""

import pytest

from conftest import build_engine, make_turn, write_json


class TestPromptAssembly:
    def test_sandbox_strips_setting_after_turn_one(self, engine_with_history):
        engine = engine_with_history(2, choices_per_turn=[None, "Continue"])
        engine.setup_data["setting"] = "A haunted castle on the cliffs."

        messages = engine.build_messages(target_turn=3)
        system = messages[0]["content"]
        assert "haunted castle" not in system or "SETTING" not in system.upper()

    def test_decayed_entity_omitted_from_prompt(self, engine_with_history, set_decay_threshold):
        set_decay_threshold(2)
        engine = engine_with_history(5, choices_per_turn=[None, "a", "b", "c", "d"])
        engine.memory.setdefault("character_ledger", {})["local"] = {
            "ForgottenNpc": {
                "characteristics": {"Role": "Merchant"},
                "ledger": [],
                "state": "archived",
                "last_seen_turn": 1,
            }
        }

        messages = engine.build_messages(target_turn=6)
        blob = " ".join(m.get("content", "") for m in messages)
        assert "ForgottenNpc" not in blob

    def test_campaign_includes_active_objective(self, mock_campaign_dir):
        chapters = [
            {
                "chapter_number": 1,
                "title": "Ch1",
                "start_turn": 1,
                "end_turn": None,
                "objectives": [{"goal": "Steal the gem", "status": "ACTIVE"}],
            }
        ]
        history = [make_turn(1, player_choice=None), make_turn(2, player_choice="Sneak")]
        engine = build_engine(
            mock_campaign_dir, history=history, chapters=chapters, mode="campaign"
        )

        messages = engine.build_messages(target_turn=3)
        blob = " ".join(m.get("content", "") for m in messages)
        assert "Steal the gem" in blob or "gem" in blob.lower()

    def test_build_import_context_includes_identity(self, engine_with_history):
        engine = engine_with_history(2, choices_per_turn=[None, "Go"])
        engine.setup_data["main_character"] = "Canonical Hero"

        ctx = engine.build_import_evaluation_context(insert_after_idx=1)
        assert "Canonical Hero" in ctx
        assert "STORY IDENTITY" in ctx


class TestImportEvaluationGate:
    def test_evaluate_import_integration_parses_mock_response(
        self, engine_with_history, monkeypatch
    ):
        engine = engine_with_history(2, choices_per_turn=[None, "Wait"])

        class FakeResp:
            status_code = 200

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"integration_score": 82, "fitting_reasons": ["Tone match"], "misfit_reasons": [], "summary": "OK", "character_analysis": "", "recommendation": "Import", "verdict": "Good fit"}'
                            }
                        }
                    ]
                }

        monkeypatch.setattr("requests.post", lambda *a, **k: FakeResp())

        ok, data = __import__("api").TomeWeaverAPI.evaluate_import_integration(
            engine, "The hero enters the tavern quietly.", insert_after_idx=1
        )
        assert ok is True
        assert data["integration_score"] == 82
        assert "Tone match" in data["fitting_reasons"]

    def test_evaluate_import_rejects_empty_text(self, sandbox_engine):
        from api import TomeWeaverAPI

        ok, msg = TomeWeaverAPI.evaluate_import_integration(sandbox_engine, "   ", 0)
        assert ok is False
        assert "Paste" in msg
