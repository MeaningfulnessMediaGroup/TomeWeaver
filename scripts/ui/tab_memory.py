"""
    TomeWeaver: Memory & Lore UI
    ----------------------------
    Provides a RAG (Retrieval-Augmented Generation) viewer for long-term memory.
    Displays the AI-generated Plot Summaries and the evolving Character/Location states.
"""
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
        
        # --- HEADER ---
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(hdr, text="Long-Term Memory Ledger", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(side="left", padx=10, pady=10)
        
        self.btn_compile = ctk.CTkButton(hdr, text="⟳ Compile Missing History", font=("Arial", 12, "bold"), fg_color="#F57C00", hover_color="#E65100", command=self._compile_history)
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
        dialog.geometry("480x420")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Compile Long-Term Memory", font=("Arial", 16, "bold"), text_color="#00ACC1").pack(pady=(20, 10))
        ctk.CTkLabel(dialog, text="This will scan your history and ask the AI to generate missing data. This consumes API tokens.", wraplength=400, text_color="gray").pack(padx=20, pady=(0, 20))

        v_mode = ctk.StringVar(value="missing")
        
        rb_base = ctk.CTkRadioButton(dialog, text="Base Lore Only (Parse setup.json and Prologue)", variable=v_mode, value="base")
        rb_base.pack(anchor="w", padx=40, pady=(0, 10))
        Tooltip(rb_base, "Extracts static traits from your World Builder text without reading the gameplay turns.")
        
        ctk.CTkRadioButton(dialog, text="Standard Compile (Only missing chunks)", variable=v_mode, value="missing").pack(anchor="w", padx=40, pady=10)
        
        rb_force = ctk.CTkRadioButton(dialog, text="Deep Entity Scan (Re-read all chunks)", variable=v_mode, value="force")
        rb_force.pack(anchor="w", padx=40, pady=10)
        Tooltip(rb_force, "If you just added a new Character/Location, use this to scan the entire history for past events involving them.")

        # Divider
        ctk.CTkFrame(dialog, height=2, fg_color="#333333").pack(fill="x", padx=40, pady=15)

        v_recon = ctk.BooleanVar(value=True)
        cb_recon = ctk.CTkCheckBox(dialog, text="Auto-Reconcile Duplicates (Merge aliases)", variable=v_recon)
        cb_recon.pack(anchor="w", padx=40)
        Tooltip(cb_recon, "Runs a final AI pass to automatically merge duplicate entities like 'John' and 'John Smith'.")

        def apply_compile():
            mode_selection = v_mode.get()
            run_recon = v_recon.get()
            dialog.destroy()
            
            self.winfo_toplevel().configure(cursor="watch")
            self.btn_compile.configure(state="disabled", text="Initializing...")
            
            def on_progress(current, total):
                if current == "Seeding":
                    msg = "Extracting Base Lore..."
                else:
                    msg = f"Processing Chunk {current}/{total}..."
                self.after(0, lambda: self.btn_compile.configure(text=msg))
                
            def on_complete(success, msg):
                def update_ui():
                    self.winfo_toplevel().configure(cursor="") # Restore cursor
                    self.btn_compile.configure(state="normal", text="⟳ Compile Missing History")
                    messagebox.showinfo("Complete", msg)
                    self._refresh_nav()
                    self._render_view()
                self.after(0, update_ui)
                
            self.engine.compile_missing_memories(
                compile_mode=mode_selection, 
                run_reconciliation=run_recon,
                progress_callback=on_progress, 
                completion_callback=on_complete
            )

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Start Compiler", width=120, fg_color="#F57C00", hover_color="#E65100", command=apply_compile).pack(side="right", padx=10)

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
                # Completely wipe all active aliases if we are doing a nuclear wipe
                self.engine.memory["aliases"] = {"character_ledger": {}, "location_ledger": {}, "artifact_ledger": {}}
                
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
        
        # 1. The Plot Ledger Button
        row = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 15))
        ctk.CTkRadioButton(row, text="📖 The Plot Ledger", font=("Arial", 14, "bold"), variable=self.active_selection, value="PLOT_LEDGER", command=self._render_view).pack(side="left")
        
        # 2. Characters List
        ctk.CTkLabel(self.nav_frame, text="Characters", font=("Arial", 12, "bold"), text_color="gray").pack(anchor="w", pady=(5, 2))
        chars = self.engine.memory.get("character_ledger", {})
        for name in sorted(chars.keys()):
            r = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkRadioButton(r, text=f"👤 {name}", variable=self.active_selection, value=f"CHAR_{name}", command=self._render_view).pack(side="left")
            ctk.CTkButton(r, text="X", width=20, fg_color="#B71C1C", hover_color="#7F0000", command=lambda n=name: self._delete_entity(n, "character_ledger")).pack(side="right")
        
        ctk.CTkButton(self.nav_frame, text="+ Add Character", fg_color="#4A4A4A", hover_color="#333333", command=lambda: self._add_entity("character_ledger")).pack(fill="x", pady=(5, 15))
        
        # 3. Locations List
        ctk.CTkLabel(self.nav_frame, text="Locations", font=("Arial", 12, "bold"), text_color="gray").pack(anchor="w", pady=(5, 2))
        locs = self.engine.memory.get("location_ledger", {})
        for name in sorted(locs.keys()):
            r = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkRadioButton(r, text=f"🗺️ {name}", variable=self.active_selection, value=f"LOC_{name}", command=self._render_view).pack(side="left")
            ctk.CTkButton(r, text="X", width=20, fg_color="#B71C1C", hover_color="#7F0000", command=lambda n=name: self._delete_entity(n, "location_ledger")).pack(side="right")
            
        ctk.CTkButton(self.nav_frame, text="+ Add Location", fg_color="#4A4A4A", hover_color="#333333", command=lambda: self._add_entity("location_ledger")).pack(fill="x", pady=(5, 15))
        
        # 4. Artifacts List
        ctk.CTkLabel(self.nav_frame, text="Artifacts / Items", font=("Arial", 12, "bold"), text_color="gray").pack(anchor="w", pady=(5, 2))
        arts = self.engine.memory.get("artifact_ledger", {})
        for name in sorted(arts.keys()):
            r = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkRadioButton(r, text=f"💎 {name}", variable=self.active_selection, value=f"ART_{name}", command=self._render_view).pack(side="left")
            ctk.CTkButton(r, text="X", width=20, fg_color="#B71C1C", hover_color="#7F0000", command=lambda n=name: self._delete_entity(n, "artifact_ledger")).pack(side="right")
            
        ctk.CTkButton(self.nav_frame, text="+ Add Artifact", fg_color="#4A4A4A", hover_color="#333333", command=lambda: self._add_entity("artifact_ledger")).pack(fill="x", pady=(5, 0))

        self._render_view()

    def _delete_entity(self, name, ledger_type):
        if messagebox.askyesno("Delete", f"Stop tracking memory for '{name}'?"):
            if name in self.engine.memory[ledger_type]:
                del self.engine.memory[ledger_type][name]
                self.engine.save_state()
                self.active_selection.set("PLOT_LEDGER")
                self._refresh_nav()

    def _add_entity(self, ledger_type):
        if ledger_type == "character_ledger": type_str = "Character"
        elif ledger_type == "location_ledger": type_str = "Location"
        else: type_str = "Artifact"
        dialog = ctk.CTkInputDialog(text=f"Enter the exact name of a {type_str} to track:", title=f"Add {type_str}")
        name = dialog.get_input()
        if name and name.strip():
            clean_name = name.strip()
            if clean_name not in self.engine.memory[ledger_type]:
                self.engine.memory[ledger_type][clean_name] = {"characteristics": {}, "ledger": []}
                self.engine.save_state()
                prefix = "CHAR_" if ledger_type == "character_ledger" else "LOC_"
                self.active_selection.set(f"{prefix}{clean_name}")
                self._refresh_nav()

    def _render_view(self):
        for w in self.editor_frame.winfo_children(): w.destroy()
        selection = self.active_selection.get()
        
        if selection == "PLOT_LEDGER":
            self._render_plot_ledger()
        elif selection.startswith("CHAR_"):
            self._render_entity_editor(selection.replace("CHAR_", "", 1), "character_ledger")
        elif selection.startswith("LOC_"):
            self._render_entity_editor(selection.replace("LOC_", "", 1), "location_ledger")
        elif selection.startswith("ART_"):
            self._render_entity_editor(selection.replace("ART_", "", 1), "artifact_ledger")


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
            btn_del.pack(side="right")
            
            box = ctk.CTkTextbox(card, height=120, wrap="word", font=("Arial", 14))
            box.insert("1.0", chunk.get("summary", ""))
            box.pack(fill="x", padx=15, pady=(0, 15))
            
            # Save a reference to the box back into the UI object so we can read it later
            chunk["_ui_box"] = box

        def save_plot_ledger():
            for chunk in plot_list:
                if "_ui_box" in chunk:
                    chunk["summary"] = chunk["_ui_box"].get("1.0", "end").strip()
                    del chunk["_ui_box"] # Clean up memory reference before saving to JSON
            self.engine.save_state()
            messagebox.showinfo("Saved", "Plot summaries updated.")
            self._render_view()

        ctk.CTkButton(self.editor_frame, text="Save Summaries", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=save_plot_ledger).pack(pady=10)
        ctk.CTkLabel(self.editor_frame, text="Use the engine configuration to change the Memory Chunk size.", font=("Arial", 12, "italic"), text_color="#555555").pack(pady=20)

    def _render_entity_editor(self, entity_name, ledger_type):
        if ledger_type == "character_ledger": type_str = "Character"; icon = "👤"
        elif ledger_type == "location_ledger": type_str = "Location"; icon = "🗺️"
        else: type_str = "Artifact / Item"; icon = "💎"
        
        # --- HEADER (Editable Name & Merge Tool) ---
        hdr = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(0, 5))
        
        ctk.CTkLabel(hdr, text=f"The Lore Bible: {icon}", font=("Arial", 18, "bold")).pack(side="left")
        
        # Editable Name Field
        self.var_entity_name = ctk.StringVar(value=entity_name)
        ctk.CTkEntry(hdr, textvariable=self.var_entity_name, font=("Arial", 18, "bold"), width=300, fg_color="transparent", border_width=1).pack(side="left", padx=10)
        
        def prompt_merge():
            safe_entity_name = entity_name
            if safe_entity_name not in self.engine.memory[ledger_type]: return
            all_entities = [k for k in self.engine.memory[ledger_type].keys() if k != safe_entity_name]
            if not all_entities: return
                
            dialog = ctk.CTkToplevel(self)
            dialog.title(f"Merge '{safe_entity_name}'")
            dialog.geometry("450x250")
            dialog.attributes("-topmost", True)
            dialog.grab_set()
            
            from ui.tooltip import center_window_on_parent
            center_window_on_parent(dialog, self.winfo_toplevel())
            
            ctk.CTkLabel(dialog, text=f"Select Master Entity to merge '{safe_entity_name}' into:", font=("Arial", 14, "bold")).pack(pady=20)
            
            target_var = ctk.StringVar(value=all_entities[0])
            ctk.CTkOptionMenu(dialog, variable=target_var, values=all_entities, width=300).pack(pady=10)
            
            def apply_merge():
                master_name = target_var.get()
                master = self.engine.memory[ledger_type][master_name]
                slave = self.engine.memory[ledger_type][safe_entity_name]
                
                if isinstance(master, list): master = {"characteristics": {}, "ledger": master}
                if isinstance(slave, list): slave = {"characteristics": {}, "ledger": slave}
                
                master["characteristics"].update(slave.get("characteristics", {}))
                master["ledger"].extend(slave.get("ledger", []))
                
                self.engine.memory.setdefault("aliases", {"character_ledger": {}, "location_ledger": {}, "artifact_ledger": {}})[ledger_type][safe_entity_name] = master_name
                
                del self.engine.memory[ledger_type][safe_entity_name]
                self.engine.save_state()
                
                dialog.destroy()
                prefix = "CHAR_" if ledger_type == "character_ledger" else ("LOC_" if ledger_type == "location_ledger" else "ART_")
                self.active_selection.set(f"{prefix}{master_name}")
                self._refresh_nav()
                
            ctk.CTkButton(dialog, text="Confirm Merge", fg_color="#F57C00", hover_color="#E65100", command=apply_merge).pack(pady=20)
            
        btn_merge = ctk.CTkButton(hdr, text="🔗 Merge Into...", font=("Arial", 12, "bold"), fg_color="#7B1FA2", hover_color="#4A148C", height=24, width=100, command=prompt_merge)
        btn_merge.pack(side="right")
        Tooltip(btn_merge, "Combine this entity into another one. Creates an alias so future AI mentions are auto-corrected.")
        
        # --- ALIAS EDITOR ---
        alias_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        alias_frame.pack(fill="x", padx=10, pady=(5, 20))
        ctk.CTkLabel(alias_frame, text="Aliases (Comma separated):", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
        
        all_aliases = self.engine.memory.setdefault("aliases", {}).setdefault(ledger_type, {})
        current_aliases = [k for k, v in all_aliases.items() if v == entity_name]
        
        self.var_aliases = ctk.StringVar(value=", ".join(current_aliases))
        ctk.CTkEntry(alias_frame, textvariable=self.var_aliases, font=("Arial", 12), fg_color="transparent", width=400).pack(side="left", padx=10)
        Tooltip(alias_frame, "If the AI uses these names, they will be automatically redirected to this Master Entity.")

        # --- DATA EXTRACTION ---
        # Fetch the LIVE dictionary from memory
        if entity_name not in self.engine.memory[ledger_type]:
            self.engine.memory[ledger_type][entity_name] = {"characteristics": {}, "ledger": [], "author_notes": ""}
            
        active_data = self.engine.memory[ledger_type][entity_name]
        
        # Auto-migrate legacy list formats
        if isinstance(active_data, list):
            active_data = {"characteristics": {}, "ledger": active_data, "author_notes": ""}
            self.engine.memory[ledger_type][entity_name] = active_data
            
        # --- AUTHOR'S NOTES (Immortal Custom Data) ---
        notes_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        notes_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        lbl_notes = ctk.CTkLabel(notes_frame, text="Author's Notes (Indestructible):", font=("Arial", 14, "bold"), text_color="#4CAF50")
        lbl_notes.pack(anchor="w")
        Tooltip(lbl_notes, "The AI cannot overwrite or delete this box. Use it to force the AI to remember critical facts.")
        
        self.var_notes = ctk.CTkTextbox(notes_frame, height=80, wrap="word", font=("Arial", 14))
        self.var_notes.insert("1.0", active_data.get("author_notes", ""))
        self.var_notes.pack(fill="x", pady=(5, 0))

        # --- SECTION 1: CHARACTERISTICS DICTIONARY ---
        ctk.CTkLabel(self.editor_frame, text="Static Characteristics (Traits, Appearance, Quirks)", font=("Arial", 14, "bold"), text_color="#00ACC1").pack(anchor="w", padx=10, pady=(10, 5))
        
        dict_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        dict_container.pack(fill="x", padx=10)
        
        self.trait_vars = []
        traits = active_data.get("characteristics", {})
        
        def delete_trait(target_k_var):
            new_dict = {vk.get().strip(): vv.get() for vk, vv in self.trait_vars if vk != target_k_var and vk.get().strip()}
            self.engine.memory[ledger_type][entity_name]["characteristics"] = new_dict
            self.engine.save_state()
            self._render_view()
            
        for k, v in traits.items():
            row = ctk.CTkFrame(dict_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var_k = ctk.StringVar(value=str(k))
            var_v = ctk.StringVar(value=str(v))
            ctk.CTkEntry(row, textvariable=var_k, width=150, font=("Arial", 14, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=var_v, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda vk=var_k: delete_trait(vk)).pack(side="left", padx=(5, 0))
            self.trait_vars.append((var_k, var_v))
            
        def add_trait():
            new_dict = {vk.get().strip(): vv.get() for vk, vv in self.trait_vars if vk.get().strip()}
            safe_new = "New_Trait"
            c = 1
            while safe_new in new_dict: safe_new = f"New_Trait_{c}"; c += 1
            new_dict[safe_new] = "Value"
            self.engine.memory[ledger_type][entity_name]["characteristics"] = new_dict
            self.engine.save_state()
            self._render_view()
            
        ctk.CTkButton(self.editor_frame, text="+ Add Trait", fg_color="#4A4A4A", command=add_trait).pack(pady=(5, 20))

        # --- SECTION 2: EVENT LEDGER (Bullets) ---
        ctk.CTkLabel(self.editor_frame, text="Chronological Event Ledger", font=("Arial", 14, "bold"), text_color="#FFCA28").pack(anchor="w", padx=10, pady=(10, 5))

        list_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        list_container.pack(fill="x", padx=10)

        self.bullet_vars = []
        bullets = active_data.get("ledger", [])

        def delete_bullet(target_var):
            self.engine.memory[ledger_type][entity_name]["ledger"] = [v.get() for v in self.bullet_vars if v != target_var]
            self.engine.save_state()
            self._render_view()

        for b_text in bullets:
            row = ctk.CTkFrame(list_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = ctk.StringVar(value=str(b_text))
            ctk.CTkLabel(row, text="•", font=("Arial", 16, "bold")).pack(side="left", padx=5)
            ctk.CTkEntry(row, textvariable=var, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda v=var: delete_bullet(v)).pack(side="left", padx=(5, 0))
            self.bullet_vars.append(var)

        def add_bullet():
            self.engine.memory[ledger_type][entity_name]["ledger"] = [v.get() for v in self.bullet_vars]
            self.engine.memory[ledger_type][entity_name]["ledger"].append("New event...")
            self.engine.save_state()
            self._render_view()

        ctk.CTkButton(self.editor_frame, text="+ Add Event", fg_color="#4A4A4A", command=add_bullet).pack(pady=(5, 15))

        # --- SAVE ENTITY BUTTON ---
        def save_entity():
            # 1. Update Traits, Ledger, and Notes
            new_traits = {vk.get().strip(): vv.get().strip() for vk, vv in self.trait_vars if vk.get().strip()}
            new_ledger = [v.get().strip() for v in self.bullet_vars if v.get().strip()]
            self.engine.memory[ledger_type][entity_name]["characteristics"] = new_traits
            self.engine.memory[ledger_type][entity_name]["ledger"] = new_ledger
            self.engine.memory[ledger_type][entity_name]["author_notes"] = self.var_notes.get("1.0", "end").strip()
            
            # 2. Update Aliases
            all_aliases = self.engine.memory.setdefault("aliases", {}).setdefault(ledger_type, {})
            # Remove old aliases mapped to this entity
            keys_to_delete = [k for k, v in all_aliases.items() if v == entity_name]
            for k in keys_to_delete: del all_aliases[k]
            
            # Add new aliases
            new_aliases_raw = self.var_aliases.get()
            if new_aliases_raw:
                for a in new_aliases_raw.split(","):
                    clean_a = a.strip()
                    if clean_a: all_aliases[clean_a] = entity_name

            # 3. Handle Rename
            new_name = self.var_entity_name.get().strip()
            target_name = entity_name
            if new_name and new_name != entity_name:
                if new_name in self.engine.memory[ledger_type]:
                    messagebox.showerror("Error", f"An entity named '{new_name}' already exists. Use the Merge tool instead.")
                    return
                # Swap keys
                self.engine.memory[ledger_type][new_name] = self.engine.memory[ledger_type].pop(entity_name)
                
                # Re-map aliases to new name
                for k, v in all_aliases.items():
                    if v == entity_name: all_aliases[k] = new_name
                    
                target_name = new_name
                prefix = "CHAR_" if ledger_type == "character_ledger" else ("LOC_" if ledger_type == "location_ledger" else "ART_")
                self.active_selection.set(f"{prefix}{target_name}")

            self.engine.save_state()
            messagebox.showinfo("Saved", f"'{target_name}' updated successfully.")
            self._refresh_nav()

        ctk.CTkButton(self.editor_frame, text="Save Entity Lore", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=save_entity).pack(pady=20)