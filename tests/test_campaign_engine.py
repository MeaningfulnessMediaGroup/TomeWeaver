"""Campaign engine boot and plot-outline scaffolding."""

import pytest

from conftest import build_engine


class TestCampaignEngine:
    """Campaign cartridges load plot metadata and flag mode correctly."""

    def test_campaign_engine_sets_is_campaign(self, mock_campaign_dir):
        # Act
        engine = build_engine(mock_campaign_dir, mode="campaign")

        # Assert
        assert engine.is_campaign is True
        assert engine.chapters
        assert engine.chapters[0]["start_turn"] == 1

    def test_campaign_plot_outline_loaded_from_boilerplate(self, mock_campaign_dir):
        # Act
        engine = build_engine(mock_campaign_dir, mode="campaign")

        # Assert
        assert isinstance(engine.setup_data.get("plot_outline"), list)
        assert len(engine.setup_data["plot_outline"]) >= 1
