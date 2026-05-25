"""Atmospheric theme engine: luminance flip and resolution hierarchy."""

import pytest

from config import ENGINE_CONFIG
from ui.theme_utils import (
    get_contrast_color,
    normalize_theme,
    resolve_theme,
    get_global_theme_preset_name,
    apply_library_card_style,
    LIBRARY_CARD_ROUNDING,
)


class TestGetContrastColor:
    """Luminance flip picks readable text on light or dark backgrounds."""

    @pytest.mark.parametrize(
        "bg,expected",
        [
            ("#121212", "white"),
            ("#FFFFFF", "black"),
            ("#f5f5dc", "black"),
            ("#2d0a0a", "white"),
        ],
    )
    def test_contrast_on_known_backgrounds(self, bg, expected):
        assert get_contrast_color(bg) == expected


class TestResolveTheme:
    """Global theme loads from engine_config global_theme_name."""

    def test_loads_named_global_preset(self, monkeypatch):
        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Horror")
        theme = resolve_theme()
        assert theme["inner"] == "#2d0a0a"

    def test_loads_default_light_preset(self, monkeypatch):
        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Default Light")
        theme = resolve_theme()
        assert theme["outer"] == "#e6e6e6"
        assert theme["inner"] == "#cccccc"
        assert get_contrast_color(theme["inner"]) == "black"

    def test_falls_back_to_default_when_preset_missing(self, monkeypatch):
        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Does Not Exist")
        theme = resolve_theme()
        assert theme["outer"] == "#121212"

    def test_setup_data_is_ignored(self, monkeypatch):
        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Parchment")
        theme = resolve_theme({"visual_theme": "Horror"})
        assert theme["inner"] == "#f5f5dc"


class TestGetGlobalThemePresetName:
    """Saved global preset name falls back when missing from gallery."""

    def test_returns_configured_name(self, monkeypatch):
        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Horror")
        assert get_global_theme_preset_name() == "Horror"

    def test_falls_back_when_preset_missing(self, monkeypatch):
        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Does Not Exist")
        assert get_global_theme_preset_name() == "Default Dark"


class TestNormalizeTheme:
    """Partial theme payloads merge with safe defaults."""

    def test_clamps_border_and_rounding(self):
        theme = normalize_theme({"border_w": 99, "rounding": -5})
        assert theme["border_w"] == 5
        assert theme["rounding"] == 0


class TestLibraryCardStyle:
    """Dashboard tiles keep fixed rounding independent of theme border settings."""

    def test_library_card_uses_fixed_rounding(self):
        class FakeFrame:
            config = {}

            def configure(self, **kwargs):
                self.config.update(kwargs)

        frame = FakeFrame()
        theme = {"inner": "#2a2a2a", "border_w": 3, "rounding": 16}
        apply_library_card_style(frame, theme)
        assert frame.config["corner_radius"] == LIBRARY_CARD_ROUNDING
        assert frame.config["border_width"] == 0
        assert frame.config["fg_color"] == "#2a2a2a"
