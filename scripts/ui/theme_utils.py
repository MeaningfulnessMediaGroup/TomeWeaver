"""
TomeWeaver: Theme Engine Utilities
----------------------------------
State-driven visual theming: luminance-aware text, preset resolution,
and CustomTkinter frame styling helpers.
"""

from config import (
    DEFAULT_THEME_PRESET,
    ENGINE_CONFIG,
    get_default_theme,
    load_themes,
)

VALID_RELIEFS = ("flat", "groove", "raised", "ridge", "sunken")


def normalize_theme(raw):
    """Merge partial theme dict with defaults and coerce types."""
    base = get_default_theme()
    if not isinstance(raw, dict):
        return base

    theme = dict(base)
    for key in ("outer", "mid", "inner"):
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

    relief = str(raw.get("relief", theme["relief"])).lower()
    if relief in VALID_RELIEFS:
        theme["relief"] = relief

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
    """Load the active global theme preset from ``engine_config.json``."""
    themes = load_themes()
    name = ENGINE_CONFIG.get("global_theme_name", DEFAULT_THEME_PRESET)
    preset = themes.get(name)
    if isinstance(preset, dict):
        return normalize_theme(preset)
    return get_default_theme()


def resolve_dashboard_theme():
    """Alias for :func:`resolve_theme` — dashboard and workspace share one global skin."""
    return resolve_theme()


def get_global_theme_preset_name():
    """Return the saved global preset name, falling back if missing from gallery."""
    name = ENGINE_CONFIG.get("global_theme_name", DEFAULT_THEME_PRESET)
    themes = load_themes()
    if name in themes:
        return name
    return DEFAULT_THEME_PRESET


def resolve_theme_for_story_folder(folder_name):
    """Library cards use the same global theme as the rest of the app."""
    return resolve_theme()


def effective_canvas_borderwidth(relief, border_w):
    """Tk 3D reliefs need at least 2px on the internal canvas to render shading."""
    relief = str(relief).lower() if relief else "flat"
    try:
        border_w = max(0, int(border_w))
    except (TypeError, ValueError):
        border_w = 0
    if relief == "flat" or relief not in VALID_RELIEFS:
        return 0
    return max(2, border_w)


def apply_ctk_canvas_relief(widget, relief, border_w):
    """Force native Tk relief on the CTkFrame's internal canvas (CustomTkinter canvas hack)."""
    if not widget:
        return
    relief = str(relief).lower() if relief else "flat"
    if relief not in VALID_RELIEFS:
        relief = "flat"

    canvas_bw = effective_canvas_borderwidth(relief, border_w)
    try:
        canvas = widget._canvas
        if relief == "flat":
            canvas.configure(relief="flat", borderwidth=0)
        else:
            canvas.configure(relief=relief, borderwidth=float(canvas_bw))
    except Exception:
        try:
            widget.configure(relief=relief)
        except Exception:
            pass


def apply_frame_relief(widget, relief, border_w=1):
    """Backward-compatible alias for canvas relief application."""
    apply_ctk_canvas_relief(widget, relief, border_w)


def apply_card_style(frame, theme, *, use_inner=True):
    """Apply inner-card colors, border, rounding, and native canvas relief to a CTkFrame."""
    if not frame or not theme:
        return
    bg = theme["inner"] if use_inner else theme.get("mid", theme["inner"])
    border_w = theme.get("border_w", 1)
    rounding = theme.get("rounding", 10)
    relief = theme.get("relief", "flat")
    contrast = get_contrast_color(bg)

    # Mid-tone borders give ridge/groove/sunken room to shade lighter and darker.
    if relief != "flat":
        border_color = "#808080"
    else:
        border_color = "#888888" if contrast == "black" else "#444444"

    frame.configure(
        fg_color=bg,
        border_width=float(border_w),
        corner_radius=rounding,
        border_color=border_color,
    )
    apply_ctk_canvas_relief(frame, relief, border_w)


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

    # Title, search, breadcrumb, pagination, and scroll list share the outer zone —
    # mid color on these bars created visible horizontal bands.
    for attr in ("header_frame", "search_frame", "breadcrumb_frame", "footer_frame", "scroll"):
        frame = getattr(dashboard, attr, None)
        if frame is not None:
            try:
                frame.configure(fg_color=outer)
            except Exception:
                pass

    text = get_contrast_color(outer)
    muted = get_muted_text_color(outer)
    if hasattr(dashboard, "lbl_library_title"):
        dashboard.lbl_library_title.configure(text_color=text)
    if hasattr(dashboard, "lbl_page"):
        dashboard.lbl_page.configure(text_color=text)
    if hasattr(dashboard, "lbl_loading"):
        dashboard.lbl_loading.configure(text_color=muted)
    if hasattr(dashboard, "lbl_empty"):
        dashboard.lbl_empty.configure(text_color=muted)


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
    story_tab.lbl_chapter.configure(text_color=text)
    story_tab.lbl_action.configure(text_color=text)

    tb = story_tab.prose_box._textbox
    tb.configure(fg=text, insertbackground=text)
    tb.tag_config("story", foreground=text)
    bridge_color = "#1565C0" if text == "black" else "#90CAF9"
    tb.tag_config("bridge", foreground=bridge_color)
    tb.tag_config("lore_dump", foreground=muted)


def repaint_library_card(refs, theme):
    """Re-style a pooled dashboard card to match a story's resolved theme."""
    if not refs or not theme:
        return
    apply_card_style(refs["frame"], theme, use_inner=True)
    text = get_contrast_color(theme["inner"])
    muted = get_muted_text_color(theme["inner"])

    if "title_lbl" in refs:
        refs["title_lbl"].configure(text_color=text)
    if "meta_lbl" in refs:
        refs["meta_lbl"].configure(text_color=muted)
    if "auth_lbl" in refs:
        refs["auth_lbl"].configure(text_color=muted)
