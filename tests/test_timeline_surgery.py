"""
Suites A–C: Timeline surgery, bridge ↔ turn conversion, chapter boundary math.
"""



# ---------------------------------------------------------------------------
# Suite A: Timeline Surgery (Master Clock)
# ---------------------------------------------------------------------------


class TestInsertBlankTurn:
    def test_insert_blank_turn_right_shifts_history(self, engine_with_history):
        engine = engine_with_history(4)
        assert len(engine.history) == 4

        engine.insert_blank_turn(2)

        assert len(engine.history) == 5
        assert engine.history[2]["story_text"].startswith("[ Blank Turn inserted")
        assert engine.history[2]["turn"] == 3
        assert engine.history[3]["turn"] == 4
        assert engine.history[4]["turn"] == 5

    def test_insert_blank_turn_inherits_previous_choice(self, engine_with_history):
        engine = engine_with_history(3, choices_per_turn=[None, "Go left", "Go right"])
        # Insert before turn 3: steals player_choice from the preceding turn (index 1).
        engine.insert_blank_turn(2)

        assert engine.history[1]["player_choice"] == "[ Blank Turn ]"
        assert engine.history[2]["player_choice"] == "Go left"
        assert engine.history[3]["player_choice"] == "Go right"

    def test_insert_blank_turn_shifts_chapter_boundaries(self, engine_with_history):
        engine = engine_with_history(
            4,
            chapters=[
                {
                    "chapter_number": 1,
                    "title": "Act I",
                    "start_turn": 1,
                    "end_turn": 4,
                }
            ],
            memory_flat={
                "plot_ledger": [
                    {
                        "chapter_number": 1,
                        "chapter_title": "Act I",
                        "summary": "Cached plot",
                    }
                ],
                "chapter_ledger": [],
            },
        )

        engine.insert_blank_turn(2)

        ch = engine.chapters[0]
        assert ch["start_turn"] == 1
        assert ch["end_turn"] == 5
        assert engine.memory["plot_ledger"] == []


class TestDeleteTurn:
    def test_delete_turn_left_shifts_history(self, engine_with_history):
        engine = engine_with_history(4)
        engine.delete_turn(2)

        assert len(engine.history) == 3
        assert [t["turn"] for t in engine.history] == [1, 2, 3]
        assert "turn 3" in engine.history[1]["story_text"].lower() or engine.history[1]["turn"] == 2

    def test_delete_turn_restores_player_choice_causality(self, engine_with_history):
        engine = engine_with_history(
            3,
            choices_per_turn=[None, "Pick A", "Pick B"],
        )
        engine.delete_turn(1)

        assert engine.history[0]["player_choice"] == "Pick A"
        assert engine.history[1]["player_choice"] == "Pick B"

    def test_delete_turn_heals_chapter_boundaries(self, engine_with_history):
        engine = engine_with_history(
            4,
            chapters=[
                {
                    "chapter_number": 1,
                    "title": "Act I",
                    "start_turn": 1,
                    "end_turn": 4,
                }
            ],
            memory_flat={
                "plot_ledger": [
                    {"chapter_number": 1, "summary": "Will be invalidated"}
                ],
                "chapter_ledger": [],
            },
        )

        engine.delete_turn(2)

        assert engine.chapters[0]["end_turn"] == 3
        assert engine.memory["plot_ledger"] == []


# ---------------------------------------------------------------------------
# Suite B: Narrative Conversion (Bridge ↔ Turn)
# ---------------------------------------------------------------------------


class TestTurnToBridge:
    def test_turn_to_bridge_concatenates_and_deletes_turn(self, engine_with_history):
        engine = engine_with_history(3)
        engine.history[0]["narrative_bridge"] = "Opening bridge."
        engine.history[0]["story_text"] = "Middle prose."
        engine.history[1]["narrative_bridge"] = "Closing bridge."
        engine.history[1]["player_choice"] = "Advance"

        assert engine.convert_turn_to_bridge(0) is True
        assert len(engine.history) == 2
        bridge = engine.history[0]["narrative_bridge"]
        assert "Opening bridge." in bridge
        assert "Middle prose." in bridge
        assert "Closing bridge." in bridge


class TestBridgeToTurn:
    def test_bridge_to_turn_extracts_card_and_clears_bridge(self, engine_with_history):
        engine = engine_with_history(3)
        bridge_text = "The corridor stretches into darkness."
        engine.history[1]["narrative_bridge"] = bridge_text
        engine.history[0]["player_choice"] = "Step forward"

        assert engine.convert_bridge_to_turn(1) is True
        assert len(engine.history) == 4
        assert engine.history[1]["story_text"] == bridge_text
        assert engine.history[0]["player_choice"] == "[ Timeline Expanded ]"
        assert engine.history[2].get("narrative_bridge", "") == ""


# ---------------------------------------------------------------------------
# Suite C: Chapter Boundary Math
# ---------------------------------------------------------------------------


class TestSplitChapter:
    def test_split_chapter_at_turn_index(self, engine_with_history):
        engine = engine_with_history(
            6,
            chapters=[
                {
                    "chapter_number": 1,
                    "title": "Long Chapter",
                    "start_turn": 1,
                    "end_turn": None,
                }
            ],
        )

        assert engine.split_chapter(3) is True
        assert len(engine.chapters) == 2
        # Split at history index 3 (turn 4): chapter 1 ends at turn 3.
        assert engine.chapters[0]["end_turn"] == 3
        assert engine.chapters[1]["start_turn"] == 4
        assert engine.chapters[0]["chapter_number"] == 1
        assert engine.chapters[1]["chapter_number"] == 2
        assert "(Split)" in engine.chapters[1]["title"]


class TestMergeChapter:
    def test_merge_chapter_absorbs_and_invalidates_rag(self, engine_with_history):
        engine = engine_with_history(
            6,
            chapters=[
                {
                    "chapter_number": 1,
                    "title": "Part A",
                    "start_turn": 1,
                    "end_turn": 3,
                },
                {
                    "chapter_number": 2,
                    "title": "Part B (Split)",
                    "start_turn": 4,
                    "end_turn": 6,
                },
            ],
            memory_flat={
                "plot_ledger": [
                    {"chapter_number": 1, "summary": "Summary A"},
                    {"chapter_number": 2, "summary": "Summary B"},
                ],
                "chapter_ledger": [
                    {"chapter_number": 1, "summary": "Chapter ledger A"},
                    {"chapter_number": 2, "summary": "Chapter ledger B"},
                ],
            },
        )

        assert engine.merge_chapter_up(2) is True
        assert len(engine.chapters) == 1
        assert engine.chapters[0]["chapter_number"] == 1
        assert engine.chapters[0]["end_turn"] == 6
        assert engine.memory["plot_ledger"] == []
        assert engine.memory["chapter_ledger"] == []
