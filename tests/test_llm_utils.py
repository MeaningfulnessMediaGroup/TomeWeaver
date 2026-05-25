"""Loop detection and user-facing API error translation."""

from unittest.mock import MagicMock

import pytest
import requests

from llm import is_repetitive, translate_api_error


class TestIsRepetitive:
    """Detects when the model repeats the opening of the previous turn."""

    def test_detects_identical_opening_phrase(self):
        # Arrange
        prev = "The rain fell hard on the cobblestones below."
        new = "The rain fell hard on the cobblestones above."

        # Act
        result = is_repetitive(prev, new, num_words=4)

        # Assert
        assert result is True

    def test_ignores_when_openings_differ(self):
        # Arrange
        prev = "The rain fell hard."
        new = "Sunlight broke through the clouds."

        # Act / Assert
        assert is_repetitive(prev, new) is False

    def test_returns_false_for_empty_inputs(self):
        # Act / Assert
        assert is_repetitive("", "Some text") is False
        assert is_repetitive("Some text", "") is False


class TestTranslateApiError:
    """Network and HTTP failures become GUI-safe messages."""

    def test_connection_error_message(self):
        # Act
        msg = translate_api_error(exception=requests.exceptions.ConnectionError())

        # Assert
        assert "Server Unreachable" in msg
        assert "LM Studio" in msg

    def test_timeout_error_message(self):
        # Act
        msg = translate_api_error(exception=requests.exceptions.Timeout())

        # Assert
        assert "Timed Out" in msg

    def test_generic_exception_includes_class_name(self):
        # Act
        msg = translate_api_error(exception=ValueError("bad payload"))

        # Assert
        assert "ValueError" in msg
        assert "bad payload" in msg

    def test_http_401_includes_status_context(self):
        # Arrange
        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {"error": {"message": "Invalid API key"}}
        response.text = ""

        # Act
        msg = translate_api_error(response=response)

        # Assert
        assert "401" in msg
        assert "Invalid API key" in msg
