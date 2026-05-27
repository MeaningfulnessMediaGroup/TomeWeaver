"""Campaign objective auditor hooks (mocked LLM)."""

import pytest

from conftest import build_engine, make_turn, write_json


def _campaign_with_objectives(adv_dir):
    chapters = [
        {
            "chapter_number": 1,
            "title": "Chapter 1",
            "start_turn": 1,
            "end_turn": None,
            "objectives": [
                {"goal": "Find the key", "status": "ACTIVE"},
                {"goal": "Open the door", "status": "LOCKED"},
            ],
        }
    ]
    history = [
        make_turn(1, player_choice=None),
        make_turn(2, player_choice="Search the room"),
    ]
    return build_engine(adv_dir, history=history, chapters=chapters, mode="campaign")


class TestCampaignObjectiveFlow:
    def test_auditor_success_unlocks_next_objective(self, mock_campaign_dir, monkeypatch):
        engine = _campaign_with_objectives(mock_campaign_dir)

        def fake_auditor(*_args, **_kwargs):
            return {"achieved": True, "reason": "Key found under the mat.", "inventory": ""}

        monkeypatch.setattr("llm.evaluate_campaign_objective", fake_auditor)

        turn_data = make_turn(3, player_choice=None)
        engine.post_generation_hook(turn_data)

        objectives = engine.chapters[0]["objectives"]
        assert objectives[0]["status"] == "COMPLETED"
        assert objectives[1]["status"] == "ACTIVE"
        assert turn_data["choices"] == ["Proceed to the next objective"]

    def test_auditor_failure_leaves_objective_active(self, mock_campaign_dir, monkeypatch):
        engine = _campaign_with_objectives(mock_campaign_dir)

        monkeypatch.setattr(
            "llm.evaluate_campaign_objective",
            lambda *_a, **_k: {"achieved": False, "reason": "Not yet.", "inventory": ""},
        )

        turn_data = make_turn(3, player_choice=None)
        engine.post_generation_hook(turn_data)

        assert engine.chapters[0]["objectives"][0]["status"] == "ACTIVE"
        assert turn_data.get("chapter_goal_achieved") is False

    def test_final_objective_completes_chapter(self, mock_campaign_dir, monkeypatch):
        chapters = [
            {
                "chapter_number": 1,
                "title": "Chapter 1",
                "start_turn": 1,
                "end_turn": None,
                "objectives": [{"goal": "Escape", "status": "ACTIVE"}],
            }
        ]
        history = [
            make_turn(1, player_choice=None),
            make_turn(2, player_choice="Run"),
        ]
        engine = build_engine(
            mock_campaign_dir, history=history, chapters=chapters, mode="campaign"
        )
        engine.setup_data["plot_outline"] = [
            {"title": "Chapter 1", "objectives": [{"goal": "Escape"}]},
            {"title": "Chapter 2", "objectives": [{"goal": "Survive"}]},
        ]

        monkeypatch.setattr(
            "llm.evaluate_campaign_objective",
            lambda *_a, **_k: {"achieved": True, "reason": "Escaped.", "inventory": ""},
        )

        turn_data = make_turn(3, player_choice=None)
        engine.post_generation_hook(turn_data)

        assert turn_data.get("chapter_goal_achieved") is True
        pending = next(c for c in engine.chapters if c.get("start_turn") is None)
        assert pending["chapter_number"] == 2

    def test_setup_turn_skips_auditor(self, mock_campaign_dir, monkeypatch):
        engine = _campaign_with_objectives(mock_campaign_dir)
        calls = []

        def spy(*_a, **_k):
            calls.append(1)
            return {"achieved": False, "reason": "", "inventory": ""}

        monkeypatch.setattr("llm.evaluate_campaign_objective", spy)

        turn_data = make_turn(1, player_choice=None)
        engine.post_generation_hook(turn_data)

        assert calls == []
        assert turn_data.get("objective_achieved") is False
