"""Turn JSON schema validation and auto-healing (validate_turn_schema)."""

import pytest

from llm import validate_turn_schema


def _minimal_turn(**overrides):
    base = {
        "story_text": "The door creaks open.",
        "pov_character": "Hero",
        "location": "Hallway",
        "input_type": "choice",
        "choices": ["Enter", "Flee"],
    }
    base.update(overrides)
    return base


class TestValidateTurnSchema:
    """Fortress gatekeeper before turns enter history."""

    def test_rejects_non_dict_payload(self):
        # Act
        data, err = validate_turn_schema("not a dict")

        # Assert
        assert data is None
        assert "dictionary" in err.lower()

    def test_rejects_missing_required_keys(self):
        # Arrange
        payload = {"story_text": "Incomplete turn."}

        # Act
        data, err = validate_turn_schema(payload)

        # Assert
        assert data is None
        assert "Missing required JSON keys" in err

    def test_inherits_location_from_previous_turn(self):
        # Arrange
        prev = _minimal_turn(location="Castle Gate")
        payload = _minimal_turn()
        del payload["location"]

        # Act
        data, err = validate_turn_schema(payload, prev_turn=prev)

        # Assert
        assert err is None
        assert data["location"] == "Castle Gate"

    def test_forces_is_game_over_false_when_mortality_disabled(self):
        # Arrange
        payload = _minimal_turn(is_game_over=True)

        # Act
        data, err = validate_turn_schema(payload, can_die=False)

        # Assert
        assert err is None
        assert data["is_game_over"] is False

    def test_scrubs_malformed_choice_artifacts(self):
        # Arrange
        payload = _minimal_turn(
            choices=['"Go north"', ', "Pick the lock"', '  "Wait"  ']
        )

        # Act
        data, err = validate_turn_schema(payload, is_test_mode=True)

        # Assert
        assert err is None
        assert data["choices"] == ["Go north", "Pick the lock", "Wait"]
        assert data["player_choice"] is None

    def test_injects_empty_choices_list_when_missing(self):
        # Arrange
        payload = _minimal_turn()
        del payload["choices"]

        # Act
        data, err = validate_turn_schema(payload)

        # Assert
        assert err is None
        assert data["choices"] == []

    def test_flattens_hard_wrapped_story_prose(self):
        # Arrange
        payload = _minimal_turn(story_text="Line one\nLine two continues\n\nNew paragraph.")

        # Act
        data, err = validate_turn_schema(payload, is_test_mode=True)

        # Assert
        assert err is None
        assert "Line one Line two continues" in data["story_text"]
        assert "New paragraph." in data["story_text"]
