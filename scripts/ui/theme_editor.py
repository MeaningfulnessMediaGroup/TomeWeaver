"""
TomeWeaver: Theme Editor Dialog
---------------------------------
Unified modal for creating, previewing, and assigning atmospheric skins.
"""

import customtkinter as ctk
from tkinter import colorchooser, messagebox

from config import (
    DEFAULT_THEME_PRESET,
    ENGINE_CONFIG,
    ROOT_DIR,
    load_themes,
    save_json_atomically,
    save_themes,
)
from ui.theme_utils import (
    apply_card_style,
    get_contrast_color,
    get_muted_text_color,
    get_global_theme_preset_name,
    normalize_theme,
)
from ui.tooltip import center_window_on_parent


class ThemeEditorDialog(ctk.CTkToplevel):
    """Reusable theme editor with live mini-UI preview and preset gallery."""

    def __init__(self, parent, on_theme_applied=None, *, mode="global", initial_preset=None):
        super().__init__(parent)
        self.on_theme_applied = on_theme_applied
        self.mode = mode
        self.themes = load_themes()
        if mode == "story" and initial_preset:
            initial_preset = initial_preset.strip()
        else:
            initial_preset = initial_preset or get_global_theme_preset_name()
        if initial_preset not in self.themes:
            initial_preset = get_global_theme_preset_name()
        preset_data = self.themes.get(initial_preset)
        self._draft = normalize_theme(preset_data if isinstance(preset_data, dict) else {})
        self._suppress_preset_sync = False

        self.title("Visual Settings — Theme Editor")
        self.geometry("720x680")
        self.attributes("-topmost", True)
        self.grab_set()
        center_window_on_parent(self, parent.winfo_toplevel())

        ctk.CTkLabel(
            self,
            text="Atmospheric Skinning",
            font=("Arial", 18, "bold"),
        ).pack(pady=(16, 4))
        ctk.CTkLabel(
            self,
            text="Customize the three-layer UI palette and card structure. Text colors flip automatically for readability.",
            wraplength=660,
            text_color="gray",
        ).pack(padx=20, pady=(0, 10))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=8)

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.pack(side="left", fill="both", expand=True, padx=(0, 10))

        preview_wrap = ctk.CTkFrame(body, fg_color="transparent")
        preview_wrap.pack(side="right", fill="y")

        ctk.CTkLabel(preview_wrap, text="Live Preview", font=("Arial", 14, "bold")).pack(anchor="w")
        self.preview_outer = ctk.CTkFrame(preview_wrap, width=260, height=320)
        self.preview_outer.pack(pady=8)
        self.preview_outer.pack_propagate(False)

        self.preview_mid = ctk.CTkFrame(self.preview_outer)
        self.preview_mid.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            self.preview_mid,
            text="Toolbar",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.preview_card = ctk.CTkFrame(self.preview_mid)
        self.preview_card.pack(fill="both", expand=True, padx=10, pady=8)

        self.preview_chapter = ctk.CTkLabel(
            self.preview_card, text="~ Chapter I ~", font=("Georgia", 12, "bold", "italic")
        )
        self.preview_chapter.pack(anchor="w", padx=12, pady=(10, 2))

        self.preview_meta = ctk.CTkLabel(
            self.preview_card, text="[Turn 3] • The Old Mill", font=("Arial", 10)
        )
        self.preview_meta.pack(anchor="w", padx=12)

        self.preview_action = ctk.CTkLabel(
            self.preview_card, text="You chose: Open the rusted door", font=("Arial", 11, "bold")
        )
        self.preview_action.pack(anchor="w", padx=12, pady=(4, 2))

        self.preview_prose = ctk.CTkLabel(
            self.preview_card,
            text="The hinges scream. Cold air spills into the hallway.",
            wraplength=210,
            justify="left",
            font=("Georgia", 11),
        )
        self.preview_prose.pack(anchor="w", padx=12, pady=(4, 12))

        preset_row = ctk.CTkFrame(controls, fg_color="transparent")
        preset_row.pack(fill="x", pady=6)
        ctk.CTkLabel(preset_row, text="Preset:", font=("Arial", 13, "bold"), width=90, anchor="e").pack(
            side="left"
        )
        self.preset_var = ctk.StringVar(value=initial_preset)
        self.preset_menu = ctk.CTkOptionMenu(
            preset_row,
            variable=self.preset_var,
            values=sorted(self.themes.keys()),
            width=220,
            command=self._load_selected_preset,
        )
        self.preset_menu.pack(side="left", padx=8)

        self.color_vars = {}
        self.color_buttons = {}
        for label, key in (
            ("Outer Background", "outer"),
            ("Mid Container", "mid"),
            ("Inner Card", "inner"),
            ("Chapter Title", "chapter_title"),
            ("Player Action", "player_action"),
        ):
            row = ctk.CTkFrame(controls, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=f"{label}:", font=("Arial", 12, "bold"), width=130, anchor="e").pack(
                side="left"
            )
            swatch = ctk.CTkButton(
                row,
                text=self._draft[key].upper(),
                width=100,
                height=28,
                command=lambda k=key: self._pick_color(k),
            )
            swatch.pack(side="left", padx=6)
            self.color_buttons[key] = swatch
            var = ctk.StringVar(value=self._draft[key])
            self.color_vars[key] = var
            ctk.CTkLabel(row, textvariable=var, font=("Consolas", 11), width=80).pack(side="left")

        self.border_slider = self._add_slider(controls, "Border Width", 0, 5, self._draft["border_w"], self._on_border_change)
        self.round_slider = self._add_slider(
            controls, "Corner Rounding", 0, 30, self._draft["rounding"], self._on_round_change
        )

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)

        ctk.CTkButton(btn_row, text="Save as New Preset", width=140, command=self._save_new_preset).pack(
            side="left", padx=4
        )
        ctk.CTkButton(btn_row, text="Overwrite Preset", width=130, command=self._overwrite_preset).pack(
            side="left", padx=4
        )
        ctk.CTkButton(btn_row, text="Delete Preset", width=110, fg_color="#B71C1C", command=self._delete_preset).pack(
            side="left", padx=4
        )

        apply_row = ctk.CTkFrame(self, fg_color="transparent")
        apply_row.pack(fill="x", padx=16, pady=(4, 16))

        ctk.CTkButton(
            apply_row,
            text="Apply to Story" if mode == "story" else "Apply Theme",
            fg_color="#1F6AA5",
            command=self._apply_theme,
        ).pack(side="left", padx=4)

        ctk.CTkButton(apply_row, text="Close", fg_color="#4A4A4A", command=self.destroy).pack(side="right", padx=4)

        self._load_selected_preset(initial_preset)

    def _add_slider(self, parent, label, low, high, initial, callback):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=f"{label}:", font=("Arial", 12, "bold"), width=130, anchor="e").pack(side="left")
        val_lbl = ctk.CTkLabel(row, text=str(initial), width=30)
        val_lbl.pack(side="right")

        def on_move(v):
            val_lbl.configure(text=str(int(float(v))))
            callback(int(float(v)))

        slider = ctk.CTkSlider(row, from_=low, to=high, number_of_steps=high - low, command=on_move)
        slider.set(initial)
        slider.pack(side="left", fill="x", expand=True, padx=8)
        return slider

    def _on_border_change(self, value):
        self._draft["border_w"] = value
        self._refresh_preview()

    def _on_round_change(self, value):
        self._draft["rounding"] = value
        self._refresh_preview()

    def _pick_color(self, key):
        current = self.color_vars[key].get()
        _, hex_color = colorchooser.askcolor(color=current, title=f"Choose {key} color")
        if hex_color:
            self.color_vars[key].set(hex_color)
            self._draft[key] = hex_color
            self._refresh_preview()

    def _update_color_swatches(self):
        """Paint each picker button with its current hex for at-a-glance feedback."""
        for key, btn in self.color_buttons.items():
            hex_color = self.color_vars[key].get()
            btn.configure(
                fg_color=hex_color,
                hover_color=hex_color,
                text=hex_color.upper(),
                text_color=get_contrast_color(hex_color),
            )

    def _sync_draft_from_controls(self):
        self._draft = normalize_theme(
            {
                "outer": self.color_vars["outer"].get(),
                "mid": self.color_vars["mid"].get(),
                "inner": self.color_vars["inner"].get(),
                "chapter_title": self.color_vars["chapter_title"].get(),
                "player_action": self.color_vars["player_action"].get(),
                "border_w": int(self.border_slider.get()),
                "rounding": int(self.round_slider.get()),
            }
        )

    def _load_selected_preset(self, name):
        if self._suppress_preset_sync:
            return
        preset = self.themes.get(name)
        if not isinstance(preset, dict):
            return
        self._draft = normalize_theme(preset)
        self.color_vars["outer"].set(self._draft["outer"])
        self.color_vars["mid"].set(self._draft["mid"])
        self.color_vars["inner"].set(self._draft["inner"])
        self.color_vars["chapter_title"].set(self._draft["chapter_title"])
        self.color_vars["player_action"].set(self._draft["player_action"])
        self.border_slider.set(self._draft["border_w"])
        self.round_slider.set(self._draft["rounding"])
        self._refresh_preview()

    def _refresh_preview(self):
        self._sync_draft_from_controls()
        theme = self._draft
        self.preview_outer.configure(fg_color=theme["outer"])
        self.preview_mid.configure(fg_color=theme["mid"])
        apply_card_style(self.preview_card, theme)
        text = get_contrast_color(theme["inner"])
        muted = get_muted_text_color(theme["inner"])
        self.preview_chapter.configure(text_color=theme["chapter_title"])
        self.preview_meta.configure(text_color=muted)
        self.preview_action.configure(text_color=theme["player_action"])
        self.preview_prose.configure(text_color=text)
        self._update_color_swatches()

    def _save_new_preset(self):
        dialog = ctk.CTkInputDialog(text="Enter a name for this preset:", title="Save Preset")
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        if name in self.themes and not messagebox.askyesno(
            "Overwrite?", f"Preset '{name}' already exists. Overwrite it?"
        ):
            return
        self.themes[name] = dict(self._draft)
        save_themes(self.themes)
        self._refresh_preset_menu(select=name)
        messagebox.showinfo("Saved", f"Preset '{name}' saved to themes.json.")

    def _overwrite_preset(self):
        name = self.preset_var.get()
        if name not in self.themes:
            messagebox.showerror("Error", "Select a valid preset to overwrite.")
            return
        if not messagebox.askyesno("Confirm", f"Overwrite preset '{name}' with current settings?"):
            return
        self.themes[name] = dict(self._draft)
        save_themes(self.themes)
        messagebox.showinfo("Saved", f"Preset '{name}' updated.")

    def _delete_preset(self):
        name = self.preset_var.get()
        if name == DEFAULT_THEME_PRESET:
            messagebox.showerror("Protected", f"'{DEFAULT_THEME_PRESET}' cannot be deleted.")
            return
        if name not in self.themes:
            return
        if not messagebox.askyesno("Delete Preset", f"Delete preset '{name}' permanently?"):
            return
        del self.themes[name]
        save_themes(self.themes)
        self._refresh_preset_menu(select=DEFAULT_THEME_PRESET)
        self._load_selected_preset(DEFAULT_THEME_PRESET)

    def _refresh_preset_menu(self, select=None):
        names = sorted(self.themes.keys())
        self._suppress_preset_sync = True
        self.preset_menu.configure(values=names)
        pick = select if select in names else DEFAULT_THEME_PRESET
        self.preset_var.set(pick)
        self._suppress_preset_sync = False

    def _apply_theme(self):
        self._sync_draft_from_controls()
        preset_name = self.preset_var.get().strip() or DEFAULT_THEME_PRESET
        self.themes[preset_name] = dict(self._draft)
        save_themes(self.themes)

        if self.mode == "global":
            ENGINE_CONFIG["global_theme_name"] = preset_name
            save_json_atomically(ENGINE_CONFIG, ROOT_DIR / "configs" / "engine_config.json")
        self._notify_applied()

    def _notify_applied(self):
        if callable(self.on_theme_applied):
            self.on_theme_applied(self.preset_var.get(), dict(self._draft))
