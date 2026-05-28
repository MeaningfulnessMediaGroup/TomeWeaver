"""Dedicated Prose Lint settings dialog (Phases 1–3).

Centralizes spell, grammar, synonym, locale, and lexicon-scope toggles that
were previously scattered in Global Settings. Saves via :func:`save_engine_config`
so unrelated engine keys are preserved.
"""

from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox

from config import (
    ENGINE_CONFIG,
    LOCALE_LABELS,
    SCOPE_LABELS,
    save_engine_config,
)
from ui.tooltip import Tooltip, center_window_on_parent

# Human-readable option menu labels ↔ engine_config values.
_LOCALE_DISPLAY = [
    LOCALE_LABELS["american"],
    LOCALE_LABELS["british"],
    LOCALE_LABELS["both"],
]
_SCOPE_DISPLAY = [SCOPE_LABELS["story"], SCOPE_LABELS["universe"], SCOPE_LABELS["global"]]
_LOCALE_TO_VALUE = {v: k for k, v in LOCALE_LABELS.items()}
_SCOPE_TO_VALUE = {v: k for k, v in SCOPE_LABELS.items()}


class ProseLintSettingsDialog(ctk.CTkToplevel):
    """Global prose lint configuration: spell, grammar, locale, dictionary scope."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Prose Lint Settings")
        self.geometry("640x620")
        self.attributes("-topmost", True)
        self.grab_set()
        center_window_on_parent(self, parent.winfo_toplevel())

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(20, 10))

        ctk.CTkLabel(
            scroll,
            text="Offline prose linting for Edit Scene and inline timeline editing.",
            font=("Arial", 12),
            text_color="gray",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        self._vars = {}

        ctk.CTkLabel(scroll, text="--- Features ---", text_color="gray").pack(pady=(8, 5))
        self._add_switch(
            scroll,
            "Enable Inline Prose Editing",
            "inline_prose_edit",
            "Edit story prose directly on timeline cards (debounced auto-save).",
            default=False,
        )
        self._add_switch(
            scroll,
            "Offline Spell Check",
            "offline_spell_check",
            "Red underlines for likely typos (local dictionary + story/universe allowlist).",
            default=True,
        )
        self._add_switch(
            scroll,
            "Offline Grammar Check",
            "offline_grammar_check",
            "Amber underlines for common grammar/style rules (spaces, agreement, dialogue-safe).",
            default=True,
        )
        self._add_switch(
            scroll,
            "Offline Synonyms",
            "offline_synonyms",
            "Right-click any word for WordNet synonyms (no underlines; lookup when you open the menu).",
            default=False,
        )
        self._add_switch(
            scroll,
            "AI Spelling Suggestions",
            "spell_ai_suggestions",
            "Right-click menu can ask your active LLM for quick replacements (local if using LM Studio).",
            default=True,
        )

        ctk.CTkLabel(scroll, text="--- Spelling ---", text_color="gray").pack(pady=(16, 5))
        self._add_locale_option(scroll)

        ctk.CTkLabel(scroll, text="--- Custom dictionary ---", text_color="gray").pack(pady=(16, 5))
        self._add_scope_option(scroll)

        from config import get_adventures_dir

        adv = get_adventures_dir()
        ctk.CTkLabel(
            scroll,
            text=(
                "Lexicon files (merged when checking):\n"
                f"  • Global: {adv / 'spelling_lexicon_global.json'}\n"
                "  • Universe: {universe}/spelling_lexicon.json (Shared Universe root)\n"
                "  • Story: {cartridge}/spelling_lexicon.json\n\n"
                "Auto-allowlist (not saved to disk): setup + Memory & Lore entity names "
                "from this story and, when tethered, the universe shared_memory ledgers."
            ),
            font=("Arial", 11),
            text_color="gray",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(4, 8))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            btn_row,
            text="Save",
            font=("Arial", 14, "bold"),
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            command=self._save,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_row, text="Cancel", command=self.destroy).pack(side="right")

    def _add_switch(self, parent, label, key, tooltip, default=False):
        """Register a boolean ``ENGINE_CONFIG`` key bound to a CTkSwitch."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        lbl = ctk.CTkLabel(row, text=label, font=("Arial", 13, "bold"), width=220, anchor="e")
        lbl.pack(side="left", padx=(0, 12))
        Tooltip(lbl, tooltip)
        var = ctk.BooleanVar(value=bool(ENGINE_CONFIG.get(key, default)))
        ctk.CTkSwitch(row, text="", variable=var).pack(side="left")
        self._vars[key] = ("bool", var)

    def _add_locale_option(self, parent):
        """American / British / Both Allowed spelling preference."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        lbl = ctk.CTkLabel(row, text="Spelling locale:", font=("Arial", 13, "bold"), width=220, anchor="e")
        lbl.pack(side="left", padx=(0, 12))
        Tooltip(lbl, "American accepts color; British prefers colour and flags US spellings (and vice versa).")
        stored = str(ENGINE_CONFIG.get("spelling_locale", "american")).strip().lower()
        display = LOCALE_LABELS.get(stored, LOCALE_LABELS["american"])
        var = ctk.StringVar(value=display)
        ctk.CTkOptionMenu(row, variable=var, values=_LOCALE_DISPLAY, width=200).pack(side="left")
        self._vars["spelling_locale"] = ("locale", var)

    def _add_scope_option(self, parent):
        """Story / universe / global write target for Add and Ignore actions."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        lbl = ctk.CTkLabel(row, text="Save added words to:", font=("Arial", 13, "bold"), width=220, anchor="e")
        lbl.pack(side="left", padx=(0, 12))
        Tooltip(
            lbl,
            "Where right-click Add / Ignore writes. All lexicon layers merge when checking.",
        )
        stored = str(ENGINE_CONFIG.get("custom_dictionary_scope", "story")).strip().lower()
        display = SCOPE_LABELS.get(stored, SCOPE_LABELS["story"])
        var = ctk.StringVar(value=display)
        ctk.CTkOptionMenu(row, variable=var, values=_SCOPE_DISPLAY, width=200).pack(side="left")
        self._vars["custom_dictionary_scope"] = ("scope", var)

    def _save(self):
        """Merge widget values into ``engine_config.json`` and close."""
        updates = {}
        for key, spec in self._vars.items():
            kind, widget = spec
            if kind == "bool":
                updates[key] = bool(widget.get())
            elif kind == "locale":
                updates[key] = _LOCALE_TO_VALUE.get(widget.get(), "american")
            elif kind == "scope":
                updates[key] = _SCOPE_TO_VALUE.get(widget.get(), "story")

        try:
            save_engine_config(updates)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save prose lint settings: {exc}", parent=self)


def open_prose_lint_settings(parent):
    """Open the Prose Lint settings dialog."""
    ProseLintSettingsDialog(parent)
