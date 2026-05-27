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

    def test_setup_embedded_theme_used_when_opted_in(self, monkeypatch, tmp_path):
        from config import INSTANCE_CONFIG, save_json_atomically, ROOT_DIR
        from ui.theme_utils import (
            assign_story_theme,
            resolve_theme_for_workspace,
            set_story_theme_preference,
        )

        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Default Dark")
        setup = {}
        assign_story_theme(setup, "Parchment", embed=True)
        folder = "TestStory"
        set_story_theme_preference(folder, "story")
        theme = resolve_theme_for_workspace(folder, setup)
        assert theme["inner"] == "#f5f5dc"

    def test_story_theme_ignored_when_preference_global(self, monkeypatch):
        from ui.theme_utils import assign_story_theme, resolve_theme_for_workspace

        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Horror")
        setup = {}
        assign_story_theme(setup, "Parchment", embed=True)
        theme = resolve_theme_for_workspace("AnyStory", setup)
        assert theme["inner"] == "#2d0a0a"


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

    def test_backfills_card_label_accent_colors(self):
        theme = normalize_theme({"outer": "#121212"})
        assert theme["chapter_title"] == "#00ACC1"
        assert theme["player_action"] == "#4CAF50"


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


class TestStoryThemeBundling:
    """Per-story theme fields in setup.json and workspace preference."""

    def test_assign_story_theme_embeds_colors(self, monkeypatch):
        from ui.theme_utils import assign_story_theme, story_has_bundled_theme

        monkeypatch.setitem(ENGINE_CONFIG, "global_theme_name", "Default Dark")
        setup = {}
        assign_story_theme(setup, "Parchment", embed=True)
        assert story_has_bundled_theme(setup)
        assert setup["theme_preset"] == "Parchment"
        assert setup["theme_embedded"]["inner"] == "#f5f5dc"

    def test_assign_none_clears_bundled_theme(self):
        from ui.theme_utils import assign_story_theme, story_has_bundled_theme

        setup = {"theme_preset": "Horror", "theme_embedded": {"inner": "#000"}}
        assign_story_theme(setup, None, embed=True)
        assert not story_has_bundled_theme(setup)
        assert "theme_preset" not in setup

    def test_resolve_story_theme_prefers_embedded_over_preset_name(self):
        from ui.theme_utils import assign_story_theme, resolve_story_theme

        setup = {}
        assign_story_theme(setup, "Default Dark", embed=True)
        setup["theme_embedded"]["inner"] = "#ABCDEF"
        theme = resolve_story_theme(setup)
        assert theme["inner"] == "#ABCDEF"

    def test_story_theme_menu_label_reflects_preference(self, monkeypatch):
        from config import INSTANCE_CONFIG
        from ui.theme_utils import assign_story_theme, set_story_theme_preference, story_theme_menu_label

        monkeypatch.setitem(INSTANCE_CONFIG, "story_theme_preference", {})
        setup = {}
        assign_story_theme(setup, "Parchment", embed=True)
        folder = "MyStory_MenuLabel"
        label = story_theme_menu_label(setup, folder)
        assert "Use Story Theme" in label

        set_story_theme_preference(folder, "story")
        active = story_theme_menu_label(setup, folder)
        assert "✓" in active
        assert "Parchment" in active

    def test_get_story_theme_preset_name(self):
        from ui.theme_utils import get_story_theme_preset_name

        assert get_story_theme_preset_name({}) is None
        assert get_story_theme_preset_name({"theme_preset": " Horror "}) == "Horror"
