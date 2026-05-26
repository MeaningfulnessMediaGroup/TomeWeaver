"""
TomeWeaver: Memory & Lore UI
----------------------------
RAG (Retrieval-Augmented Generation) viewer for long-term story memory.

Layout (tabbed navigation):
    - Top tab bar: Chapters, Plot, Characters, Locations, Artifacts, Factions.
    - Summary tabs (Chapters / Plot): full-width ledger editors; no side list.
    - Entity tabs: 280px entity list (with optional name filter) + Lore Bible editor.

Extend ``MEMORY_TAB_REGISTRY`` to add new ledger categories without rewriting navigation.
"""
import json
import customtkinter as ctk
from tkinter import messagebox
from ui.tooltip import Tooltip

# Registry of top-level Memory tab definitions.
#
# Keys per entry:
#   id            — internal tab identifier (stored in active_tab)
#   label         — button caption (badge count appended at runtime)
#   kind          — "summary" (full-width ledger) or "ledger" (entity list + editor)
#   selection     — active_selection value for summary tabs (e.g. PLOT_LEDGER)
#   ledger_type   — engine.memory key for entity tabs
#   prefix        — entity selection token prefix (CHAR, LOC, ART, FAC)
#   emoji         — list icon for entity rows
#   add_label     — singular noun for the "+ Add …" button
#   requires_factions — if True, tab hidden unless track_factions is enabled
#   badge         — callable(engine) -> int shown in tab label
MEMORY_TAB_REGISTRY = [
    {
        "id": "chapters",
        "label": "Chapters",
        "kind": "summary",
        "selection": "CHAPTER_LEDGER",
        "badge": lambda engine: len(engine.memory.get("chapter_ledger", [])),
    },
    {
        "id": "plot",
        "label": "Plot",
        "kind": "summary",
        "selection": "PLOT_LEDGER",
        "badge": lambda engine: len(engine.memory.get("plot_ledger", [])),
    },
    {
        "id": "characters",
        "label": "Characters",
        "kind": "ledger",
        "ledger_type": "character_ledger",
        "prefix": "CHAR",
        "emoji": "👤",
        "add_label": "Character",
        "badge": lambda engine: _count_ledger_entities(engine, "character_ledger"),
    },
    {
        "id": "locations",
        "label": "Locations",
        "kind": "ledger",
        "ledger_type": "location_ledger",
        "prefix": "LOC",
        "emoji": "📍",
        "add_label": "Location",
        "badge": lambda engine: _count_ledger_entities(engine, "location_ledger"),
    },
    {
        "id": "artifacts",
        "label": "Artifacts",
        "kind": "ledger",
        "ledger_type": "artifact_ledger",
        "prefix": "ART",
        "emoji": "💎",
        "add_label": "Artifact",
        "badge": lambda engine: _count_ledger_entities(engine, "artifact_ledger"),
    },
    {
        "id": "factions",
        "label": "Factions",
        "kind": "ledger",
        "ledger_type": "faction_ledger",
        "prefix": "FAC",
        "emoji": "🛡️",
        "add_label": "Faction",
        "requires_factions": True,
        "badge": lambda engine: _count_ledger_entities(engine, "faction_ledger"),
    },
]

# Show the entity-list filter field when a ledger tab exceeds this many entries.
ENTITY_FILTER_THRESHOLD = 15


def _count_ledger_entities(engine, ledger_type):
    """Return the number of distinct entity names in a ledger (local + global).

    Args:
        engine: Active headless engine with loaded ``memory.json``.
        ledger_type: One of ``character_ledger``, ``location_ledger``, etc.

    Returns:
        int: Count of unique keys across both scopes.
    """
    seen = set()
    for scope in ("global", "local"):
        bucket = engine.memory.get(ledger_type, {}).get(scope, {})
        if isinstance(bucket, dict):
            seen.update(bucket.keys())
    return len(seen)


def _ledger_tab_id(ledger_type):
    """Map an engine ledger key to its Memory tab ``id``.

    Args:
        ledger_type: Engine memory key (e.g. ``character_ledger``).

    Returns:
        str | None: Tab id from ``MEMORY_TAB_REGISTRY``, or None if unknown.
    """
    for tab in MEMORY_TAB_REGISTRY:
        if tab.get("ledger_type") == ledger_type:
            return tab["id"]
    return None


class MemoryTab(ctk.CTkFrame):
    """Memory & Lore workspace tab: tabbed RAG viewer and entity editor.

    Navigation state:
        active_tab       — current top-level tab id (chapters, plot, characters, …)
        active_selection — CHAPTER_LEDGER / PLOT_LEDGER or ``PREFIX_scope_name``
        _tab_selections  — per-tab last entity selection (restored when revisiting)
    """

    def __init__(self, parent, engine):
        """Build the tab bar, optional entity list pane, and editor region.

        Args:
            parent: Workspace tab container.
            engine: Active headless engine instance.
        """
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        self._last_render_time = 0 
        
        # --- HEADER ---
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(hdr, text="Long-Term Memory Ledger", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(side="left", padx=5, pady=10)
        
        self.btn_compile = ctk.CTkButton(hdr, text="🔄 Compile Missing History", font=("Arial", 12, "bold"), fg_color="#F57C00", hover_color="#E65100", command=self._compile_history)
        self.btn_compile.pack(side="right", padx=10)
        Tooltip(self.btn_compile, "Scans your past turns and generates memory for any missing chunks.")
        
        self.btn_clear = ctk.CTkButton(hdr, text="🧨 Clear...", font=("Arial", 12, "bold"), fg_color="#D32F2F", hover_color="#9A0007", command=self._show_clear_dialog)
        self.btn_clear.pack(side="right", padx=(10, 0))

        # Tab navigation state (see class docstring).
        self.active_tab = ctk.StringVar(value="plot")
        self.active_selection = ctk.StringVar(value="PLOT_LEDGER")
        self._tab_selections = {}
        self._left_pane_visible = False
        self.entity_filter_var = ctk.StringVar(value="")
        self._tab_buttons = {}
        self._suppress_filter_trace = False

        # --- TOP TAB BAR ---
        tab_bar = ctk.CTkFrame(self, fg_color="transparent")
        tab_bar.pack(fill="x", padx=10, pady=(0, 4))
        self._build_tab_bar(tab_bar)

        # --- MAIN CONTENT (grid: optional left list + right editor) ---
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.content.grid_columnconfigure(1, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.left_bucket = ctk.CTkFrame(self.content, width=280, fg_color="transparent")
        self.left_bucket.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.left_bucket.grid_rowconfigure(1, weight=1)
        self.left_bucket.grid_columnconfigure(0, weight=1)

        self.right_bucket = ctk.CTkFrame(self.content, fg_color="transparent")
        self.right_bucket.grid(row=0, column=1, sticky="nsew")

        self.filter_frame = ctk.CTkFrame(self.left_bucket, fg_color="transparent")
        self.filter_entry = ctk.CTkEntry(
            self.filter_frame,
            textvariable=self.entity_filter_var,
            placeholder_text="Filter list…",
            font=("Arial", 13),
        )
        self.filter_entry.pack(fill="x", padx=4, pady=(4, 6))
        Tooltip(self.filter_entry, "Filter the entity list by name (shown when there are more than 15 entries).")
        self.entity_filter_var.trace_add("write", lambda *_: self._on_filter_changed())

        # Entity list (ledger tabs only).
        self.nav_frame = ctk.CTkScrollableFrame(self.left_bucket, width=260)
        self.nav_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        self.btn_add_entity = ctk.CTkButton(
            self.left_bucket,
            text="+ Add",
            fg_color="#4A4A4A",
            hover_color="#333333",
            command=self._add_entity_for_active_tab,
        )
        self.btn_add_entity.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 4))

        self.editor_master = ctk.CTkFrame(self.right_bucket, fg_color="transparent")
        self.editor_master.pack(fill="both", expand=True)

        self._switch_tab("plot", initial=True)

    def _compile_history(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Retroactive Compiler")
        dialog.geometry("500x400") # Made slightly taller for the 4th option
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Compile Long-Term Memory", font=("Arial", 16, "bold"), text_color="#00ACC1").pack(pady=(20, 10))
        ctk.CTkLabel(dialog, text="This will scan your history and ask the AI to generate missing data. This consumes API tokens.", wraplength=400, text_color="gray").pack(padx=20, pady=(0, 20))

        # Load the last used mode from engine settings (defaults to 'missing' on first run)
        v_mode = ctk.StringVar(value=self.engine.setup_data.get("last_compile_mode", "missing"))
        
        rb_base = ctk.CTkRadioButton(dialog, text="Base Lore Only (Parse setup.json and Prologue)", variable=v_mode, value="base")
        rb_base.pack(anchor="w", padx=40, pady=(0, 10))
        Tooltip(rb_base, "Extracts static traits from your World Builder text without reading the gameplay turns.")
        
        ctk.CTkRadioButton(dialog, text="Standard Compile (Only missing chunks)", variable=v_mode, value="missing").pack(anchor="w", padx=40, pady=10)
        
        rb_force = ctk.CTkRadioButton(dialog, text="Deep Entity Scan (Re-read all chunks)", variable=v_mode, value="force")
        rb_force.pack(anchor="w", padx=40, pady=10)
        Tooltip(rb_force, "If you just added a new Character/Location, use this to scan the entire history for past events involving them.")
        
        rb_verify = ctk.CTkRadioButton(dialog, text="Integrity Check & Reconcile (Fast Verification)", variable=v_mode, value="verify")
        rb_verify.pack(anchor="w", padx=40, pady=10)
        Tooltip(rb_verify, "Reads the already summarized Plot Ledger and Lore Bible to check for logical contradictions. Runs Auto-Reconcile if checked.")

        # Divider
        ctk.CTkFrame(dialog, height=2, fg_color="#333333").pack(fill="x", padx=40, pady=15)

        def apply_compile():
            mode_selection = v_mode.get()
            
            # Save preferences to setup.json so they persist
            self.engine.setup_data["last_compile_mode"] = mode_selection
            from config import save_json_atomically
            save_json_atomically(self.engine.setup_data, self.engine.adv_dir / "setup.json")
            
            dialog.destroy()
            
            self.winfo_toplevel().configure(cursor="watch")
            self.btn_compile.configure(state="disabled", text="Initializing...")
            
            def on_progress(current, total, start_t=None, end_t=None):
                if current == "Seeding":
                    msg = "Extracting Base Lore..."
                else:
                    msg = f"Processing Chunk {current}/{total}..."
                self.after(0, lambda: self.btn_compile.configure(text=msg))
                
            def on_complete(success, msg):
                def update_ui():
                    self.winfo_toplevel().configure(cursor="") # Restore cursor
                    self.btn_compile.configure(state="normal", text="🔄 Compile Missing History")
                    
                    if mode_selection == "verify":
                        self._show_verification_report(msg)
                    else:
                        messagebox.showinfo("Complete", msg)
                        
                    self._refresh_all()
                self.after(0, update_ui)
                
            self.engine.compile_missing_memories(
                compile_mode=mode_selection, 
                progress_callback=on_progress, 
                completion_callback=on_complete
            )

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Start Compiler", width=120, fg_color="#F57C00", hover_color="#E65100", command=apply_compile).pack(side="right", padx=10)

    def _show_verification_report(self, report_text, patch_callback=None):
        """Spawns a scrollable text window to display the Continuity Editor's report."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Continuity & Integrity Report")
        dialog.geometry("650x500")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())
        
        is_clear = "Nothing to report" in report_text or "100/100" in report_text
        hdr_color = "#4CAF50" if is_clear else "#F57C00"
        hdr_text = "Verification Complete: No Issues Found" if is_clear else "Verification Complete: Potential Issues Found"

        ctk.CTkLabel(dialog, text=hdr_text, font=("Arial", 16, "bold"), text_color=hdr_color).pack(pady=(20, 10))

        box = ctk.CTkTextbox(dialog, wrap="word", font=("Arial", 14))
        box.insert("1.0", report_text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=20, pady=10)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkButton(btn_frame, text="Close Report", fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left", expand=True, padx=10)
        
        # Only show the Auto-Patch button if there are issues AND a callback was provided
        if patch_callback and not is_clear:
            btn_patch = ctk.CTkButton(btn_frame, text="🔧 Auto-Patch Summary", fg_color="#009688", hover_color="#00796B", command=lambda: patch_callback(dialog))
            btn_patch.pack(side="right", expand=True, padx=10)
            Tooltip(btn_patch, "Ask the AI to automatically rewrite the summary to fix these exact issues.")
        
    def _show_clear_dialog(self):
        """Spawns a granular memory-wipe dialog with scope-awareness."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Clear Memory")
        dialog.geometry("480x550")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Maintenance: Prune Memory", font=("Arial", 18, "bold"), text_color="#D32F2F").pack(pady=(20, 10))
        
        # --- 1. SCOPE SELECTION ---
        ctk.CTkLabel(dialog, text="Target Scope:", font=("Arial", 12, "bold"), text_color="#00BCD4").pack(anchor="w", padx=40)
        v_scope = ctk.StringVar(value="local")
        
        scope_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        scope_frame.pack(fill="x", padx=40, pady=(5, 15))
        
        rb_loc = ctk.CTkRadioButton(scope_frame, text="Local Thread", variable=v_scope, value="local")
        rb_loc.pack(side="left", padx=(0, 20))
        
        is_univ = self.engine.is_universe_thread
        rb_glo = ctk.CTkRadioButton(scope_frame, text="Global Universe", variable=v_scope, value="global", state="normal" if is_univ else "disabled")
        rb_glo.pack(side="left")
        if is_univ: Tooltip(rb_glo, "WARNING: This affects ALL stories in this universe.")

        # --- 2. ACTION SELECTION ---
        ctk.CTkLabel(dialog, text="Wipe Options:", font=("Arial", 12, "bold"), text_color="#00BCD4").pack(anchor="w", padx=40)
        
        v_plot = ctk.BooleanVar(value=True)
        v_bullets = ctk.BooleanVar(value=True)
        v_entities = ctk.BooleanVar(value=False)

        ctk.CTkSwitch(dialog, text="Clear Plot Summaries & Chapters", variable=v_plot).pack(anchor="w", padx=50, pady=8)
        ctk.CTkSwitch(dialog, text="Clear AI-Tracked Events (Keep Names)", variable=v_bullets).pack(anchor="w", padx=50, pady=8)
        ctk.CTkSwitch(dialog, text="Nuclear Wipe (Delete Entities entirely)", variable=v_entities).pack(anchor="w", padx=50, pady=8)

        def apply_clear():
            scope = v_scope.get()
            ledgers = ["character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"]

            # Confirm Global Nuclear Wipe
            if scope == "global" and v_entities.get():
                if not messagebox.askyesno("Confirm Global Wipe", "This will PERMANENTLY delete every character and location from the Shared World Bible.\n\nAre you absolutely sure?"):
                    return

            if v_plot.get():
                # Plot and Chapters are inherently Local to the story
                self.engine.memory["plot_ledger"] = []
                self.engine.memory["chapter_ledger"] = [] 
            
            if v_bullets.get():
                # Wipe events but keep traits and author notes
                for l in ledgers:
                    for k in self.engine.memory[l].get(scope, {}): 
                        ent = self.engine.memory[l][scope][k]
                        ent["ledger"] = []
                        # Optionally clear characteristics but keep the object
                        # ent["characteristics"] = {}
            
            if v_entities.get():
                # Complete removal from the targeted scope
                for l in ledgers:
                    self.engine.memory[l][scope] = {}
                self.engine.memory["aliases"][scope] = {l: {} for l in ledgers}
                if scope == "global":
                    self.engine.memory["global_states"] = {}
                
            self.engine.save_state()
            self.active_tab.set("plot")
            self._switch_tab("plot")
            dialog.destroy()
            messagebox.showinfo("Memory Pruned", f"Successfully updated {scope} memory banks.")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=30)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Execute Prune", width=120, fg_color="#B71C1C", hover_color="#7F0000", command=apply_clear).pack(side="right", padx=10)

    # ---------------------------------------------------------
    # TAB NAVIGATION (top bar + entity list pane)
    # ---------------------------------------------------------

    def _get_visible_tabs(self):
        """Return registry entries visible for the current story settings."""
        tabs = []
        for tab in MEMORY_TAB_REGISTRY:
            if tab.get("requires_factions") and not self.engine.setup_data.get("track_factions", False):
                continue
            tabs.append(tab)
        return tabs

    def _get_tab_config(self, tab_id):
        """Resolve a tab id to its registry dict, falling back to the first visible tab."""
        for tab in self._get_visible_tabs():
            if tab["id"] == tab_id:
                return tab
        return self._get_visible_tabs()[0]

    def _tab_label(self, tab):
        """Format a tab button caption with live badge count."""
        count = tab["badge"](self.engine)
        return f"{tab['label']} ({count})"

    def _build_tab_bar(self, parent):
        """Create top-level Memory tab buttons from ``MEMORY_TAB_REGISTRY``."""
        for tab in self._get_visible_tabs():
            btn = ctk.CTkButton(
                parent,
                text=self._tab_label(tab),
                height=32,
                fg_color="#4A4A4A",
                hover_color="#333333",
                command=lambda tid=tab["id"]: self._switch_tab(tid),
            )
            btn.pack(side="left", padx=(0, 6), pady=4)
            self._tab_buttons[tab["id"]] = btn

    def _update_tab_badges(self):
        """Refresh badge counts on all tab buttons after memory changes."""
        for tab in self._get_visible_tabs():
            btn = self._tab_buttons.get(tab["id"])
            if btn:
                btn.configure(text=self._tab_label(tab))

    def _on_filter_changed(self):
        """Re-render the entity list when the filter field changes."""
        if self._suppress_filter_trace:
            return
        self._refresh_entity_list()

    def _set_left_pane_visible(self, visible):
        """Show or hide the entity list column (grid_remove for summary tabs).

        Uses ``grid`` / ``grid_remove`` instead of ``PanedWindow.forget`` so
        CustomTkinter frames remain reliable on Windows.
        """
        if visible:
            self.left_bucket.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            self.content.grid_columnconfigure(0, minsize=280, weight=0)
        else:
            self.left_bucket.grid_remove()
            self.content.grid_columnconfigure(0, minsize=0, weight=0)
        self._left_pane_visible = visible

    def _switch_tab(self, tab_id, initial=False):
        """Activate a top-level tab and sync list pane, selection, and editor.

        Args:
            tab_id: Registry tab id (e.g. ``characters``).
            initial: If True, skip persisting the previous tab's selection.
        """
        if not initial:
            prev = self._get_tab_config(self.active_tab.get())
            if prev["kind"] == "ledger":
                self._tab_selections[prev["id"]] = self.active_selection.get()
            elif prev["kind"] == "summary":
                self._tab_selections[prev["id"]] = prev["selection"]

        tab = self._get_tab_config(tab_id)
        self.active_tab.set(tab["id"])

        for tid, btn in self._tab_buttons.items():
            if tid == tab["id"]:
                btn.configure(fg_color="#1565C0", hover_color="#0D47A1")
            else:
                btn.configure(fg_color="#4A4A4A", hover_color="#333333")

        if tab["kind"] == "summary":
            self._set_left_pane_visible(False)
            self.active_selection.set(tab["selection"])
        else:
            self._set_left_pane_visible(True)
            self._suppress_filter_trace = True
            self.entity_filter_var.set("")
            self._suppress_filter_trace = False
            saved = self._tab_selections.get(tab["id"], "")
            if saved and self._selection_matches_tab(saved, tab):
                self.active_selection.set(saved)
            else:
                self.active_selection.set("")
            self.btn_add_entity.configure(text=f"+ Add {tab['add_label']}")
            self._refresh_entity_list()

        self._update_tab_badges()
        self._render_view()

    def _selection_matches_tab(self, selection, tab):
        """Return True if ``selection`` belongs to the given ledger tab."""
        if not selection or tab.get("kind") != "ledger":
            return False
        prefix = tab.get("prefix", "")
        return selection.startswith(f"{prefix}_")

    def _refresh_all(self):
        """Rebuild badges, entity list (if applicable), and the active editor view."""
        self._update_tab_badges()
        tab = self._get_tab_config(self.active_tab.get())
        if tab["kind"] == "ledger":
            self._refresh_entity_list()
        self._render_view()

    def _refresh_entity_list(self):
        """Populate the left-pane list for the active ledger tab.

        Shows a name filter when entry count exceeds ``ENTITY_FILTER_THRESHOLD``.
        Entity rows use ``PREFIX_scope_name`` selection tokens consumed by ``_render_view``.
        """
        tab = self._get_tab_config(self.active_tab.get())
        if tab["kind"] != "ledger":
            return

        for w in self.nav_frame.winfo_children():
            w.destroy()

        ledger_type = tab["ledger_type"]
        entity_count = _count_ledger_entities(self.engine, ledger_type)
        filter_text = self.entity_filter_var.get().strip().lower()

        if entity_count > ENTITY_FILTER_THRESHOLD:
            self.filter_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        else:
            self.filter_frame.grid_remove()
            if filter_text:
                self._suppress_filter_trace = True
                self.entity_filter_var.set("")
                self._suppress_filter_trace = False

        def get_state_icon(data_obj, entity_name, scope):
            if not isinstance(data_obj, dict):
                return ""
            if scope == "global" and self.engine.is_universe_thread:
                s = self.engine.memory.get("global_states", {}).get(entity_name, {}).get("state", "archived")
            else:
                s = data_obj.get("state", "active")
            if s == "pinned":
                return "📌 "
            if s == "archived":
                return "📦 "
            return ""

        entities = {}
        for scope in ["global", "local"]:
            for name, data in self.engine.memory.get(ledger_type, {}).get(scope, {}).items():
                if isinstance(data, list):
                    continue
                entities.setdefault(name, []).append((scope, data))

        mode_color = "#2196F3" if self.engine.setup_data.get("mode", "sandbox") == "sandbox" else "#9C27B0"
        is_univ = self.engine.is_universe_thread
        visible_rows = 0

        for name in sorted(entities.keys()):
            for scope, data in entities[name]:
                if filter_text and filter_text not in name.lower():
                    continue

                r = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
                r.pack(fill="x", pady=2)
                visible_rows += 1

                s_icon = get_state_icon(data, name, scope)
                e_color = "#FF9800" if (is_univ and scope == "global") else (mode_color if is_univ else "white")
                display_text = f"{tab['emoji']} {s_icon}{name}"
                sel_val = f"{tab['prefix']}_{scope}_{name}"

                rb = ctk.CTkRadioButton(
                    r,
                    text=display_text,
                    text_color=e_color,
                    variable=self.active_selection,
                    value=sel_val,
                    command=self._on_entity_selected,
                )
                rb.pack(side="left", fill="x", expand=True)

                ctk.CTkButton(
                    r,
                    text="X",
                    width=20,
                    fg_color="#B71C1C",
                    hover_color="#7F0000",
                    command=lambda n=name, s=scope, lt=ledger_type: self._delete_entity(n, s, lt),
                ).pack(side="right")

        if filter_text and visible_rows == 0:
            ctk.CTkLabel(
                self.nav_frame,
                text="No matches for this filter.",
                font=("Arial", 12, "italic"),
                text_color="gray",
            ).pack(pady=20)
        elif entity_count == 0:
            ctk.CTkLabel(
                self.nav_frame,
                text=f"No {tab['label'].lower()} tracked yet.",
                font=("Arial", 12, "italic"),
                text_color="gray",
            ).pack(pady=20)

    def _on_entity_selected(self):
        """Persist the current entity selection for this tab and refresh the editor."""
        tab = self._get_tab_config(self.active_tab.get())
        if tab["kind"] == "ledger":
            self._tab_selections[tab["id"]] = self.active_selection.get()
        self._render_view()

    def _add_entity_for_active_tab(self):
        """Route the '+ Add' button to the ledger type of the active tab."""
        tab = self._get_tab_config(self.active_tab.get())
        if tab["kind"] == "ledger":
            self._add_entity(tab["ledger_type"])

    def _delete_entity(self, name, scope, ledger_type):
        """Remove an entity from memory and clear the tab selection."""
        if messagebox.askyesno("Delete", f"Stop tracking {scope} memory for '{name}'?"):
            if name in self.engine.memory[ledger_type].get(scope, {}):
                del self.engine.memory[ledger_type][scope][name]
                self.engine.save_state()
                tab_id = _ledger_tab_id(ledger_type)
                if tab_id:
                    self._tab_selections[tab_id] = ""
                self.active_selection.set("")
                self._refresh_all()

    def _add_entity(self, ledger_type):
        """Prompt for a name and seed a new local entity in the given ledger."""
        if ledger_type == "character_ledger":
            type_str = "Character"
        elif ledger_type == "location_ledger":
            type_str = "Location"
        elif ledger_type == "faction_ledger":
            type_str = "Faction / Org"
        else:
            type_str = "Artifact"

        dialog = ctk.CTkInputDialog(text=f"Enter the exact name of a {type_str} to track:", title=f"Add {type_str}")
        name = dialog.get_input()
        if name and name.strip():
            clean_name = name.strip()
            if clean_name not in self.engine.memory[ledger_type].get("local", {}):
                self.engine.memory[ledger_type].setdefault("local", {})[clean_name] = {
                    "characteristics": {},
                    "ledger": [],
                    "author_notes": "",
                    "state": "active",
                }
                self.engine.save_state()

                prefix = (
                    "CHAR_"
                    if ledger_type == "character_ledger"
                    else ("LOC_" if ledger_type == "location_ledger" else ("FAC_" if ledger_type == "faction_ledger" else "ART_"))
                )
                sel = f"{prefix}_local_{clean_name}"
                tab_id = _ledger_tab_id(ledger_type)
                if tab_id:
                    self._tab_selections[tab_id] = sel
                self.active_selection.set(sel)
                self._refresh_all()

    def _render_empty_entity_state(self, tab):
        """Show a placeholder when no entity is selected on a ledger tab."""
        for w in self.editor_master.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.editor_master,
            text=f"Select a {tab['add_label'].lower()} from the list,\nor use “+ Add {tab['add_label']}” to start tracking one.",
            font=("Arial", 15, "italic"),
            text_color="gray",
            justify="center",
        ).pack(expand=True, pady=80)

    def _render_view(self):
        """Route the right-hand editor to the active tab and selection."""
        import time
        self._last_render_time = time.time()

        for w in self.editor_master.winfo_children():
            w.destroy()

        selection = self.active_selection.get()
        tab = self._get_tab_config(self.active_tab.get())

        if tab["kind"] == "summary":
            if selection == "CHAPTER_LEDGER":
                self._render_chapter_ledger()
            else:
                self._render_plot_ledger()
            return

        if not selection or not self._selection_matches_tab(selection, tab):
            self._render_empty_entity_state(tab)
            return

        parts = selection.split("_", 2)
        if len(parts) != 3:
            self._render_empty_entity_state(tab)
            return

        prefix, scope, entity_name = parts
        if prefix == "CHAR":
            self._render_entity_editor(entity_name, scope, "character_ledger")
        elif prefix == "LOC":
            self._render_entity_editor(entity_name, scope, "location_ledger")
        elif prefix == "ART":
            self._render_entity_editor(entity_name, scope, "artifact_ledger")
        elif prefix == "FAC":
            self._render_entity_editor(entity_name, scope, "faction_ledger")
        else:
            self._render_empty_entity_state(tab)
                
                
    # ---------------------------------------------------------
    # PLOT LEDGER VIEW
    # ---------------------------------------------------------
    def _render_plot_ledger(self):
        for w in self.editor_master.winfo_children(): w.destroy()
        
        # --- STICKY HEADER & DIRTY TRACKER ---
        hdr = ctk.CTkFrame(self.editor_master, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(10, 5))
        
        title_stack = ctk.CTkFrame(hdr, fg_color="transparent")
        title_stack.pack(side="left")
        ctk.CTkLabel(title_stack, text="The Plot Ledger (Chronological Summaries)", font=("Arial", 18, "bold")).pack(anchor="w")
        ctk.CTkLabel(title_stack, text="The AI automatically compresses long chapters into chunks so it never forgets the past.", text_color="gray").pack(anchor="w")
        
        btn_save_plot = ctk.CTkButton(hdr, text="💾 Save Summaries", font=("Arial", 14, "bold"), height=36, command=self._save_plot_ledger)
        btn_save_plot.pack(side="right", padx=10)
        
        def mark_dirty(*args):
            btn_save_plot.configure(state="normal", fg_color="#2E7D32", text="💾 Save Summaries")

        def mark_clean():
            btn_save_plot.configure(state="disabled", fg_color="#4A4A4A", text="💾 Saved")
            
        mark_clean() # Initialize in safe state
        
        # Override the class method locally so the button resets when clicked
        original_save = self._save_plot_ledger
        def hooked_save():
            original_save()
            mark_clean()
        btn_save_plot.configure(command=hooked_save)
        
        # --- SCROLLABLE BODY ---
        self.editor_frame = ctk.CTkScrollableFrame(self.editor_master, fg_color="transparent")
        self.editor_frame.pack(fill="both", expand=True)
        
        plot_list = self.engine.memory.get("plot_ledger", [])
        if not plot_list:
            ctk.CTkLabel(self.editor_frame, text="The story hasn't reached the auto-summarize threshold yet.", font=("Arial", 14, "italic")).pack(pady=50)
            return

        self.plot_ui_references = [] 

        for idx, chunk in enumerate(plot_list):
            card = ctk.CTkFrame(self.editor_frame, fg_color="#2B2B2B", corner_radius=8)
            card.pack(fill="x", padx=10, pady=10)
            
            c_hdr = ctk.CTkFrame(card, fg_color="transparent")
            c_hdr.pack(fill="x", padx=15, pady=10)
            
            c_num = chunk.get("chapter_number", "?")
            title = chunk.get("chapter_title", "Unknown Chapter")
            t_start = chunk.get("start_turn", "?")
            t_end = chunk.get("end_turn", "?")
            
            ctk.CTkLabel(c_hdr, text=f"Chapter {c_num}: {title} | Turns {t_start} - {t_end}", font=("Arial", 14, "bold"), text_color="#FFCA28").pack(side="left")
            
            def delete_chunk(c=chunk):
                if messagebox.askyesno("Delete Summary", f"Delete summary for Turns {c.get('start_turn')} - {c.get('end_turn')}?\n\nThe compiler will automatically regenerate it next time you run it."):
                    self.engine.memory["plot_ledger"].remove(c)
                    self.engine.save_state()
                    self._render_view()
                    
            ctk.CTkButton(c_hdr, text="🗑️ Delete", width=60, height=24, fg_color="#B71C1C", hover_color="#7F0000", command=delete_chunk).pack(side="right", padx=(5, 0))
            
            btn_reroll = ctk.CTkButton(c_hdr, text="⟳ Reroll", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
            btn_reroll.pack(side="right", padx=(5, 0))
            
            btn_val = ctk.CTkButton(c_hdr, text="✔️ Validate", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            btn_val.pack(side="right")
            
            box = ctk.CTkTextbox(card, height=120, wrap="word", font=("Arial", 14))
            box.insert("1.0", chunk.get("summary", ""))
            box.bind("<KeyRelease>", mark_dirty) # Flag as dirty when typing
            box.pack(fill="x", padx=15, pady=(0, 15))
            
            # (Validation and Reroll callbacks remain exactly the same...)
            def validate_chunk(c=chunk, b=box, btn=btn_val):
                orig_text = btn.cget("text")
                btn.configure(state="disabled", text="...")
                self.winfo_toplevel().configure(cursor="watch")
                def worker():
                    raw_chunk = [t for t in self.engine.history if c["start_turn"] <= t.get("turn", 0) <= c["end_turn"]]
                    if not raw_chunk:
                        self.after(0, lambda: [messagebox.showerror("Error", "Could not find raw turns for this chunk."), btn.configure(state="normal", text=orig_text), self.winfo_toplevel().configure(cursor="")])
                        return
                    turns_text = "".join([f"Turn {t['turn']} [Loc: {t.get('location', '')}]: {t.get('story_text', '')}\nAction: {t.get('player_choice', '')}\n\n" for t in raw_chunk])
                    current_summary = b.get("1.0", "end").strip()
                    from api import TomeWeaverAPI
                    succ, res = TomeWeaverAPI.validate_plot_chunk(turns_text, current_summary, self.engine.adv_dir)
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn.configure(state="normal", text=orig_text)
                        if succ:
                            def trigger_patch(report_dialog):
                                report_dialog.destroy(); btn.configure(state="disabled", text="Patching..."); self.winfo_toplevel().configure(cursor="watch")
                                def patch_worker():
                                    succ_patch, patched_text = TomeWeaverAPI.patch_plot_chunk(turns_text, current_summary, res, self.engine.adv_dir)
                                    def post_patch_ui():
                                        if succ_patch:
                                            b.delete("1.0", "end"); b.insert("1.0", patched_text)
                                            btn.configure(state="normal", text=orig_text); self.winfo_toplevel().configure(cursor=""); btn.invoke()
                                        else:
                                            btn.configure(state="normal", text=orig_text); self.winfo_toplevel().configure(cursor=""); messagebox.showerror("Patch Error", patched_text)
                                    self.after(0, post_patch_ui)
                                import threading; threading.Thread(target=patch_worker, daemon=True).start()
                            self._show_verification_report(res, patch_callback=trigger_patch)
                        else: messagebox.showerror("Error", res)
                    self.after(0, update_ui)
                import threading; threading.Thread(target=worker, daemon=True).start()
                
            btn_val.configure(command=validate_chunk)
            
            def reroll_chunk(c=chunk, b=box, btn=btn_reroll):
                orig_text = btn.cget("text")
                btn.configure(state="disabled", text="...")
                self.winfo_toplevel().configure(cursor="watch")
                def worker():
                    raw_chunk = [t for t in self.engine.history if c["start_turn"] <= t.get("turn", 0) <= c["end_turn"]]
                    if not raw_chunk:
                        self.after(0, lambda: messagebox.showerror("Error", "Could not find raw turns for this chunk."))
                        return
                    turns_text = "".join([f"Turn {t['turn']} [Loc: {t.get('location', '')}]: {t.get('story_text', '')}\nAction: {t.get('player_choice', '')}\n\n" for t in raw_chunk])
                    from api import TomeWeaverAPI
                    succ, res = TomeWeaverAPI.generate_plot_summary(turns_text, c["start_turn"], c["end_turn"], self.engine.adv_dir)
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn.configure(state="normal", text=orig_text)
                        if succ:
                            b.delete("1.0", "end"); b.insert("1.0", res); self._save_plot_ledger()
                        else: messagebox.showerror("Error", res)
                    self.after(0, update_ui)
                import threading; threading.Thread(target=worker, daemon=True).start()
                
            btn_reroll.configure(command=reroll_chunk)
            self.plot_ui_references.append((chunk, box))

        ctk.CTkLabel(self.editor_frame, text="Use the engine configuration to change the Memory Chunk size.", font=("Arial", 12, "italic"), text_color="#555555").pack(pady=20)


    def _render_chapter_ledger(self):
        for w in self.editor_master.winfo_children(): w.destroy()
        
        # --- STICKY HEADER & DIRTY TRACKER ---
        hdr = ctk.CTkFrame(self.editor_master, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(10, 5))
        
        title_stack = ctk.CTkFrame(hdr, fg_color="transparent")
        title_stack.pack(side="left")
        ctk.CTkLabel(title_stack, text="Chapter Summaries (High-Level Memory)", font=("Arial", 18, "bold")).pack(anchor="w")
        ctk.CTkLabel(title_stack, text="Completed chapters are highly condensed here. This prevents Context Limit crashes in long games.", text_color="gray").pack(anchor="w")
        
        btn_save_chap = ctk.CTkButton(hdr, text="💾 Save Summaries", font=("Arial", 14, "bold"), height=36, command=self._save_chapter_ledger)
        btn_save_chap.pack(side="right", padx=10)
        
        def mark_dirty(*args):
            btn_save_chap.configure(state="normal", fg_color="#2E7D32", text="💾 Save Summaries")

        def mark_clean():
            btn_save_chap.configure(state="disabled", fg_color="#4A4A4A", text="💾 Saved")
            
        mark_clean() # Initialize
        
        original_save = self._save_chapter_ledger
        def hooked_save():
            original_save()
            mark_clean()
        btn_save_chap.configure(command=hooked_save)
        
        # --- SCROLLABLE BODY ---
        self.editor_frame = ctk.CTkScrollableFrame(self.editor_master, fg_color="transparent")
        self.editor_frame.pack(fill="both", expand=True)
        
        chap_list = self.engine.memory.get("chapter_ledger", [])
        if not chap_list:
            ctk.CTkLabel(self.editor_frame, text="No chapters have been completed and summarized yet.", font=("Arial", 14, "italic")).pack(pady=50)
            return

        self.chap_ui_references = [] 

        for idx, chunk in enumerate(chap_list):
            card = ctk.CTkFrame(self.editor_frame, fg_color="#2B2B2B", corner_radius=8)
            card.pack(fill="x", padx=10, pady=10)
            
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=15, pady=10)
            
            c_num = chunk.get("chapter_number", "?")
            title = chunk.get("chapter_title", "Unknown Chapter")
            
            ctk.CTkLabel(hdr, text=f"Chapter {c_num}: {title}", font=("Arial", 16, "bold"), text_color="#00BCD4").pack(side="left")
            
            def delete_chunk(c=chunk):
                if messagebox.askyesno("Delete Summary", f"Delete the high-level summary for Chapter {c.get('chapter_number')}?"):
                    self.engine.memory["chapter_ledger"].remove(c)
                    self.engine.save_state()
                    self._render_view()
                    
            btn_del = ctk.CTkButton(hdr, text="🗑️ Delete", width=60, height=24, fg_color="#B71C1C", hover_color="#7F0000", command=delete_chunk)
            btn_del.pack(side="right", padx=(5, 0))
            
            btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
            btn_reroll.pack(side="right", padx=(5, 0))
            
            btn_val = ctk.CTkButton(hdr, text="✔️ Validate", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            btn_val.pack(side="right")
            
            btn_val = ctk.CTkButton(hdr, text="✔️ Validate", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            btn_val.pack(side="right")
            
            box = ctk.CTkTextbox(card, height=120, wrap="word", font=("Arial", 14))
            box.insert("1.0", chunk.get("summary", ""))
            box.bind("<KeyRelease>", mark_dirty) # Flag dirty on text edit
            box.pack(fill="x", padx=15, pady=(0, 5))
            
            tags_frame = ctk.CTkFrame(card, fg_color="transparent")
            tags_frame.pack(fill="x", padx=15, pady=(0, 15))
            ctk.CTkLabel(tags_frame, text="Tags:", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
            
            tags_var = ctk.StringVar(value=", ".join(chunk.get("tags", [])))
            tags_var.trace_add("write", mark_dirty) # Flag dirty on tags edit
            ctk.CTkEntry(tags_frame, textvariable=tags_var, font=("Arial", 13)).pack(side="left", fill="x", expand=True, padx=10)
            
            def reroll_tags(b=box, t_var=tags_var):
                self.winfo_toplevel().configure(cursor="watch")
                def worker():
                    current_summary = b.get("1.0", "end").strip()
                    from api import TomeWeaverAPI
                    succ, res = TomeWeaverAPI.generate_chapter_tags(current_summary, self.engine.setup_data)
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        if succ and isinstance(res, list):
                            t_var.set(", ".join(res))
                        else:
                            messagebox.showerror("Error", res)
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            btn_reroll_tags = ctk.CTkButton(tags_frame, text="⟳ Tags", width=60, height=24, font=("Arial", 11), fg_color="#7B1FA2", hover_color="#4A148C", command=reroll_tags)
            btn_reroll_tags.pack(side="right")
            Tooltip(btn_reroll_tags, "Regenerate only the thematic tags based on the current summary text.")

            def get_source_text(c_num):
                parts = [p.get('summary', '') for p in self.engine.memory.get("plot_ledger", []) if p.get("chapter_number") == c_num]
                return "\n".join([f"Part {i+1}: {p}" for i, p in enumerate(parts)])
                
            def validate_chunk(c=chunk, b=box, t_var=tags_var, btn=btn_val):
                orig_text = btn.cget("text")
                btn.configure(state="disabled", text="...")
                self.winfo_toplevel().configure(cursor="watch")
                
                def worker():
                    source_text = get_source_text(c.get("chapter_number"))
                    current_json = json.dumps({"summary": b.get("1.0", "end").strip(), "tags": [t.strip() for t in t_var.get().split(",") if t.strip()]})
                    
                    from api import TomeWeaverAPI
                    succ, res = TomeWeaverAPI.validate_chapter_chunk(source_text, current_json)
                    
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn.configure(state="normal", text=orig_text)
                        if succ:
                            def trigger_patch(report_dialog):
                                report_dialog.destroy()
                                btn.configure(state="disabled", text="Patching...")
                                self.winfo_toplevel().configure(cursor="watch")
                                def patch_worker():
                                    succ_patch, patched_data = TomeWeaverAPI.patch_chapter_chunk(source_text, current_json, res)
                                    def post_patch_ui():
                                        if succ_patch and isinstance(patched_data, dict):
                                            b.delete("1.0", "end")
                                            b.insert("1.0", patched_data.get("summary", ""))
                                            t_var.set(", ".join(patched_data.get("tags", [])))
                                            btn.configure(state="normal", text=orig_text)
                                            self.winfo_toplevel().configure(cursor="")
                                            btn.invoke() # Re-validate
                                        else:
                                            btn.configure(state="normal", text=orig_text)
                                            self.winfo_toplevel().configure(cursor="")
                                            messagebox.showerror("Patch Error", patched_data)
                                    self.after(0, post_patch_ui)
                                import threading
                                threading.Thread(target=patch_worker, daemon=True).start()
                            self._show_verification_report(res, patch_callback=trigger_patch)
                        else:
                            messagebox.showerror("Error", res)
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            btn_val.configure(command=validate_chunk)
            
            def reroll_chunk(c=chunk, b=box, t_var=tags_var, btn=btn_reroll):
                orig_text = btn.cget("text")
                btn.configure(state="disabled", text="...")
                self.winfo_toplevel().configure(cursor="watch")
                
                def worker():
                    source_text = get_source_text(c.get("chapter_number"))
                    from api import TomeWeaverAPI
                    
                    # FIXED CALL:
                    succ, res = TomeWeaverAPI.generate_chapter_summary(source_text, self.engine.setup_data)
                    
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn.configure(state="normal", text=orig_text)
                        if succ and isinstance(res, dict):
                            b.delete("1.0", "end")
                            b.insert("1.0", res.get("summary", ""))
                            t_var.set(", ".join(res.get("tags", [])))
                        else:
                            messagebox.showerror("Error", str(res))
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            btn_reroll.configure(command=reroll_chunk)
            self.chap_ui_references.append((chunk, box, tags_var))


    def _render_entity_editor(self, entity_name, scope, ledger_type):
        """
        The Master Entity Editor.
        Handles data display, name collisions, deep-renaming across files, 
        cross-scope promotion/demotion, and dirty-state tracking.
        """
        if ledger_type == "character_ledger": icon = "👤"
        elif ledger_type == "location_ledger": icon = "📍"
        elif ledger_type == "faction_ledger": icon = "🛡️"
        else: icon = "💎"
        
        # --- 1. DATA EXTRACTION ---
        active_data = self.engine.memory[ledger_type].get(scope, {}).get(entity_name, {})
        if not active_data:
            tab = self._get_tab_config(self.active_tab.get())
            self._render_empty_entity_state(tab)
            return

        self.editor_frame = ctk.CTkScrollableFrame(self.editor_master, fg_color="transparent")
        self.editor_frame.pack(fill="both", expand=True)

        # --- 2. DIRTY STATE TRACKER ---
        footer = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        center_frame = ctk.CTkFrame(footer, fg_color="transparent")
        btn_save_lore = ctk.CTkButton(center_frame, text="💾 Save Entity Lore", font=("Arial", 14, "bold"), height=36)
        
        def mark_dirty(*args):
            btn_save_lore.configure(state="normal", fg_color="#2E7D32", text="💾 Save Entity Lore")

        def mark_clean():
            btn_save_lore.configure(state="disabled", fg_color="#4A4A4A", text="💾 Saved")

        # --- 3. HEADER (TITLE, STATE, LAST SEEN) ---
        hdr = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(0, 5))
        
        ctk.CTkLabel(hdr, text=f"The Lore Bible: {icon}", font=("Arial", 18, "bold")).pack(side="left")
        
        var_entity_name = ctk.StringVar(value=entity_name)
        var_entity_name.trace_add("write", mark_dirty)
        
        entry_name = ctk.CTkEntry(hdr, textvariable=var_entity_name, font=("Arial", 18, "bold"), width=250, fg_color="transparent", border_width=1)
        entry_name.pack(side="left", padx=10)

        # State/Last Seen Extraction
        if scope == "global" and self.engine.is_universe_thread:
            state_obj = self.engine.memory.get("global_states", {}).get(entity_name, {})
            current_state = state_obj.get("state", "archived")
            last_seen = state_obj.get("last_seen_turn", "?")
        else:
            current_state = active_data.get("state", "active")
            last_seen = active_data.get("last_seen_turn", "?")

        var_state = ctk.StringVar(value=current_state)
        
        def update_state_color(*args):
            s = var_state.get()
            if s == "pinned": 
                state_menu.configure(fg_color="#FBC02D", text_color="black")
            elif s == "archived": 
                state_menu.configure(fg_color="#4A4A4A", text_color="white")
            else: 
                state_menu.configure(fg_color="#1F6AA5", text_color="white")
            mark_dirty()
            
        state_menu = ctk.CTkOptionMenu(hdr, variable=var_state, values=["active", "pinned", "archived"], width=100, command=update_state_color)
        state_menu.pack(side="left", padx=10)
        update_state_color()
        Tooltip(state_menu, "Active: Included in AI prompt.\nPinned: Guaranteed included in AI prompt.\nArchived: Hidden from AI to save tokens.")
        
        btn_seen = ctk.CTkButton(
            hdr, text=f"🔍 Last Seen: Turn {last_seen}", font=("Arial", 12, "bold", "underline"),
            fg_color="transparent", text_color="#00BCD4", hover_color="#333333", height=24, width=80,
            command=lambda: self._show_last_seen_context(entity_name, ledger_type, last_seen)
        )
        btn_seen.pack(side="left", padx=10)

        # --- 4. THE MERGE TOOL ---
        def prompt_merge():
            targets = []
            for s_key in ["global", "local"]:
                for name in self.engine.memory[ledger_type].get(s_key, {}).keys():
                    if s_key == scope and name == entity_name: 
                        continue
                    targets.append({"name": name, "scope": s_key, "display": f"{name} [{s_key.capitalize()}]"})
            
            if not targets: 
                messagebox.showinfo("Merge", "No other entities found to merge with.")
                return
                
            dialog = ctk.CTkToplevel(self)
            dialog.title(f"Merge '{entity_name}'")
            dialog.geometry("500x280")
            dialog.attributes("-topmost", True)
            dialog.grab_set()
            
            from ui.tooltip import center_window_on_parent
            center_window_on_parent(dialog, self.winfo_toplevel())
            
            ctk.CTkLabel(dialog, text=f"Merge {scope.capitalize()} '{entity_name}' INTO:", font=("Arial", 14, "bold")).pack(pady=(20, 10))
            
            display_options = [t["display"] for t in sorted(targets, key=lambda x: x["name"].lower())]
            target_var = ctk.StringVar(value=display_options[0])
            ctk.CTkOptionMenu(dialog, variable=target_var, values=display_options, width=350).pack(pady=10)
            
            def apply_merge():
                selected_display = target_var.get()
                target_meta = next(t for t in targets if t["display"] == selected_display)
                
                master_name = target_meta["name"]
                master_scope = target_meta["scope"]
                
                master = self.engine.memory[ledger_type][master_scope][master_name]
                current = self.engine.memory[ledger_type][scope][entity_name]
                
                self.engine._smart_merge_traits(master["characteristics"], current.get("characteristics", {}))
                master["ledger"].extend(current.get("ledger", []))
                
                m_notes = master.get("author_notes", "").strip()
                s_notes = current.get("author_notes", "").strip()
                if s_notes and s_notes not in m_notes:
                    master["author_notes"] = f"{m_notes}\n\n{s_notes}".strip()
                
                all_aliases = self.engine.memory.setdefault("aliases", {}).setdefault(master_scope, {}).setdefault(ledger_type, {})
                all_aliases[entity_name] = master_name
                
                del self.engine.memory[ledger_type][scope][entity_name]
                
                self.engine._resync_all_visibility()
                self.engine.save_state()
                dialog.destroy()
                
                prefix = "CHAR_" if ledger_type == "character_ledger" else ("LOC_" if ledger_type == "location_ledger" else ("FAC_" if ledger_type == "faction_ledger" else "ART_"))
                self.active_selection.set(f"{prefix}_{master_scope}_{master_name}")
                self._refresh_all()
                
            ctk.CTkButton(dialog, text="Confirm Merge", font=("Arial", 14, "bold"), fg_color="#7B1FA2", hover_color="#4A148C", command=apply_merge).pack(pady=20)
            
        btn_merge = ctk.CTkButton(hdr, text="🔗 Merge...", font=("Arial", 12, "bold"), fg_color="#7B1FA2", hover_color="#4A148C", height=24, width=80, command=prompt_merge)
        btn_merge.pack(side="right")

        # --- 5. SCOPE & ALIASING ---
        var_scope = ctk.StringVar(value=scope)
        if self.engine.is_universe_thread:
            scope_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
            scope_frame.pack(fill="x", padx=10, pady=(5, 10))
            
            ctk.CTkLabel(scope_frame, text="Memory Scope:", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
            
            rb_loc = ctk.CTkRadioButton(scope_frame, text="Local (This story only)", variable=var_scope, value="local", command=mark_dirty)
            rb_loc.pack(side="left", padx=10)
            
            rb_glo = ctk.CTkRadioButton(scope_frame, text="Global (Shared Universe)", variable=var_scope, value="global", command=mark_dirty)
            rb_glo.pack(side="left", padx=10)

        alias_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        alias_frame.pack(fill="x", padx=10, pady=(5, 20))
        
        ctk.CTkLabel(alias_frame, text="Aliases (Comma separated):", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
        
        all_aliases = self.engine.memory.setdefault("aliases", {}).setdefault(scope, {}).setdefault(ledger_type, {})
        current_aliases = [k for k, v in all_aliases.items() if v == entity_name]
        
        var_aliases = ctk.StringVar(value=", ".join(current_aliases))
        var_aliases.trace_add("write", mark_dirty)
        
        entry_alias = ctk.CTkEntry(alias_frame, textvariable=var_aliases, font=("Arial", 12), fg_color="transparent", width=400)
        entry_alias.pack(side="left", padx=10)

        # --- 6. AUTHOR'S NOTES ---
        notes_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        notes_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        ctk.CTkLabel(notes_frame, text="Author's Notes (Indestructible):", font=("Arial", 14, "bold"), text_color="#4CAF50").pack(anchor="w")
        
        var_notes = ctk.CTkTextbox(notes_frame, height=80, wrap="word", font=("Arial", 14))
        var_notes.insert("1.0", active_data.get("author_notes", ""))
        var_notes.bind("<KeyRelease>", mark_dirty)
        var_notes.pack(fill="x", pady=(5, 0))

        # --- 7. CHARACTERISTICS DICTIONARY ---
        ctk.CTkLabel(self.editor_frame, text="Static Characteristics (Traits, Appearance, Quirks)", font=("Arial", 14, "bold"), text_color="#00ACC1").pack(anchor="w", padx=10, pady=(10, 5))
        
        dict_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        dict_container.pack(fill="x", padx=10)
        
        trait_vars = []
        
        def delete_trait(row_widget, tuple_ref):
            row_widget.destroy()
            if tuple_ref in trait_vars: 
                trait_vars.remove(tuple_ref)
            mark_dirty()
            
        def add_trait_row(k_val, v_val):
            row = ctk.CTkFrame(dict_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            vk = ctk.StringVar(value=str(k_val))
            vv = ctk.StringVar(value=str(v_val))
            
            vk.trace_add("write", mark_dirty)
            vv.trace_add("write", mark_dirty)
            
            ctk.CTkEntry(row, textvariable=vk, width=150, font=("Arial", 14, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=vv, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            
            tup = (vk, vv)
            trait_vars.append(tup)
            
            btn_x = ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda r=row, t=tup: delete_trait(r, t))
            btn_x.pack(side="left", padx=(5, 0))
            
        for k, v in sorted(active_data.get("characteristics", {}).items()): 
            add_trait_row(k, v)
            
        btn_add_trait = ctk.CTkButton(self.editor_frame, text="+ Add Trait", fg_color="#4A4A4A", command=lambda: [add_trait_row("New_Trait", "Value"), mark_dirty()])
        btn_add_trait.pack(pady=(5, 20))

        # --- 8. EVENT LEDGER ---
        ctk.CTkLabel(self.editor_frame, text="Chronological Event Ledger", font=("Arial", 14, "bold"), text_color="#FFCA28").pack(anchor="w", padx=10, pady=(10, 5))
        
        list_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        list_container.pack(fill="x", padx=10)
        
        bullet_vars = []
        
        def delete_bullet(row_widget, var_ref):
            row_widget.destroy()
            if var_ref in bullet_vars: 
                bullet_vars.remove(var_ref)
            mark_dirty()

        def add_bullet_row(val):
            row = ctk.CTkFrame(list_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            v = ctk.StringVar(value=str(val))
            v.trace_add("write", mark_dirty)
            
            ctk.CTkLabel(row, text="•", font=("Arial", 16, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=v, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            
            bullet_vars.append(v)
            
            btn_x = ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda r=row, bv=v: delete_bullet(r, bv))
            btn_x.pack(side="left", padx=(5, 0))
            
        for b_text in active_data.get("ledger", []): 
            add_bullet_row(b_text)
            
        btn_add_event = ctk.CTkButton(self.editor_frame, text="+ Add Event", fg_color="#4A4A4A", command=lambda: [add_bullet_row("New event..."), mark_dirty()])
        btn_add_event.pack(pady=(5, 15))

        # --- 9. SAVE & COLLISION HANDLERS ---
        def save_entity():
            new_name = var_entity_name.get().strip()
            new_scope = var_scope.get()
            
            is_rename = (new_name != entity_name)
            is_promotion = (scope != new_scope)

            # --- A. COLLISION CHECK ---
            if (is_rename or is_promotion) and new_name in self.engine.memory[ledger_type].get(new_scope, {}):
                dialog = ctk.CTkToplevel(self)
                dialog.title("Collision Detected")
                dialog.geometry("400x280")
                dialog.attributes("-topmost", True)
                dialog.grab_set()
                
                from ui.tooltip import center_window_on_parent
                center_window_on_parent(dialog, self.winfo_toplevel())
                
                ctk.CTkLabel(dialog, text=f"'{new_name}' already exists in {new_scope.capitalize()} Memory.", font=("Arial", 14, "bold"), text_color="#F57C00").pack(pady=20)
                
                def on_collision_merge():
                    target = self.engine.memory[ledger_type][new_scope][new_name]
                    current = self.engine.memory[ledger_type][scope][entity_name]
                    
                    self.engine._smart_merge_traits(target["characteristics"], current.get("characteristics", {}))
                    target["ledger"].extend(current.get("ledger", []))
                    
                    del self.engine.memory[ledger_type][scope][entity_name]
                    dialog.destroy()
                    prompt_deep_rename(merged=True)
                    
                def on_collision_override(): 
                    var_scope.set("local")
                    dialog.destroy()
                    prompt_deep_rename(merged=False)
                    
                def on_collision_overwrite(): 
                    del self.engine.memory[ledger_type][new_scope][new_name]
                    dialog.destroy()
                    prompt_deep_rename(merged=False)
                
                ctk.CTkButton(dialog, text="Merge into Existing", fg_color="#2E7D32", hover_color="#1B5E20", command=on_collision_merge).pack(pady=5)
                
                if is_promotion: 
                    ctk.CTkButton(dialog, text="Keep Both (Local Override)", fg_color="#1F6AA5", hover_color="#144870", command=on_collision_override).pack(pady=5)
                    
                ctk.CTkButton(dialog, text="Overwrite Existing", fg_color="#B71C1C", hover_color="#7F0000", command=on_collision_overwrite).pack(pady=5)
                ctk.CTkButton(dialog, text="Cancel", fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(pady=5)
                return

            # --- B. DEEP RENAME LOGIC ---
            def prompt_deep_rename(merged=False):
                if is_rename:
                    warn_msg = f"Run Deep Search & Replace for '{entity_name}' -> '{new_name}' in Story Prose?"
                    if messagebox.askyesno("Deep Rename", warn_msg):
                        self.winfo_toplevel().configure(cursor="watch")
                        
                        def worker():
                            affected = self.engine.analyze_deep_rename(entity_name, new_scope)
                            self.after(0, lambda: [self.winfo_toplevel().configure(cursor=""), show_review_ui(affected, merged)])
                            
                        import threading
                        threading.Thread(target=worker, daemon=True).start()
                        return
                        
                finalize_save(new_name, new_scope, merged)

            def show_review_ui(affected, merged):
                if not affected["ram"] and not affected["files"]: 
                    finalize_save(new_name, new_scope, merged)
                    return
                    
                rv = ctk.CTkToplevel(self)
                rv.title("Review Changes")
                rv.geometry("600x450")
                rv.attributes("-topmost", True)
                rv.grab_set()
                
                from ui.tooltip import center_window_on_parent
                center_window_on_parent(rv, self.winfo_toplevel())
                
                ctk.CTkLabel(rv, text=f"Replace '{entity_name}' -> '{new_name}'", font=("Arial", 18, "bold"), text_color="#FF9800").pack(pady=15)
                
                sc = ctk.CTkScrollableFrame(rv, fg_color="#2B2B2B")
                sc.pack(fill="both", expand=True, padx=20, pady=5)
                
                r_v = None
                if affected["ram"]: 
                    r_v = ctk.BooleanVar(value=True)
                    ctk.CTkCheckBox(sc, text="Current Story", variable=r_v).pack(anchor="w", padx=10, pady=5)
                    
                f_vs = {}
                for f_p in affected["files"]:
                    v = ctk.BooleanVar(value=True)
                    f_vs[f_p] = v
                    ctk.CTkCheckBox(sc, text=f"📁 {f_p}", variable=v).pack(anchor="w", padx=10, pady=5)
                    
                def on_exec():
                    self.winfo_toplevel().configure(cursor="watch")
                    rv.destroy()
                    
                    def bg(): 
                        auth_ram = r_v.get() if r_v else False
                        auth_files = [f for f, v in f_vs.items() if v.get()]
                        self.engine.execute_deep_rename(entity_name, new_name, new_scope, auth_ram, auth_files)
                        self.after(0, lambda: [self.winfo_toplevel().configure(cursor=""), finalize_save(new_name, new_scope, merged)])
                        
                    import threading
                    threading.Thread(target=bg, daemon=True).start()
                    
                f_r = ctk.CTkFrame(rv, fg_color="transparent")
                f_r.pack(fill="x", padx=20, pady=15)
                
                ctk.CTkButton(f_r, text="Skip Story Patch", fg_color="#4A4A4A", hover_color="#333333", command=lambda: [rv.destroy(), finalize_save(new_name, new_scope, merged)]).pack(side="left")
                ctk.CTkButton(f_r, text="Execute Rename", fg_color="#E65100", hover_color="#BF360C", command=on_exec).pack(side="right")

            # Demotion check
            if scope == "global" and new_scope == "local":
                if not messagebox.askyesno("Demote", "Proceed with isolation?"): 
                    return
                    
            prompt_deep_rename(merged=False)

        def finalize_save(new_name, final_scope, merged=False):
            # Intelligent Refresh: Only rebuild UI if identity or scope changed
            is_structural = (new_name != entity_name) or (final_scope != scope) or merged
            
            if not merged:
                obj = self.engine.memory[ledger_type][scope].pop(entity_name)
                self.engine.memory[ledger_type][final_scope][new_name] = obj
                
                obj["characteristics"] = {vk.get().strip(): vv.get().strip() for vk, vv in trait_vars if vk.get().strip()}
                obj["ledger"] = [v.get().strip() for v in bullet_vars if v.get().strip()]
                obj["author_notes"] = var_notes.get("1.0", "end").strip()
                
                if final_scope == "global" and self.engine.is_universe_thread: 
                    self.engine.memory.setdefault("global_states", {}).setdefault(new_name, {})["state"] = var_state.get()
                else: 
                    obj["state"] = var_state.get()
            else:
                t_o = self.engine.memory[ledger_type][final_scope][new_name]
                
                new_traits = {vk.get().strip(): vv.get().strip() for vk, vv in trait_vars if vk.get().strip()}
                self.engine._smart_merge_traits(t_o["characteristics"], new_traits)
                t_o["ledger"].extend([v.get().strip() for v in bullet_vars if v.get().strip()])
                
                ui_notes = var_notes.get("1.0", "end").strip()
                ex_notes = t_o.get("author_notes", "").strip()
                if ui_notes and ui_notes not in ex_notes:
                    t_o["author_notes"] = f"{ex_notes}\n\n{ui_notes}".strip()
                    
                if final_scope == "global" and self.engine.is_universe_thread: 
                    self.engine.memory.setdefault("global_states", {}).setdefault(new_name, {})["state"] = var_state.get()
                else: 
                    t_o["state"] = var_state.get()

            # Handle Aliases
            all_a = self.engine.memory.setdefault("aliases", {}).setdefault(final_scope, {}).setdefault(ledger_type, {})
            for k in list(all_a.keys()):
                if all_a[k] == entity_name: del all_a[k]
                
            for a in var_aliases.get().split(","):
                cl_a = a.strip()
                if cl_a: all_a[cl_a] = new_name

            self.engine._resync_all_visibility()
            self.engine.save_state()
            
            if is_structural:
                prefix = "CHAR_" if ledger_type == "character_ledger" else ("LOC_" if ledger_type == "location_ledger" else ("FAC_" if ledger_type == "faction_ledger" else "ART_"))
                self.active_selection.set(f"{prefix}_{final_scope}_{new_name}")
                self._refresh_all()
            else: 
                mark_clean()

        # --- 10. FOOTER BUTTONS ---
        footer.pack(fill="x", pady=20)
        center_frame.pack(expand=True)

        def trigger_deep_scan():
            btn_scan.configure(state="disabled", text="Scanning...")
            self.winfo_toplevel().configure(cursor="watch")
            
            def on_p(c, t, st, et): 
                self.after(0, lambda: btn_scan.configure(text=f"Turns {st}-{et}..."))
                
            def worker():
                succ, msg = self.engine.perform_surgical_deep_scan(entity_name, ledger_type, scope, progress_callback=on_p)
                def up():
                    self.winfo_toplevel().configure(cursor="")
                    btn_scan.configure(state="normal", text="✨ Deep-Scan History")
                    if succ: 
                        messagebox.showinfo("Deep Scan", msg)
                        self._render_view()
                self.after(0, up)
                
            import threading
            threading.Thread(target=worker, daemon=True).start()
            
        btn_scan = ctk.CTkButton(center_frame, text="✨ Deep-Scan History", font=("Arial", 14, "bold"), fg_color="#00ACC1", hover_color="#00838F", height=36, command=trigger_deep_scan)
        btn_scan.pack(side="left", padx=10)
        
        btn_save_lore.configure(command=save_entity)
        btn_save_lore.pack(side="left", padx=10)
        
        mark_clean()
        
        
    # ---------------------------------------------------------
    # LAST SEEN CONTEXT VIEWER (HIGHLIGHTER)
    # ---------------------------------------------------------

    def _show_last_seen_context(self, entity_name, ledger_type, turn_num):
        if turn_num == "?" or turn_num == 0:
            messagebox.showinfo("Context", "This entity was seeded at the start of the game and hasn't been seen in the timeline yet.")
            return
            
        # 1. Find the raw turn data
        turn_data = None
        for t in self.engine.history:
            if str(t.get("turn", -1)) == str(turn_num):
                turn_data = t
                break
                
        if not turn_data:
            messagebox.showerror("Error", f"Turn {turn_num} could not be found in the history ledger.")
            return

        # 2. Setup the Viewer Dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Context: {entity_name} (Turn {turn_num})")
        dialog.geometry("750x550")
        dialog.attributes("-topmost", True)
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text=f"🔍 Highlighted Mentions (Turn {turn_num})", font=("Arial", 16, "bold"), text_color="#00ACC1").pack(pady=(20, 10))

        # 3. Assemble the full scanned text (Location + Bridge + Story)
        loc = turn_data.get("location", "Unknown")
        pov = turn_data.get("pov_character", "Unknown")
        bridge = turn_data.get("narrative_bridge", "")
        story = turn_data.get("story_text", "").replace("\\n", "\n")
        
        full_text = f"[ Location: {loc} ]\n[ POV: {pov} ]\n\n"
        if bridge and bridge not in ["[OK]", "[FAILED]"]:
            full_text += f"{bridge}\n\n"
        full_text += story

        # 4. Textbox Injection
        box = ctk.CTkTextbox(dialog, wrap="word", font=("Georgia", 15))
        box.pack(fill="both", expand=True, padx=20, pady=10)
        box.insert("1.0", full_text)

        # 5. Extract Master Name + All Aliases for searching
        aliases_map = self.engine.memory.get("aliases", {}).get(ledger_type, {})
        search_terms = [entity_name.lower()]
        for alias, master in aliases_map.items():
            if master == entity_name:
                search_terms.append(alias.lower())

        # 6. Apply Highlighting via Native Python Search (Bypasses Tkinter's regex bugs)
        # Bright yellow background with black text for extreme contrast
        box._textbox.tag_config("highlight", background="#FFEB3B", foreground="black", font=("Georgia", 15, "bold"))

        import re
        for term in search_terms:
            # Use Python's robust regex engine to find the exact character offsets
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for match in pattern.finditer(full_text):
                # Convert Python's character index into Tkinter's '1.0 + X chars' format
                start_idx = f"1.0 + {match.start()}c"
                end_idx = f"1.0 + {match.end()}c"
                box._textbox.tag_add("highlight", start_idx, end_idx)

        # 7. Auto-Scroll to the first found match
        try:
            box._textbox.see("highlight.first")
        except Exception:
            pass # Failsafe if the scanner tracked it but it wasn't visually found

        box.configure(state="disabled")

        ctk.CTkButton(dialog, text="Close Viewer", command=dialog.destroy, fg_color="#4A4A4A", hover_color="#333333").pack(pady=(10, 20))
        
        
    def _save_active_memory(self):
        """Routes the global Save button to the correct ledger logic based on selection."""
        selection = self.active_selection.get()
        if selection == "PLOT_LEDGER":
            self._save_plot_ledger()
        elif selection == "CHAPTER_LEDGER":
            self._save_chapter_ledger()
        else:
            # If an entity is selected, remind the user the save button is on the detail form
            messagebox.showinfo("Save Info", "Individual Character and Location changes are saved using the 'Save Entity Lore' button at the bottom of the editor.")

    def _save_plot_ledger(self):
        """Internal logic to extract text from Plot boxes and commit to engine."""
        if not hasattr(self, 'plot_ui_references') or not self.plot_ui_references: return
        for chunk, box in self.plot_ui_references:
            chunk["summary"] = box.get("1.0", "end").strip()
        self.engine.save_state()
        #messagebox.showinfo("Saved", "Plot Ledger updated successfully.")
        self._render_view()

    def _save_chapter_ledger(self):
        """Internal logic to extract text from Chapter boxes and commit to engine."""
        if not hasattr(self, 'chap_ui_references') or not self.chap_ui_references: return
        for chunk, box, tags_var in self.chap_ui_references:
            chunk["summary"] = box.get("1.0", "end").strip()
            chunk["tags"] = [t.strip() for t in tags_var.get().split(",") if t.strip()]
        self.engine.save_state()
        #messagebox.showinfo("Saved", "Chapter Summaries updated successfully.")
        self._render_view()