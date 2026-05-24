"""
    TomeWeaver: Memory & Lore UI
    ----------------------------
    Provides a RAG (Retrieval-Augmented Generation) viewer for long-term memory.
    Displays the AI-generated Plot Summaries and the evolving Character/Location states.
"""
import json
import customtkinter as ctk
from tkinter import messagebox
from ui.tooltip import Tooltip

class MemoryTab(ctk.CTkFrame):
    """
    Memory & Lore UI (RAG Viewer)
    """
    def __init__(self, parent, engine):
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        self._last_render_time = 0 # Tracks when this tab was last drawn
        
        # --- HEADER ---
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=5)
        
        # STICKY SAVE BUTTON: Positioned on the far left for instant access
        self.btn_save_memory = ctk.CTkButton(hdr, text="💾 Save Changes", font=("Arial", 12, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", width=120, command=self._save_active_memory)
        self.btn_save_memory.pack(side="left", padx=(10, 5))
        Tooltip(self.btn_save_memory, "Commit manual edits to Plot or Chapter summaries.")

        ctk.CTkLabel(hdr, text="Long-Term Memory Ledger", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(side="left", padx=5, pady=10)
        
        self.btn_compile = ctk.CTkButton(hdr, text="🔄 Compile Missing History", font=("Arial", 12, "bold"), fg_color="#F57C00", hover_color="#E65100", command=self._compile_history)
        self.btn_compile.pack(side="right", padx=10)
        Tooltip(self.btn_compile, "Scans your past turns and generates memory for any missing chunks.")
        
        self.btn_clear = ctk.CTkButton(hdr, text="🧨 Clear...", font=("Arial", 12, "bold"), fg_color="#D32F2F", hover_color="#9A0007", command=self._show_clear_dialog)
        self.btn_clear.pack(side="right", padx=(10, 0))
        
        # --- RESIZABLE SPLIT PANE LAYOUT ---
        import tkinter as tk
        # Use native PanedWindow to allow dragging the sash. Colors matched to dark mode.
        self.paned_window = tk.PanedWindow(self, orient="horizontal", bg="#212121", bd=0, sashwidth=6, sashcursor="sb_h_double_arrow")
        self.paned_window.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 1. Create two basic CTkFrames to act as safe buckets for the PanedWindow
        left_bucket = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        right_bucket = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        
        self.paned_window.add(left_bucket, minsize=200)
        self.paned_window.add(right_bucket, minsize=400)
        
        # 2. Pack the complex CustomTkinter scrollable frames safely inside the buckets
        self.nav_frame = ctk.CTkScrollableFrame(left_bucket, width=280)
        self.nav_frame.pack(fill="both", expand=True)
        
        self.editor_frame = ctk.CTkScrollableFrame(right_bucket, fg_color="transparent")
        self.editor_frame.pack(fill="both", expand=True)
        
        self.active_selection = ctk.StringVar(value="PLOT_LEDGER")
        self._refresh_nav()

    def _compile_history(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Retroactive Compiler")
        dialog.geometry("500x480") # Made slightly taller for the 4th option
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
        # Divider
        ctk.CTkFrame(dialog, height=2, fg_color="#333333").pack(fill="x", padx=40, pady=15)

        # Load the last used reconcile setting (defaults to True on first run)
        v_recon = ctk.BooleanVar(value=self.engine.setup_data.get("auto_reconcile", True))
        cb_recon = ctk.CTkCheckBox(dialog, text="Auto-Reconcile Duplicates (Merge aliases)", variable=v_recon)
        cb_recon.pack(anchor="w", padx=40)
        Tooltip(cb_recon, "Runs a final AI pass to automatically merge duplicate entities like 'John' and 'John Smith'.")

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
                        from tkinter import messagebox
                        messagebox.showinfo("Complete", msg)
                        
                    self._refresh_nav()
                    self._render_view()
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
        """Spawns a granular memory-wipe dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Clear Memory")
        dialog.geometry("420x350")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Wipe Long-Term Memory", font=("Arial", 16, "bold"), text_color="#D32F2F").pack(pady=(20, 10))
        ctk.CTkLabel(dialog, text="Select what you want to delete. You can safely regenerate wiped data using the Compiler.", wraplength=350, text_color="gray").pack(padx=20, pady=(0, 20))

        v_plot = ctk.BooleanVar(value=True)
        v_bullets = ctk.BooleanVar(value=True)
        v_entities = ctk.BooleanVar(value=False)

        ctk.CTkSwitch(dialog, text="Clear Plot Summaries", variable=v_plot).pack(anchor="w", padx=40, pady=10)
        ctk.CTkSwitch(dialog, text="Clear Entity Histories (Keep tracked names)", variable=v_bullets).pack(anchor="w", padx=40, pady=10)
        ctk.CTkSwitch(dialog, text="Untrack Entities (Delete names entirely)", variable=v_entities).pack(anchor="w", padx=40, pady=10)

        def apply_clear():
            if v_plot.get():
                self.engine.memory["plot_ledger"] = []
                self.engine.memory["chapter_ledger"] = [] # Also wipe high-level chapter summaries
            if v_bullets.get():
                # Preserve the Author's Notes while wiping the AI's data
                for l_type in ["character_ledger", "location_ledger", "artifact_ledger"]:
                    for k in self.engine.memory.get(l_type, {}): 
                        saved_notes = self.engine.memory[l_type][k].get("author_notes", "")
                        self.engine.memory[l_type][k] = {"characteristics": {}, "ledger": [], "author_notes": saved_notes}
            if v_entities.get():
                self.engine.memory["character_ledger"] = {}
                self.engine.memory["location_ledger"] = {}
                self.engine.memory["artifact_ledger"] = {}
                self.engine.memory["faction_ledger"] = {}
                # Completely wipe all active aliases if we are doing a nuclear wipe
                self.engine.memory["aliases"] = {"character_ledger": {}, "location_ledger": {}, "artifact_ledger": {}, "faction_ledger": {}}
                
            self.engine.save_state()
            self.active_selection.set("PLOT_LEDGER")
            self._refresh_nav()
            dialog.destroy()
            messagebox.showinfo("Memory Cleared", "Selected memory banks have been wiped.")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Wipe Selected", width=120, fg_color="#B71C1C", hover_color="#7F0000", command=apply_clear).pack(side="right", padx=10)

    def _refresh_nav(self):
        for w in self.nav_frame.winfo_children(): w.destroy()
        
        def get_state_icon(data_obj, entity_name, scope):
            if not isinstance(data_obj, dict): return ""
            
            if scope == "global" and self.engine.is_universe_thread:
                s = self.engine.memory.get("global_states", {}).get(entity_name, {}).get("state", "archived")
            else:
                s = data_obj.get("state", "active")
                
            if s == "pinned": return "📌 "
            if s == "archived": return "📦 "
            return ""
            
        # 1. Plot & Chapter Summaries
        row_c = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        row_c.pack(fill="x", pady=(0, 5))
        ctk.CTkRadioButton(row_c, text="📚 Chapter Summaries", font=("Arial", 14, "bold"), variable=self.active_selection, value="CHAPTER_LEDGER", command=self._render_view).pack(side="left")
        
        row_p = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        row_p.pack(fill="x", pady=(0, 15))
        ctk.CTkRadioButton(row_p, text="📖 Plot Ledger (Parts)", font=("Arial", 14, "bold"), variable=self.active_selection, value="PLOT_LEDGER", command=self._render_view).pack(side="left")
        
        def render_ledger_nav(title, ledger_type, prefix, emoji):
            ctk.CTkLabel(self.nav_frame, text=title, font=("Arial", 12, "bold"), text_color="gray").pack(anchor="w", pady=(5, 2))
            
            entities = {}
            for scope in ["global", "local"]:
                for name, data in self.engine.memory.get(ledger_type, {}).get(scope, {}).items():
                    if isinstance(data, list): continue
                    entities.setdefault(name, []).append((scope, data))
                    
            mode_color = "#2196F3" if self.engine.setup_data.get("mode", "sandbox") == "sandbox" else "#9C27B0"
            is_univ = self.engine.is_universe_thread
                    
            for name in sorted(entities.keys()):
                for scope, data in entities[name]:
                    r = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
                    r.pack(fill="x", pady=2)
                    
                    s_icon = get_state_icon(data, name, scope)
                    
                    # Context-Aware Coloring: Only use colors if we are actually in a Universe!
                    if is_univ:
                        e_color = "#FF9800" if scope == "global" else mode_color
                    else:
                        e_color = "white" # Standard theme color for standalone
                        
                    display_text = f"{emoji} {s_icon}{name}"
                    
                    rb = ctk.CTkRadioButton(r, text=display_text, text_color=e_color, variable=self.active_selection, value=f"{prefix}_{scope}_{name}", command=self._render_view)
                    rb.pack(side="left")
                    
                    ctk.CTkButton(r, text="X", width=20, fg_color="#B71C1C", hover_color="#7F0000", command=lambda n=name, s=scope, lt=ledger_type: self._delete_entity(n, s, lt)).pack(side="right")
            
            ctk.CTkButton(self.nav_frame, text=f"+ Add {title[:-1]}", fg_color="#4A4A4A", hover_color="#333333", command=lambda lt=ledger_type: self._add_entity(lt)).pack(fill="x", pady=(5, 15))

        render_ledger_nav("Characters", "character_ledger", "CHAR", "👤")
        render_ledger_nav("Locations", "location_ledger", "LOC", "📍")
        render_ledger_nav("Artifacts", "artifact_ledger", "ART", "💎")
        if self.engine.setup_data.get("track_factions", False):
            render_ledger_nav("Factions & Orgs", "faction_ledger", "FAC", "🛡️")

        self._render_view()

    def _delete_entity(self, name, scope, ledger_type):
        if messagebox.askyesno("Delete", f"Stop tracking {scope} memory for '{name}'?"):
            if name in self.engine.memory[ledger_type].get(scope, {}):
                del self.engine.memory[ledger_type][scope][name]
                self.engine.save_state()
                self.active_selection.set("PLOT_LEDGER")
                self._refresh_nav()

    def _add_entity(self, ledger_type):
        if ledger_type == "character_ledger": type_str = "Character"
        elif ledger_type == "location_ledger": type_str = "Location"
        elif ledger_type == "faction_ledger": type_str = "Faction / Org"
        else: type_str = "Artifact"
        
        dialog = ctk.CTkInputDialog(text=f"Enter the exact name of a {type_str} to track:", title=f"Add {type_str}")
        name = dialog.get_input()
        if name and name.strip():
            clean_name = name.strip()
            # New entities default to LOCAL
            if clean_name not in self.engine.memory[ledger_type].get("local", {}):
                self.engine.memory[ledger_type].setdefault("local", {})[clean_name] = {"characteristics": {}, "ledger": [], "author_notes": "", "state": "active"}
                self.engine.save_state()
                
                prefix = "CHAR_" if ledger_type == "character_ledger" else ("LOC_" if ledger_type == "location_ledger" else ("FAC_" if ledger_type == "faction_ledger" else "ART_"))
                self.active_selection.set(f"{prefix}_local_{clean_name}")
                self._refresh_nav()

    def _render_view(self):
        import time
        self._last_render_time = time.time()
        
        for w in self.editor_frame.winfo_children(): w.destroy()
        selection = self.active_selection.get()
        
        if selection == "CHAPTER_LEDGER": self._render_chapter_ledger()
        elif selection == "PLOT_LEDGER": self._render_plot_ledger()
        else:
            # Parse the new compound value: e.g., "CHAR_local_Kaelen"
            parts = selection.split("_", 2)
            if len(parts) == 3:
                prefix, scope, entity_name = parts
                if prefix == "CHAR": self._render_entity_editor(entity_name, scope, "character_ledger")
                elif prefix == "LOC": self._render_entity_editor(entity_name, scope, "location_ledger")
                elif prefix == "ART": self._render_entity_editor(entity_name, scope, "artifact_ledger")
                elif prefix == "FAC": self._render_entity_editor(entity_name, scope, "faction_ledger")
                
                
    # ---------------------------------------------------------
    # PLOT LEDGER VIEW
    # ---------------------------------------------------------
    def _render_plot_ledger(self):
        ctk.CTkLabel(self.editor_frame, text="The Plot Ledger (Chronological Summaries)", font=("Arial", 18, "bold")).pack(anchor="w", padx=10, pady=(0, 5))
        ctk.CTkLabel(self.editor_frame, text="The AI automatically compresses long chapters into chunks so it never forgets the past.", text_color="gray").pack(anchor="w", padx=10, pady=(0, 20))
        
        plot_list = self.engine.memory.get("plot_ledger", [])
        if not plot_list:
            ctk.CTkLabel(self.editor_frame, text="The story hasn't reached the auto-summarize threshold yet.", font=("Arial", 14, "italic")).pack(pady=50)
            return

        self.plot_ui_references = [] # Store widget references safely outside the Engine data

        for idx, chunk in enumerate(plot_list):
            card = ctk.CTkFrame(self.editor_frame, fg_color="#2B2B2B", corner_radius=8)
            card.pack(fill="x", padx=10, pady=10)
            
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=15, pady=10)
            
            c_num = chunk.get("chapter_number", "?")
            title = chunk.get("chapter_title", "Unknown Chapter")
            t_start = chunk.get("start_turn", "?")
            t_end = chunk.get("end_turn", "?")
            
            ctk.CTkLabel(hdr, text=f"Chapter {c_num}: {title} | Turns {t_start} - {t_end}", font=("Arial", 14, "bold"), text_color="#FFCA28").pack(side="left")
            
            # --- Individual Delete Button ---
            def delete_chunk(c=chunk):
                if messagebox.askyesno("Delete Summary", f"Delete summary for Turns {c.get('start_turn')} - {c.get('end_turn')}?\n\nThe compiler will automatically regenerate it next time you run it."):
                    self.engine.memory["plot_ledger"].remove(c)
                    self.engine.save_state()
                    self._render_view()
                    
            btn_del = ctk.CTkButton(hdr, text="🗑️ Delete", width=60, height=24, fg_color="#B71C1C", hover_color="#7F0000", command=delete_chunk)
            btn_del.pack(side="right", padx=(5, 0))

            # --- Individual Reroll Button ---
            btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
            btn_reroll.pack(side="right", padx=(5, 0))
            Tooltip(btn_reroll, "Ask the AI to regenerate this specific chunk from the raw history.")
            
            # --- Individual Validate Button ---
            btn_val = ctk.CTkButton(hdr, text="✔️ Validate", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            btn_val.pack(side="right")
            Tooltip(btn_val, "Audits the text currently in the box below against the raw game history to check for hallucinations or missing facts.")
            
            box = ctk.CTkTextbox(card, height=120, wrap="word", font=("Arial", 14))
            box.insert("1.0", chunk.get("summary", ""))
            box.pack(fill="x", padx=15, pady=(0, 15))
            
            def validate_chunk(c=chunk, b=box, btn=btn_val):
                orig_text = btn.cget("text")
                btn.configure(state="disabled", text="...")
                self.winfo_toplevel().configure(cursor="watch")
                
                def worker():
                    raw_chunk = [t for t in self.engine.history if c["start_turn"] <= t.get("turn", 0) <= c["end_turn"]]
                    if not raw_chunk:
                        self.after(0, lambda: messagebox.showerror("Error", "Could not find raw turns for this chunk."))
                        self.after(0, lambda: [btn.configure(state="normal", text=orig_text), self.winfo_toplevel().configure(cursor="")])
                        return
                        
                    turns_text = ""
                    for t in raw_chunk:
                        turns_text += f"Turn {t['turn']} [Loc: {t.get('location', '')}]: {t.get('story_text', '')}\nAction: {t.get('player_choice', '')}\n\n"
                        
                    current_summary = b.get("1.0", "end").strip()
                    from api import TomeWeaverAPI
                    succ, res = TomeWeaverAPI.validate_plot_chunk(turns_text, current_summary, self.engine.adv_dir)
                    
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn.configure(state="normal", text=orig_text)
                        if succ:
                            # --- AUTO-PATCH LOGIC ---
                            def trigger_patch(report_dialog):
                                report_dialog.destroy()
                                btn.configure(state="disabled", text="Patching...")
                                self.winfo_toplevel().configure(cursor="watch")
                                
                                def patch_worker():
                                    succ_patch, patched_text = TomeWeaverAPI.patch_plot_chunk(turns_text, current_summary, res, self.engine.adv_dir)
                                    
                                    def post_patch_ui():
                                        if succ_patch:
                                            b.delete("1.0", "end")
                                            b.insert("1.0", patched_text)
                                            
                                            # Restore UI state so the button is allowed to be clicked
                                            btn.configure(state="normal", text=orig_text)
                                            self.winfo_toplevel().configure(cursor="")
                                            
                                            # Programmatically "click" the Validate button.
                                            # This completely bypasses Python's loop memory bug because the 
                                            # button internally remembers the exact chunk it belongs to!
                                            btn.invoke()
                                        else:
                                            btn.configure(state="normal", text=orig_text)
                                            self.winfo_toplevel().configure(cursor="")
                                            messagebox.showerror("Patch Error", patched_text)
                                            
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
            
            def reroll_chunk(c=chunk, b=box, btn=btn_reroll):
                orig_text = btn.cget("text")
                btn.configure(state="disabled", text="...")
                self.winfo_toplevel().configure(cursor="watch")
                
                def worker():
                    # 1. Fetch exact turns mathematically
                    raw_chunk = [t for t in self.engine.history if c["start_turn"] <= t.get("turn", 0) <= c["end_turn"]]
                    if not raw_chunk:
                        self.after(0, lambda: messagebox.showerror("Error", "Could not find raw turns for this chunk."))
                        return
                        
                    turns_text = ""
                    for t in raw_chunk:
                        turns_text += f"Turn {t['turn']} [Loc: {t.get('location', '')}]: {t.get('story_text', '')}\nAction: {t.get('player_choice', '')}\n\n"
                        
                    # 2. Ask LLM
                    from api import TomeWeaverAPI
                    succ, res = TomeWeaverAPI.generate_plot_summary(turns_text, c["start_turn"], c["end_turn"], self.engine.adv_dir)
                    
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn.configure(state="normal", text=orig_text)
                        if succ:
                            b.delete("1.0", "end")
                            b.insert("1.0", res)
                        else:
                            messagebox.showerror("Error", res)
                            
                    self.after(0, update_ui)
                    
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            btn_reroll.configure(command=reroll_chunk)
            
            # Save the UI reference in a localized list instead of injecting it into the Engine's data
            self.plot_ui_references.append((chunk, box))

        ctk.CTkLabel(self.editor_frame, text="Use the engine configuration to change the Memory Chunk size.", font=("Arial", 12, "italic"), text_color="#555555").pack(pady=20)


    def _render_chapter_ledger(self):
        ctk.CTkLabel(self.editor_frame, text="Chapter Summaries (High-Level Memory)", font=("Arial", 18, "bold")).pack(anchor="w", padx=10, pady=(0, 5))
        ctk.CTkLabel(self.editor_frame, text="Completed chapters are highly condensed here. This prevents Context Limit crashes in long games.", text_color="gray").pack(anchor="w", padx=10, pady=(0, 20))
        
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
            
            box = ctk.CTkTextbox(card, height=120, wrap="word", font=("Arial", 14))
            box.insert("1.0", chunk.get("summary", ""))
            box.pack(fill="x", padx=15, pady=(0, 5))
            
            tags_frame = ctk.CTkFrame(card, fg_color="transparent")
            tags_frame.pack(fill="x", padx=15, pady=(0, 15))
            ctk.CTkLabel(tags_frame, text="Tags:", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
            
            tags_var = ctk.StringVar(value=", ".join(chunk.get("tags", [])))
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
        if ledger_type == "character_ledger": icon = "👤"
        elif ledger_type == "location_ledger": icon = "📍"
        elif ledger_type == "faction_ledger": icon = "🛡️"
        else: icon = "💎"
        
        # --- DATA EXTRACTION ---
        active_data = self.engine.memory[ledger_type].get(scope, {}).get(entity_name, {})
        if not active_data: return # Failsafe if deleted

        # --- HEADER ---
        hdr = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(0, 5))
        
        ctk.CTkLabel(hdr, text=f"The Lore Bible: {icon}", font=("Arial", 18, "bold")).pack(side="left")
        
        var_entity_name = ctk.StringVar(value=entity_name)
        ctk.CTkEntry(hdr, textvariable=var_entity_name, font=("Arial", 18, "bold"), width=250, fg_color="transparent", border_width=1).pack(side="left", padx=10)

        # STATE TOGGLE
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
            if s == "pinned": state_menu.configure(fg_color="#FBC02D", text_color="black")
            elif s == "archived": state_menu.configure(fg_color="#4A4A4A", text_color="white")
            else: state_menu.configure(fg_color="#1F6AA5", text_color="white")
            
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

        
        # --- SCOPE TOGGLE (PROMOTION/DEMOTION) ---
        var_scope = ctk.StringVar(value=scope)
        is_univ = self.engine.is_universe_thread
        
        # Only draw the Scope Editor if this story is actually inside a Universe
        if is_univ:
            scope_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
            scope_frame.pack(fill="x", padx=10, pady=(5, 10))
            
            ctk.CTkLabel(scope_frame, text="Memory Scope:", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
            
            rb_loc = ctk.CTkRadioButton(scope_frame, text="Local (This story only)", variable=var_scope, value="local")
            rb_loc.pack(side="left", padx=10)
            
            rb_glo = ctk.CTkRadioButton(scope_frame, text="Global (Shared Universe)", variable=var_scope, value="global")
            rb_glo.pack(side="left", padx=10)

        # --- ALIAS EDITOR ---
        alias_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        alias_frame.pack(fill="x", padx=10, pady=(5, 20))
        ctk.CTkLabel(alias_frame, text="Aliases (Comma separated):", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
        
        all_aliases = self.engine.memory.setdefault("aliases", {}).setdefault(scope, {}).setdefault(ledger_type, {})
        current_aliases = [k for k, v in all_aliases.items() if v == entity_name]
        
        var_aliases = ctk.StringVar(value=", ".join(current_aliases))
        ctk.CTkEntry(alias_frame, textvariable=var_aliases, font=("Arial", 12), fg_color="transparent", width=400).pack(side="left", padx=10)

        # --- AUTHOR'S NOTES ---
        notes_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        notes_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        lbl_notes = ctk.CTkLabel(notes_frame, text="Author's Notes (Indestructible):", font=("Arial", 14, "bold"), text_color="#4CAF50")
        lbl_notes.pack(anchor="w")
        var_notes = ctk.CTkTextbox(notes_frame, height=80, wrap="word", font=("Arial", 14))
        var_notes.insert("1.0", active_data.get("author_notes", ""))
        var_notes.pack(fill="x", pady=(5, 0))

        # --- SECTION 1: CHARACTERISTICS DICTIONARY ---
        ctk.CTkLabel(self.editor_frame, text="Static Characteristics (Traits, Appearance, Quirks)", font=("Arial", 14, "bold"), text_color="#00ACC1").pack(anchor="w", padx=10, pady=(10, 5))
        dict_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        dict_container.pack(fill="x", padx=10)
        
        trait_vars = []
        traits = active_data.get("characteristics", {})
        
        def delete_trait(row_widget, tuple_ref):
            row_widget.destroy()
            if tuple_ref in trait_vars: trait_vars.remove(tuple_ref)
            
        for k, v in sorted(traits.items(), key=lambda item: str(item[0]).lower()):
            row = ctk.CTkFrame(dict_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var_k = ctk.StringVar(value=str(k))
            var_v = ctk.StringVar(value=str(v))
            ctk.CTkEntry(row, textvariable=var_k, width=150, font=("Arial", 14, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=var_v, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            tuple_ref = (var_k, var_v)
            trait_vars.append(tuple_ref)
            ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda rw=row, tr=tuple_ref: delete_trait(rw, tr)).pack(side="left", padx=(5, 0))
            
        def add_trait():
            row = ctk.CTkFrame(dict_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var_k = ctk.StringVar(value="New_Trait")
            var_v = ctk.StringVar(value="Value")
            ctk.CTkEntry(row, textvariable=var_k, width=150, font=("Arial", 14, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=var_v, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            tuple_ref = (var_k, var_v)
            trait_vars.append(tuple_ref)
            ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda rw=row, tr=tuple_ref: delete_trait(rw, tr)).pack(side="left", padx=(5, 0))
            
        ctk.CTkButton(self.editor_frame, text="+ Add Trait", fg_color="#4A4A4A", command=add_trait).pack(pady=(5, 20))

        # --- SECTION 2: EVENT LEDGER (Bullets) ---
        ctk.CTkLabel(self.editor_frame, text="Chronological Event Ledger", font=("Arial", 14, "bold"), text_color="#FFCA28").pack(anchor="w", padx=10, pady=(10, 5))
        list_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        list_container.pack(fill="x", padx=10)

        bullet_vars = []
        bullets = active_data.get("ledger", [])

        def delete_bullet(row_widget, var_ref):
            row_widget.destroy()
            if var_ref in bullet_vars: bullet_vars.remove(var_ref)

        for b_text in bullets:
            row = ctk.CTkFrame(list_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = ctk.StringVar(value=str(b_text))
            ctk.CTkLabel(row, text="•", font=("Arial", 16, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=var, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            bullet_vars.append(var)
            ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda rw=row, vr=var: delete_bullet(rw, vr)).pack(side="left", padx=(5, 0))

        def add_bullet():
            row = ctk.CTkFrame(list_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = ctk.StringVar(value="New event...")
            ctk.CTkLabel(row, text="•", font=("Arial", 16, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=var, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            bullet_vars.append(var)
            ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda rw=row, vr=var: delete_bullet(rw, vr)).pack(side="left", padx=(5, 0))

        ctk.CTkButton(self.editor_frame, text="+ Add Event", fg_color="#4A4A4A", command=add_bullet).pack(pady=(5, 15))

        
        # --- SAVE ENTITY BUTTON & SCOPE HANDLER ---
        def save_entity():
            target_name = entity_name
            new_name = var_entity_name.get().strip()
            new_scope = var_scope.get()
            
            is_rename = (new_name != entity_name)
            is_promotion = (scope != new_scope)

            # Abstract the Deep Rename logic so it can be called after any collision resolutions
            def prompt_deep_rename(merged=False):
                if is_rename:
                    warn_msg = f"You renamed '{entity_name}' to '{new_name}'.\n\nWould you like to run a Deep Search & Replace to update all historical mentions of their old name across the actual STORY PROSE (history.json, setup.json, etc.)?"
                    if new_scope == "global" or scope == "global": 
                        warn_msg += "\n\n(WARNING: Because this involves a Global scope, this will scan EVERY story inside this Universe)."
                    
                    self.winfo_toplevel().configure(cursor="watch")
                    
                    def worker():
                        # Analyze using the OLD name to find mentions in the raw story text
                        affected = self.engine.analyze_deep_rename(entity_name, new_scope)
                        
                        def show_review_ui():
                            self.winfo_toplevel().configure(cursor="")
                            
                            if not affected["ram"] and not affected["files"]:
                                finalize_save(new_name, new_scope, merged)
                                return
                                
                            dialog = ctk.CTkToplevel(self)
                            dialog.title("Deep Rename Review (Story Text)")
                            dialog.geometry("600x450")
                            dialog.attributes("-topmost", True)
                            dialog.grab_set()
                            
                            from ui.tooltip import center_window_on_parent
                            center_window_on_parent(dialog, self.winfo_toplevel())
                            
                            ctk.CTkLabel(dialog, text=f"Replace '{entity_name}' -> '{new_name}' in Story", font=("Arial", 18, "bold"), text_color="#FF9800").pack(pady=(20, 10))
                            ctk.CTkLabel(dialog, text="The engine found mentions of this name in the raw story text. Uncheck any files you do NOT want to physically modify.", wraplength=550, text_color="gray").pack(padx=20, pady=(0, 15))
                            
                            scroll = ctk.CTkScrollableFrame(dialog, fg_color="#2B2B2B", corner_radius=6)
                            scroll.pack(fill="both", expand=True, padx=20, pady=5)
                            
                            ram_var = None
                            if affected["ram"]:
                                ram_var = ctk.BooleanVar(value=True)
                                ctk.CTkCheckBox(scroll, text="Current Active Story (RAM & Local Files)", variable=ram_var, font=("Arial", 14, "bold"), text_color="#00BCD4").pack(anchor="w", padx=10, pady=10)
                                
                            file_vars = {}
                            if affected["files"]:
                                ctk.CTkLabel(scroll, text="Other Offline Stories in Universe:", font=("Arial", 12, "bold"), text_color="gray").pack(anchor="w", padx=10, pady=(15, 5))
                                from api import ADV_DIR
                                import os
                                for f_path in affected["files"]:
                                    var = ctk.BooleanVar(value=True)
                                    file_vars[f_path] = var
                                    rel_display = os.path.relpath(f_path, ADV_DIR)
                                    ctk.CTkCheckBox(scroll, text=f"📁 {rel_display}", variable=var, font=("Arial", 13)).pack(anchor="w", padx=20, pady=5)
                                    
                            def execute_rename():
                                auth_ram = ram_var.get() if ram_var else False
                                auth_files = [f for f, var in file_vars.items() if var.get()]
                                
                                self.winfo_toplevel().configure(cursor="watch")
                                dialog.destroy()
                                
                                def bg_exec():
                                    self.engine.execute_deep_rename(entity_name, new_name, new_scope, auth_ram, auth_files)
                                    self.after(0, lambda: [self.winfo_toplevel().configure(cursor=""), finalize_save(new_name, new_scope, merged)])
                                import threading
                                threading.Thread(target=bg_exec, daemon=True).start()
                                
                            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
                            btn_frame.pack(fill="x", padx=20, pady=15)
                            
                            # If they skip, it just finishes saving the RAG changes WITHOUT touching the story text
                            ctk.CTkButton(btn_frame, text="Skip (Keep old name in story)", width=120, fg_color="#4A4A4A", hover_color="#333333", command=lambda: [dialog.destroy(), finalize_save(new_name, new_scope, merged)]).pack(side="left")
                            ctk.CTkButton(btn_frame, text="Execute Rename", width=140, font=("Arial", 14, "bold"), fg_color="#E65100", hover_color="#BF360C", command=execute_rename).pack(side="right")
                            
                        self.after(0, show_review_ui)
                    import threading
                    threading.Thread(target=worker, daemon=True).start()
                else:
                    finalize_save(new_name, new_scope, merged)


            # --- COLLISION HANDLER ---
            if (is_rename or is_promotion) and new_name in self.engine.memory[ledger_type].get(new_scope, {}):
                dialog = ctk.CTkToplevel(self)
                dialog.title("Collision Detected")
                dialog.geometry("400x250")
                dialog.attributes("-topmost", True)
                dialog.grab_set()
                
                from ui.tooltip import center_window_on_parent
                center_window_on_parent(dialog, self.winfo_toplevel())
                
                ctk.CTkLabel(dialog, text=f"'{new_name}' already exists in {new_scope.capitalize()} Memory.", font=("Arial", 14, "bold"), text_color="#F57C00").pack(pady=20)
                
                def do_merge():
                    target = self.engine.memory[ledger_type][new_scope][new_name]
                    current = self.engine.memory[ledger_type][scope][entity_name]
                    
                    self.engine._smart_merge_traits(target["characteristics"], current.get("characteristics", {}))
                    target["ledger"].extend(current.get("ledger", []))
                    
                    del self.engine.memory[ledger_type][scope][entity_name]
                    dialog.destroy()
                    # Trigger the Deep Rename on the story text now that RAG is merged!
                    prompt_deep_rename(merged=True) 
                    
                def keep_both():
                    var_scope.set("local")
                    dialog.destroy()
                    # It's still a rename, so trigger the prompt!
                    prompt_deep_rename(merged=False) 
                    
                def overwrite_target():
                    del self.engine.memory[ledger_type][new_scope][new_name]
                    dialog.destroy()
                    prompt_deep_rename(merged=False)
                    
                ctk.CTkButton(dialog, text="Merge into Existing", fg_color="#2E7D32", hover_color="#1B5E20", command=do_merge).pack(pady=5)
                if is_promotion:
                    ctk.CTkButton(dialog, text="Keep Both (Local Override)", fg_color="#1F6AA5", hover_color="#144870", command=keep_both).pack(pady=5)
                ctk.CTkButton(dialog, text="Overwrite Existing", fg_color="#B71C1C", hover_color="#7F0000", command=overwrite_target).pack(pady=5)
                ctk.CTkButton(dialog, text="Cancel Save", fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(pady=5)
                return
                    
            if scope == "global" and new_scope == "local":
                if not messagebox.askyesno("Demote Entity", f"Moving '{new_name}' to Local means other stories in this Universe will no longer see them.\n\nProceed?"):
                    var_scope.set("global")
                    return
                    
            prompt_deep_rename(merged=False)

        def finalize_save(new_name, final_scope, merged=False):
            if not merged:
                # Standard Move/Update
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
                # If merged, the target object already exists. We just need to apply any newly typed UI data to it!
                target_obj = self.engine.memory[ledger_type][final_scope][new_name]
                new_traits = {vk.get().strip(): vv.get().strip() for vk, vv in trait_vars if vk.get().strip()}
                self.engine._smart_merge_traits(target_obj["characteristics"], new_traits)
                target_obj["ledger"].extend([v.get().strip() for v in bullet_vars if v.get().strip()])
                
                ui_notes = var_notes.get("1.0", "end").strip()
                ex_notes = target_obj.get("author_notes", "").strip()
                if ui_notes and ui_notes not in ex_notes:
                    target_obj["author_notes"] = f"{ex_notes}\n\n{ui_notes}".strip()
                    
                if final_scope == "global" and self.engine.is_universe_thread:
                    self.engine.memory.setdefault("global_states", {}).setdefault(new_name, {})["state"] = var_state.get()
                else:
                    target_obj["state"] = var_state.get()

            # Handle Aliases
            all_aliases = self.engine.memory.setdefault("aliases", {}).setdefault(final_scope, {}).setdefault(ledger_type, {})
            for k in list(all_aliases.keys()):
                if all_aliases[k] == entity_name: del all_aliases[k]
            for a in var_aliases.get().split(","):
                clean_a = a.strip()
                if clean_a: all_aliases[clean_a] = new_name

            self.engine._resync_all_visibility()
            self.engine.save_state()
            
            prefix = "CHAR_" if ledger_type == "character_ledger" else ("LOC_" if ledger_type == "location_ledger" else ("FAC_" if ledger_type == "faction_ledger" else "ART_"))
            self.active_selection.set(f"{prefix}_{final_scope}_{new_name}")
            
            messagebox.showinfo("Saved", f"'{new_name}' updated successfully.")
            self._refresh_nav()
            self._render_view()

        # --- FOOTER BUTTONS ---
        footer = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        footer.pack(fill="x", pady=20)
        
        # Centering container
        center_frame = ctk.CTkFrame(footer, fg_color="transparent")
        center_frame.pack(expand=True)

        # 1. The Surgical Deep Scan Button
        def trigger_deep_scan():
            btn_scan.configure(state="disabled", text="Scanning...")
            self.winfo_toplevel().configure(cursor="watch")
            
            def on_progress(current, total, start_t=None, end_t=None):
                if start_t is not None and end_t is not None:
                    msg = f"Scanning Turns {start_t}-{end_t}..."
                else:
                    msg = f"Scanning Part {current}/{total}..."
                self.after(0, lambda: btn_scan.configure(text=msg))
                
            def worker():
                succ, msg = self.engine.perform_surgical_deep_scan(entity_name, ledger_type, scope, progress_callback=on_progress)
                def update_ui():
                    self.winfo_toplevel().configure(cursor="")
                    btn_scan.configure(state="normal", text="✨ Deep-Scan History")
                    if succ:
                        messagebox.showinfo("Deep Scan", msg)
                        self._render_view() # Reload the UI to show the newly extracted traits/events
                    else:
                        messagebox.showerror("Error", msg)
                self.after(0, update_ui)
                
            import threading
            threading.Thread(target=worker, daemon=True).start()
            
        btn_scan = ctk.CTkButton(
            center_frame, text="✨ Deep-Scan History", font=("Arial", 14, "bold"),
            fg_color="#00ACC1", hover_color="#00838F", height=36, command=trigger_deep_scan
        )
        btn_scan.pack(side="left", padx=10)
        Tooltip(btn_scan, "Forces the AI to aggressively re-read every single turn of your entire history specifically searching for new lore about this entity.")

        # 2. The Save Button
        ctk.CTkButton(
            center_frame, text="💾 Save Entity Lore", font=("Arial", 14, "bold"), 
            fg_color="#2E7D32", hover_color="#1B5E20", height=36, command=save_entity
        ).pack(side="left", padx=10)
        
        
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
        messagebox.showinfo("Saved", "Plot Ledger updated successfully.")
        self._render_view()

    def _save_chapter_ledger(self):
        """Internal logic to extract text from Chapter boxes and commit to engine."""
        if not hasattr(self, 'chap_ui_references') or not self.chap_ui_references: return
        for chunk, box, tags_var in self.chap_ui_references:
            chunk["summary"] = box.get("1.0", "end").strip()
            chunk["tags"] = [t.strip() for t in tags_var.get().split(",") if t.strip()]
        self.engine.save_state()
        messagebox.showinfo("Saved", "Chapter Summaries updated successfully.")
        self._render_view()