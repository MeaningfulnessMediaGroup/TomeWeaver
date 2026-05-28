"""Plot-ledger selection for LLM prompt assembly."""

from conftest import build_engine, make_turn
from master_clock import format_plot_ledger_section, select_plot_ledger_for_prompt


class TestSelectPlotLedgerForPrompt:
    def _memory(self):
        return {
            "chapter_ledger": [
                {"chapter_number": i, "chapter_title": f"Ch{i}", "summary": f"Summary {i}"}
                for i in range(1, 25)
            ],
            "plot_ledger": [
                {
                    "chapter_number": 21,
                    "start_turn": 155,
                    "end_turn": 205,
                    "summary": "Stale chapter 21 chunk",
                },
                {
                    "chapter_number": 25,
                    "start_turn": 284,
                    "end_turn": 293,
                    "summary": "Chapter 25 opening beats",
                },
                {
                    "chapter_number": 25,
                    "start_turn": 294,
                    "end_turn": 299,
                    "summary": "Chapter 25 mid-chapter chunk",
                },
            ],
        }

    def test_excludes_stale_other_chapter_and_superseded_ranges(self):
        active_chapter = {
            "chapter_number": 25,
            "title": "The Deep Vault",
            "start_turn": 284,
            "end_turn": None,
        }
        selected = select_plot_ledger_for_prompt(
            self._memory(),
            active_chapter,
            full_history_turns=[294, 295],
        )
        assert len(selected) == 1
        assert selected[0]["start_turn"] == 284
        assert selected[0]["end_turn"] == 293
        assert "Stale chapter 21" not in selected[0]["summary"]

    def test_includes_gap_filling_parts_before_context_window(self):
        active_chapter = {
            "chapter_number": 5,
            "title": "Act Five",
            "start_turn": 285,
            "end_turn": None,
        }
        memory = {
            "chapter_ledger": [{"chapter_number": i, "summary": "x"} for i in range(1, 5)],
            "plot_ledger": [
                {
                    "chapter_number": 5,
                    "start_turn": 285,
                    "end_turn": 293,
                    "summary": "Early chapter five beats",
                },
                {
                    "chapter_number": 5,
                    "start_turn": 295,
                    "end_turn": 299,
                    "summary": "Should be excluded when turn 294 is full prose",
                },
            ],
        }
        selected = select_plot_ledger_for_prompt(
            memory,
            active_chapter,
            full_history_turns=[294],
        )
        assert len(selected) == 1
        assert selected[0]["end_turn"] == 293

    def test_format_section_labels_chapter_and_turn_ranges(self):
        active_chapter = {"chapter_number": 25, "title": "Vault", "start_turn": 284}
        section = format_plot_ledger_section(
            [{"start_turn": 284, "end_turn": 293, "summary": "Opening"}],
            active_chapter,
        )
        assert "PLOT PARTS (Chapter 25: Vault" in section
        assert "Turns 284-293" in section


class TestPromptPlotLedgerIntegration:
    def test_build_messages_uses_scoped_plot_parts(self, engine_with_history, monkeypatch):
        monkeypatch.setitem(
            __import__("config", fromlist=["ENGINE_CONFIG"]).ENGINE_CONFIG,
            "context_window",
            2,
        )
        engine = engine_with_history(12, choices_per_turn=[None] + ["go"] * 11)
        for i, turn in enumerate(engine.history):
            turn["turn"] = 284 + i
        engine.chapters = [
            {
                "chapter_number": 25,
                "title": "Vault",
                "start_turn": 284,
                "end_turn": None,
            }
        ]
        engine.memory["chapter_ledger"] = [
            {"chapter_number": i, "chapter_title": f"Ch{i}", "summary": "done"}
            for i in range(1, 25)
        ]
        engine.memory["plot_ledger"] = [
            {
                "chapter_number": 21,
                "start_turn": 155,
                "end_turn": 205,
                "summary": "Old chapter 21 ledger",
            },
            {
                "chapter_number": 25,
                "start_turn": 284,
                "end_turn": 293,
                "summary": "Vault approach summary",
            },
            {
                "chapter_number": 25,
                "start_turn": 294,
                "end_turn": 299,
                "summary": "Should not appear in prompt",
            },
        ]

        messages = engine.build_messages(target_turn=296)
        system = messages[0]["content"]
        assert "PLOT PARTS (Chapter 25: Vault" in system
        assert "Vault approach summary" in system
        assert "Old chapter 21 ledger" not in system
        assert "Should not appear in prompt" not in system
        assert "RECENT EVENTS (Granular)" not in system
