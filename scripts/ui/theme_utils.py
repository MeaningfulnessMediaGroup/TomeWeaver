"""
TomeWeaver: Theme Engine Utilities
----------------------------------
State-driven visual theming: luminance-aware text, preset resolution,
and CustomTkinter frame styling helpers.

Global preset: ``engine_config.json`` → ``global_theme_name``.
Optional per-story bundle: ``setup.json`` → ``theme_preset`` + ``theme_embedded``.
Player override: ``instance_config.json`` → ``story_theme_preference``.
"""

from config import (
    DEFAULT_THEME_PRESET,
    ENGINE_CONFIG,
    INSTANCE_CONFIG,
    ROOT_DIR,
    get_default_theme,
    load_themes,
    save_json_atomically,
)

STORY_THEME_NONE_LABEL = "(None — player uses global theme)"


def normalize_theme(raw):
    """Merge partial theme dict with defaults and coerce types."""
    base = get_default_theme()
    if not isinstance(raw, dict):
        return base

    theme = dict(base)
    for key in ("outer", "mid", "inner", "chapter_title", "player_action"):
        val = raw.get(key)
        if isinstance(val, str) and val.startswith("#"):
            theme[key] = val

    try:
        theme["border_w"] = max(0, min(5, int(raw.get("border_w", theme["border_w"]))))
    except (TypeError, ValueError):
        pass

    try:
        theme["rounding"] = max(0, min(30, int(raw.get("rounding", theme["rounding"]))))
    except (TypeError, ValueError):
        pass

    return theme


def get_contrast_color(hex_color):
    """Return ``'white'`` or ``'black'`` based on background luminance (WCAG-style)."""
    if not hex_color or not isinstance(hex_color, str):
        return "white"
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "white"
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "white"
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "black" if luminance > 0.5 else "white"


def get_muted_text_color(hex_color):
    """Secondary label color that remains readable on the given background."""
    primary = get_contrast_color(hex_color)
    return "#555555" if primary == "black" else "#B0B0B0"


def resolve_theme(setup_data=None):
    """Load the active **global** theme preset from ``engine_config.json``."""
    themes = load_themes()
    name = ENGINE_CONFIG.get("global_theme_name", DEFAULT_THEME_PRESET)
    preset = themes.get(name)
    if isinstance(preset, dict):
        return normalize_theme(preset)
    return get_default_theme()


def resolve_dashboard_theme():
    """Dashboard shell always uses the global skin."""
    return resolve_theme()


def get_global_theme_preset_name():
    """Return the saved global preset name, falling back if missing from gallery."""
    name = ENGINE_CONFIG.get("global_theme_name", DEFAULT_THEME_PRESET)
    themes = load_themes()
    if name in themes:
        return name
    return DEFAULT_THEME_PRESET


def story_has_bundled_theme(setup_data) -> bool:
    """True when ``setup.json`` ships a recommended / bundled UI skin."""
    if not isinstance(setup_data, dict):
        return False
    if isinstance(setup_data.get("theme_embedded"), dict):
        return True
    preset = (setup_data.get("theme_preset") or "").strip()
    return bool(preset)


def get_story_theme_preset_name(setup_data) -> str | None:
    if not isinstance(setup_data, dict):
        return None
    preset = (setup_data.get("theme_preset") or "").strip()
    return preset or None


def resolve_story_theme(setup_data):
    """Resolve bundled story theme dict, or ``None`` if unset / invalid."""
    if not isinstance(setup_data, dict):
        return None

    embedded = setup_data.get("theme_embedded")
    if isinstance(embedded, dict):
        return normalize_theme(embedded)

    preset = (setup_data.get("theme_preset") or "").strip()
    if not preset:
        return None

    themes = load_themes()
    if preset in themes:
        return normalize_theme(themes[preset])
    return None


def get_story_theme_preference(folder_name: str) -> str:
    """``global`` (default) or ``story`` for this cartridge folder path."""
    prefs = INSTANCE_CONFIG.get("story_theme_preference") or {}
    mode = prefs.get(folder_name, "global")
    return mode if mode in ("global", "story") else "global"


def set_story_theme_preference(folder_name: str, mode: str) -> None:
    """Persist per-story appearance choice in ``instance_config.json``."""
    if mode not in ("global", "story"):
        mode = "global"
    INSTANCE_CONFIG.setdefault("story_theme_preference", {})[folder_name] = mode
    save_json_atomically(INSTANCE_CONFIG, ROOT_DIR / "configs" / "instance_config.json")


def resolve_theme_for_workspace(folder_name: str, setup_data) -> dict:
    """Workspace skin: story bundle when opted-in, otherwise global."""
    if get_story_theme_preference(folder_name) == "story":
        story_theme = resolve_story_theme(setup_data)
        if story_theme:
            return story_theme
    return resolve_theme()


def resolve_theme_for_story_folder(folder_name):
    """Library cards use the global theme (dashboard stays consistent)."""
    return resolve_theme()


def assign_story_theme(setup_data: dict, preset_name: str | None, *, embed: bool = True) -> None:
    """Write or clear story theme fields on ``setup_data`` (caller saves setup.json)."""
    if not preset_name or preset_name == STORY_THEME_NONE_LABEL:
        setup_data.pop("theme_preset", None)
        setup_data.pop("theme_embedded", None)
        return

    setup_data["theme_preset"] = preset_name.strip()
    if embed:
        themes = load_themes()
        raw = themes.get(setup_data["theme_preset"])
        setup_data["theme_embedded"] = normalize_theme(raw if isinstance(raw, dict) else get_default_theme())
    else:
        setup_data.pop("theme_embedded", None)


def story_theme_menu_label(setup_data, folder_name: str) -> str:
    """Short label for workspace options menu."""
    if not story_has_bundled_theme(setup_data):
        return ""
    preset = get_story_theme_preset_name(setup_data) or "Custom"
    if get_story_theme_preference(folder_name) == "story":
        return f"Appearance: Story ({preset}) ✓"
    return f"Appearance: Use Story Theme ({preset})"


LIBRARY_CARD_ROUNDING = 8


def apply_library_card_style(frame, theme):
    """Dashboard folder/story tiles: themed fill with fixed rounded corners (no theme border)."""
    if not frame or not theme:
        return
    frame.configure(
        fg_color=theme["inner"],
        border_width=0,
        corner_radius=LIBRARY_CARD_ROUNDING,
    )


def apply_card_style(frame, theme, *, use_inner=True):
    """Apply inner-card colors, border, and rounding to a CTkFrame."""
    if not frame or not theme:
        return
    bg = theme["inner"] if use_inner else theme.get("mid", theme["inner"])
    border_w = theme.get("border_w", 1)
    rounding = theme.get("rounding", 10)
    contrast = get_contrast_color(bg)
    border_color = "#888888" if contrast == "black" else "#444444"

    frame.configure(
        fg_color=bg,
        border_width=float(border_w),
        corner_radius=rounding,
        border_color=border_color,
    )


def apply_workspace_chrome(workspace, theme):
    """Paint outer/mid zones on a :class:`WorkspaceFrame`."""
    if not theme:
        return
    workspace.configure(fg_color=theme["outer"])
    if hasattr(workspace, "app") and hasattr(workspace.app, "container"):
        workspace.app.container.configure(fg_color=theme["outer"])
    if hasattr(workspace, "header_frame"):
        workspace.header_frame.configure(fg_color=theme["mid"])
    if hasattr(workspace, "tabview"):
        workspace.tabview.configure(fg_color=theme["mid"])
    for attr in ("t_story", "t_console", "t_codex", "t_memory", "t_univ", "t_chapters"):
        tab = getattr(workspace, attr, None)
        if tab is not None:
            try:
                tab.configure(fg_color=theme["mid"])
            except Exception:
                pass


def apply_dashboard_chrome(dashboard, theme):
    """Paint library shell: outer background on chrome bars; cards keep inner styling."""
    if not theme or not dashboard:
        return
    outer = theme["outer"]
    dashboard.configure(fg_color=outer)
    if hasattr(dashboard, "app") and hasattr(dashboard.app, "container"):
        dashboard.app.container.configure(fg_color=outer)

    for attr in ("header_frame", "search_frame", "breadcrumb_frame", "footer_frame"):
        frame = getattr(dashboard, attr, None)
        if frame is not None:
            try:
                frame.configure(fg_color=outer)
            except Exception:
                pass

    mid = theme["mid"]
    if hasattr(dashboard, "scroll") and dashboard.scroll is not None:
        try:
            dashboard.scroll.configure(fg_color=mid)
        except Exception:
            pass

    text = get_contrast_color(outer)
    muted = get_muted_text_color(outer)
    if hasattr(dashboard, "lbl_library_title"):
        dashboard.lbl_library_title.configure(text_color=text)
    if hasattr(dashboard, "lbl_page"):
        dashboard.lbl_page.configure(text_color=text)

    mid_muted = get_muted_text_color(mid)
    if hasattr(dashboard, "lbl_loading"):
        dashboard.lbl_loading.configure(text_color=mid_muted)
    if hasattr(dashboard, "lbl_empty"):
        dashboard.lbl_empty.configure(text_color=mid_muted)


def apply_story_tab_chrome(story_tab, theme):
    """Apply mid-layer background to the story tab shell (outside the card)."""
    if not story_tab or not theme:
        return
    story_tab.configure(fg_color=theme["mid"])
    story_tab.timeline_frame.configure(fg_color=theme["mid"])
    story_tab.input_frame.configure(fg_color=theme["mid"])


def apply_card_text_colors(story_tab, theme):
    """Luminance-flip text on metadata, actions, and prose inside the story card."""
    if not story_tab or not theme:
        return
    inner = theme["inner"]
    text = get_contrast_color(inner)
    muted = get_muted_text_color(inner)

    story_tab.lbl_meta.configure(text_color=muted)
    story_tab.lbl_chapter.configure(text_color=theme["chapter_title"])
    story_tab.lbl_action.configure(text_color=theme["player_action"])

    tb = story_tab.prose_box._textbox
    tb.configure(fg=text, insertbackground=text)
    tb.tag_config("story", foreground=text)
    bridge_color = "#1565C0" if text == "black" else "#90CAF9"
    tb.tag_config("bridge", foreground=bridge_color)
    tb.tag_config("lore_dump", foreground=muted)

    if hasattr(story_tab, "prose_prefix"):
        ptb = story_tab.prose_prefix._textbox
        ptb.configure(fg=muted, insertbackground=muted)
        ptb.tag_config("bridge", foreground=bridge_color)
        ptb.tag_config("lore_dump", foreground=muted)


def repaint_library_card(refs, theme):
    """Re-style a pooled dashboard card to match a story's resolved theme."""
    if not refs or not theme:
        return
    apply_library_card_style(refs["frame"], theme)
    text = get_contrast_color(theme["inner"])
    muted = get_muted_text_color(theme["inner"])

    if "title_lbl" in refs:
        refs["title_lbl"].configure(text_color=text)
    if "meta_lbl" in refs:
        refs["meta_lbl"].configure(text_color=muted)
    if "auth_lbl" in refs:
        refs["auth_lbl"].configure(text_color=muted)
