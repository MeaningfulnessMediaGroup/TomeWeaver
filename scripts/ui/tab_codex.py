"""
    TomeWeaver: World Builder & Lore Editor
    ---------------------------------------
    Provides a multi-tab interface for authoring the physical environment,
    lore, system rules, and narrative bookends (Prologue/Epilogue) of the story.
    Features a dynamic 'Visual JSON Editor' that constructs Lists and Dictionaries.
"""
import json
import customtkinter as ctk
from tkinter import messagebox
from ui.tooltip import Tooltip

class CodexTab(ctk.CTkFrame):

    """
    World Builder & Lore Editor
    """
    def __init__(self, parent, engine):
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        
        # Hardcoded list of engine keys so we don't display them in the "Custom Lore" section
        self.core_keys = [
            "mode", "title", "author", "version", "creation_date", "tone", 
            "goal", "setting", "main_character", "starting_situation", 
            "starting_inventory", "inventory_dictionary", "inventory_and_state", 
            "lore_and_rules", "track_inventory", "can_die", "allow_cheats", 
            "plot_outline", "narrative"
        ]

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_core = self.tabs.add("Core Settings")
        self.tab_custom = self.tabs.add("Custom Lore (Codex)")
        self.tab_prompt = self.tabs.add("System Prompt")
        self.tab_prologue = self.tabs.add("Prologue")
        
        # Epilogues only exist in Campaigns. Sandbox goes on forever.
        if self.engine.is_campaign:
            self.tab_epilogue = self.tabs.add("Epilogue")

        self._build_core_settings()
        self._build_custom_lore()
        self._build_system_prompt_tab()
        self._build_narrative_tab(self.tab_prologue, "prologue")
        
        if self.engine.is_campaign:
            self._build_narrative_tab(self.tab_epilogue, "epilogue")


    # ---------------------------------------------------------
    # PART 1: CORE SETTINGS TAB
    # ---------------------------------------------------------
    def _build_core_settings(self):
        """Constructs the standard, fixed-schema UI fields for the setup.json."""
        
        # --- STICKY HEADER (Always visible) ---
        sticky_hdr = ctk.CTkFrame(self.tab_core, fg_color="transparent")
        sticky_hdr.pack(fill="x", padx=20, pady=(10, 0))
        
        # We save a reference to the Save button so we can change its text during AI Inventory Styling
        self.btn_save_core = ctk.CTkButton(sticky_hdr, text="Save Core Settings", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=self._save_core)
        self.btn_save_core.pack(side="left")
        
        btn_master_ai = ctk.CTkButton(sticky_hdr, text="✨ Generate World", font=("Arial", 14, "bold"), fg_color="#00ACC1", hover_color="#00838F", command=self._show_master_ai_dialog)
        btn_master_ai.pack(side="right")
        Tooltip(btn_master_ai, "Completely overhaul this active story using a single AI prompt. (Warning: Destructive)")
        
        # --- SCROLLABLE FORM ---
        scroll = ctk.CTkScrollableFrame(self.tab_core, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        self.core_scroll_frame = scroll # Save global reference for auto-scrolling
        
        # Helper to create consistent labeled textboxes with tooltips
        def add_field(parent, label_text, key, uid, is_multiline=False, tooltip_text="", show_ai=False):
            hdr = ctk.CTkFrame(parent, fg_color="transparent")
            hdr.pack(fill="x", pady=(10, 2))
            
            lbl = ctk.CTkLabel(hdr, text=label_text, font=("Arial", 14, "bold"))
            lbl.pack(side="left")
            if tooltip_text: Tooltip(lbl, tooltip_text)
            
            val = self.engine.setup_data.get(key, "")
            if is_multiline:
                box = ctk.CTkTextbox(parent, height=80, wrap="word", font=("Arial", 14))
                box.insert("1.0", val)
                box.pack(fill="x")
                widget = box
            else:
                var = ctk.StringVar(value=val)
                entry = ctk.CTkEntry(parent, textvariable=var, font=("Arial", 14))
                entry.pack(fill="x")
                widget = var
                
            if show_ai:
                # 💡 Help / Examples Button (Square, far right)
                btn_help = ctk.CTkButton(hdr, text="💡", width=24, height=20, font=("Segoe UI Emoji", 12), fg_color="#FBC02D", hover_color="#F57F17", text_color="black")
                btn_help.pack(side="right", padx=(2, 0))
                Tooltip(btn_help, "Help / Template Ideas")
                
                btn_inspire = ctk.CTkButton(hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
                btn_inspire.pack(side="right", padx=2)
                Tooltip(btn_inspire, "Expand your shorthand text into a rich description.")
                
                btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
                btn_reroll.pack(side="right", padx=2)
                Tooltip(btn_reroll, "Generate a completely new, creative idea for this field.")
                
                # Bindings
                btn_reroll.configure(command=lambda k=key, w=widget, btn=btn_reroll: self._generate_field_ui(k, w, btn, False))
                btn_inspire.configure(command=lambda k=key, w=widget, btn=btn_inspire: self._generate_field_ui(k, w, btn, True))
                btn_help.configure(command=lambda u=uid, w=widget, t=label_text: self._show_field_guide(u, w, t))

            return widget

        self.core_vars = {}
        
        self.core_vars["title"] = add_field(scroll, "Adventure Title:", "title", "TITLE", tooltip_text="The display name of your story.", show_ai=True)
        
        # Group Author, Version, and Date into 3 neat columns
        av_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        av_frame.pack(fill="x", pady=(15, 0))
        
        # Column 1: Author (Expands)
        auth_frame = ctk.CTkFrame(av_frame, fg_color="transparent")
        auth_frame.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        lbl_auth = ctk.CTkLabel(auth_frame, text="Author:", font=("Arial", 14, "bold"))
        lbl_auth.pack(anchor="w", pady=(0, 2))
        Tooltip(lbl_auth, "Creator of this cartridge.")
        self.core_vars["author"] = ctk.StringVar(value=self.engine.setup_data.get("author", "Unknown"))
        ctk.CTkEntry(auth_frame, textvariable=self.core_vars["author"], font=("Arial", 14)).pack(fill="x")
        
        # Column 2: Version
        ver_frame = ctk.CTkFrame(av_frame, fg_color="transparent")
        ver_frame.pack(side="left", padx=(0, 15))
        
        lbl_ver = ctk.CTkLabel(ver_frame, text="Version:", font=("Arial", 14, "bold"))
        lbl_ver.pack(anchor="w", pady=(0, 2))
        Tooltip(lbl_ver, "Useful if you update and share your cartridges.")
        self.core_vars["version"] = ctk.StringVar(value=self.engine.setup_data.get("version", "1.0"))
        ctk.CTkEntry(ver_frame, textvariable=self.core_vars["version"], font=("Arial", 14), width=80).pack(fill="x")

        # Column 3: Date
        date_frame = ctk.CTkFrame(av_frame, fg_color="transparent")
        date_frame.pack(side="left")
        
        lbl_date = ctk.CTkLabel(date_frame, text="Date:", font=("Arial", 14, "bold"))
        lbl_date.pack(anchor="w", pady=(0, 2))
        self.core_vars["creation_date"] = ctk.StringVar(value=self.engine.setup_data.get("creation_date", "Unknown"))
        ctk.CTkEntry(date_frame, textvariable=self.core_vars["creation_date"], font=("Arial", 14), width=120).pack(fill="x")

        self.core_vars["tone"] = add_field(scroll, "Atmosphere / Tone:", "tone", "TONE", tooltip_text="Instructs the AI on the writing style.", show_ai=True)
        self.core_vars["main_character"] = add_field(scroll, "Main Character:", "main_character", "CHAR", True, tooltip_text="Name and brief description of the protagonist.", show_ai=True)
        self.core_vars["goal"] = add_field(scroll, "Overarching Goal:", "goal", "GOAL", True, tooltip_text="The ultimate motivation driving the protagonist.", show_ai=True)
        self.core_vars["setting"] = add_field(scroll, "Default Setting / Location:", "setting", "SETTING", True, tooltip_text="The initial environment where the story begins.", show_ai=True)
        self.core_vars["starting_situation"] = add_field(scroll, "Starting Situation (Cold Open):", "starting_situation", "COLD_OPEN", True, tooltip_text="Sets the immediate context for Turn 1.", show_ai=True)
        self.core_vars["lore_and_rules"] = add_field(scroll, "Global Rules & Lore:", "lore_and_rules", "LORE", True, tooltip_text="Hard rules the AI must follow.", show_ai=True)
        
        # --- SETTINGS TOGGLES (Placed directly below Lore) ---
        settings_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        settings_frame.pack(fill="x", pady=(15, 20)) 
        
        # We must instantiate the variables FIRST so they exist in memory before the UI draws
        self.var_inv = ctk.BooleanVar(value=self.engine.setup_data.get("track_inventory", False))
        self.var_die = ctk.BooleanVar(value=self.engine.setup_data.get("can_die", False))
        self.var_cheats = ctk.BooleanVar(value=self.engine.setup_data.get("allow_cheats", False))
        
        switch_inv = ctk.CTkSwitch(settings_frame, text="Track Inventory & Health", variable=self.var_inv, command=self._toggle_inv_editor_visibility)
        switch_inv.pack(side="left", padx=(0, 20))
        
        ctk.CTkSwitch(settings_frame, text="Allow Game Over (Death)", variable=self.var_die).pack(side="left", padx=(0, 20))
        ctk.CTkSwitch(settings_frame, text="Allow Editing (Cheats)", variable=self.var_cheats).pack(side="left", padx=(0, 20))

        # --- INVENTORY SCHEMA EDITOR (Placed directly below Toggles) ---
        self.inv_master_container = ctk.CTkFrame(scroll, fg_color="transparent")
        self.inv_master_container.pack(fill="x", pady=(10, 50))
        
        # 1. Permanent Header for Buttons
        ai_hdr = ctk.CTkFrame(self.inv_master_container, fg_color="transparent")
        ai_hdr.pack(fill="x", padx=10, pady=(0, 10))
        
        lbl = ctk.CTkLabel(ai_hdr, text="Inventory & State Schema (Max 8 Slots):", font=("Arial", 14, "bold"))
        lbl.pack(side="left")
        Tooltip(lbl, "Define tracking slots and their visual style. The AI will strictly update these keys.")
        
        btn_help_inv = ctk.CTkButton(ai_hdr, text="💡", width=24, height=20, font=("Segoe UI Emoji", 12), fg_color="#FBC02D", hover_color="#F57F17", text_color="black")
        btn_help_inv.pack(side="right", padx=(2, 10))
        Tooltip(btn_help_inv, "Help / Template Ideas")
        
        btn_inspire = ctk.CTkButton(ai_hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
        btn_inspire.pack(side="right", padx=2)
        Tooltip(btn_inspire, "Ask the AI to generate an inventory based on an idea (e.g. 'Cyberpunk gear').")
        
        btn_reroll = ctk.CTkButton(ai_hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
        btn_reroll.pack(side="right", padx=2)
        Tooltip(btn_reroll, "Ask the AI to invent a brand new starting inventory schema fitting this world.")
        
        # Link the Help button to the global modal, passing 'INVENTORY' as the UID
        btn_help_inv.configure(command=lambda: self._show_field_guide("INVENTORY", None, "Inventory & State"))
        
        self.btn_add_slot = ctk.CTkButton(
            ai_hdr, text="+ Add Slot", width=80, height=20, font=("Arial", 11), fg_color="#4A4A4A", 
            command=lambda: self._add_inv_row("New_Key", "Empty", "📦", "#4A4A4A")
        )
        self.btn_add_slot.pack(side="right", padx=10)
        
        btn_reroll.configure(command=lambda btn=btn_reroll: self._generate_schema_ui("inventory_dictionary", "inventory", btn, False))
        btn_inspire.configure(command=lambda btn=btn_inspire: self._generate_schema_ui("inventory_dictionary", "inventory", btn, True))

        # 2. Permanent Container for Rows
        self.inv_rows_container = ctk.CTkFrame(self.inv_master_container, fg_color="transparent")
        self.inv_rows_container.pack(fill="x", padx=10)
        
        self.inv_schema_vars = []
        self._render_inv_editor()
        self._toggle_inv_editor_visibility() # Apply initial visibility state


    # ---------------------------------------------------------
    # UI EVENT HANDLERS
    # ---------------------------------------------------------

    def _show_field_guide(self, uid, widget, field_name):
        """Spawns the Help & Examples modal, filtering examples by the active engine mode."""
        from config import FIELD_GUIDES
        guide_data = FIELD_GUIDES.get(uid, {})
        
        if not guide_data:
            messagebox.showinfo("Help", "No guide available for this field yet.")
            return
            
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Guide: {field_name.replace(':', '')}")
        dialog.geometry("800x600")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        help_text = guide_data.get("help", "")
        if help_text:
            ctk.CTkLabel(dialog, text="How to use this field:", font=("Arial", 16, "bold"), text_color="#00ACC1").pack(anchor="w", padx=20, pady=(15, 5))
            ctk.CTkLabel(dialog, text=help_text, font=("Arial", 14), justify="left", wraplength=750).pack(anchor="w", padx=20, pady=(0, 15))

        ctk.CTkLabel(dialog, text="Click an example to use it:", font=("Arial", 16, "bold"), text_color="#00ACC1").pack(anchor="w", padx=20, pady=(10, 5))
        
        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=5)
        
        active_mode = str(self.engine.setup_data.get("mode", "sandbox")).upper()
        has_examples = False

        def apply_example(text):
            # Special Override: If it's the Inventory guide, route the text directly to the AI Schema generator
            if uid == "INVENTORY":
                # Find the 'Inspire' button in the main UI so we can use its loading state
                btn_ref = None
                try: btn_ref = self.inv_master_container.winfo_children()[0].winfo_children()[3] # The Inspire button
                except Exception: pass
                
                if btn_ref:
                    self._generate_schema_ui("inventory_dictionary", "inventory", btn_ref, True, direct_shorthand=text)
            else:
                # Standard behavior: Paste the text into the target widget
                if isinstance(widget, ctk.StringVar):
                    widget.set(text)
                else:
                    widget.delete("1.0", "end")
                    widget.insert("1.0", text)
            dialog.destroy()

        for ex in guide_data.get("examples", []):
            mode = ex.get("mode", "ALL")
            if mode in ["ALL", "ANY_MODE", active_mode]:
                has_examples = True
                btn = ctk.CTkButton(scroll, text=ex.get("text"), font=("Arial", 13), fg_color="#2B2B2B", hover_color="#4A4A4A", anchor="w", command=lambda t=ex.get("text"): apply_example(t))
                btn.pack(fill="x", pady=4, padx=10)

        if not has_examples:
            ctk.CTkLabel(scroll, text="No examples available for this game mode.", font=("Arial", 14, "italic"), text_color="gray").pack(pady=20)

    def _toggle_inv_editor_visibility(self):
        """Shows or hides the Inventory Editor based on the toggle switch."""
        if self.var_inv.get():
            self.inv_master_container.pack(fill="x", pady=(10, 50))
            
            # Auto-spawn the default Health slot if the dictionary is completely empty
            schema = self.engine.setup_data.get("inventory_dictionary", {})
            if not isinstance(schema, dict) or not schema:
                self.engine.setup_data["inventory_dictionary"] = {
                    "Health": {"val": "Good", "icon": "❤️", "color": "#B71C1C"}
                }
                self._render_inv_editor()
                
            # Auto-scroll to the absolute bottom so the new UI is instantly visible
            if hasattr(self, 'core_scroll_frame'):
                def snap_to_bottom():
                    self.core_scroll_frame.update_idletasks() # Force UI to recalculate heights
                    self.core_scroll_frame._parent_canvas.yview_moveto(1.0)
                self.after(50, snap_to_bottom)
        else:
            self.inv_master_container.pack_forget()

    def _show_master_ai_dialog(self):
        """Spawns the AI World Generator modal, pre-configured for the active workspace."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("AI World Overhaul")
        dialog.geometry("550x550")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="AI World Overhaul", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(15, 5))
        
        warn_lbl = ctk.CTkLabel(dialog, text="⚠️ WARNING: This will completely overwrite your current story settings.\nThere is no undo.", font=("Arial", 12, "bold"), text_color="#FBC02D")
        warn_lbl.pack(pady=(0, 10))

        # Lock the mode to whatever the current story already is
        current_mode = self.engine.setup_data.get("mode", "sandbox")
        
        mode_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        mode_frame.pack(pady=5)
        ctk.CTkLabel(mode_frame, text=f"Target Engine Mode: {current_mode.upper()}", font=("Arial", 12, "bold"), text_color="gray").pack()

        # AI Prompt
        ctk.CTkLabel(dialog, text="Overhaul Prompt:").pack(anchor="w", padx=20, pady=(5, 0))
        prompt_box = ctk.CTkTextbox(dialog, height=200, wrap="word", font=("Arial", 14))
        prompt_box.pack(fill="x", padx=20, pady=5)
        
        # Pre-fill with the active title to give the AI context
        active_title = self.engine.setup_data.get("title", "")
        if active_title: prompt_box.insert("1.0", f"A story titled '{active_title}' where...")

        # Narrative Generation Toggles
        chk_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        chk_frame.pack(fill="x", padx=20, pady=10) 
        
        gen_pro_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(chk_frame, text="Generate Prologue", variable=gen_pro_var).pack(side="left", padx=(0, 20))
        
        gen_epi_var = ctk.BooleanVar(value=False)
        chk_epi = ctk.CTkSwitch(chk_frame, text="Generate Epilogue", variable=gen_epi_var)
        chk_epi.pack(side="left")
        if current_mode == "sandbox":
            chk_epi.configure(state="disabled")

        status_lbl = ctk.CTkLabel(dialog, text="", font=("Arial", 12, "italic"))
        status_lbl.pack(pady=(5, 0)) 

        def on_generate():
            prompt = prompt_box.get("1.0", "end").strip()
            if not prompt:
                messagebox.showwarning("Missing Info", "Please enter an adventure concept prompt.")
                return

            btn_gen.configure(state="disabled", text="Overhauling... Please wait.")
            status_lbl.configure(text="Contacting LLM... This may take up to a minute.", text_color="#00ACC1")
            
            def worker():
                from api import TomeWeaverAPI
                from api import ADV_DIR
                
                # Use the new dedicated Overhaul method which injects directly into active memory
                success, msg = TomeWeaverAPI.overhaul_active_story(
                    self.engine, prompt, gen_pro_var.get(), gen_epi_var.get()
                )
                
                def on_complete():
                    if success:
                        dialog.destroy() 
                        
                        # Tell the app to do a hard visual reload of the workspace
                        folder_name = self.engine.adv_dir.relative_to(ADV_DIR).as_posix()
                        app = self.winfo_toplevel()
                        app.clear_container() 
                        app.open_workspace(folder_name, target_tab="World Builder")
                        
                        messagebox.showinfo("Success", "World successfully overhauled!")
                    else:
                        btn_gen.configure(state="normal", text="✨ Overhaul World")
                        status_lbl.configure(text="Generation failed. Check prompt and try again.", text_color="#F44336")
                        messagebox.showerror("AI Generation Error", msg)
                        
                self.after(0, on_complete)

            import threading
            threading.Thread(target=worker, daemon=True).start()

        btn_gen = ctk.CTkButton(dialog, text="✨ Overhaul World", font=("Arial", 16, "bold"), fg_color="#D32F2F", hover_color="#9A0007", width=220, height=45, command=on_generate)
        btn_gen.pack(pady=20)
        
    

    def _save_core(self, memory_only=False):
        """Extracts data from the standard form fields. Writes to disk unless memory_only is True."""
        old_title = self.engine.setup_data.get("title", "")
        new_title = self.core_vars["title"].get().strip()
        
        for key, widget in self.core_vars.items():
            if isinstance(widget, ctk.StringVar):
                self.engine.setup_data[key] = widget.get().strip()
            else:
                self.engine.setup_data[key] = widget.get("1.0", "end").strip()
                
        self.engine.setup_data["track_inventory"] = self.var_inv.get()
        self.engine.setup_data["can_die"] = self.var_die.get()
        self.engine.setup_data["allow_cheats"] = self.var_cheats.get()
        
        # Extract Inventory Schema
        new_schema = {}
        needs_ai = False
        for k_var, v_var, i_var, c_var in self.inv_schema_vars:
            k = k_var.get().strip().replace(" ", "_")
            if k:
                i_val = i_var.get().strip()
                c_val = c_var.get().strip()
                if not i_val or not c_val:
                    needs_ai = True
                new_schema[k] = {
                    "val": v_var.get().strip(),
                    "icon": i_val,
                    "color": c_val
                }
        self.engine.setup_data["inventory_dictionary"] = new_schema
        
        if memory_only: 
            return

        if needs_ai:
            # Prevent user from spamming save while AI is styling
            self.btn_save_core.configure(state="disabled", text="Auto-Styling Inventory...")
            
            def worker():
                from api import TomeWeaverAPI
                success, updated_schema = TomeWeaverAPI.autofill_inventory_styles(new_schema)
                
                # Apply absolute fallbacks if the API drops out or fails to fill a specific key
                for key, info in updated_schema.items():
                    if not info.get("icon"): info["icon"] = "🎒"
                    if not info.get("color"): info["color"] = "#1F6AA5"
                    
                self.engine.setup_data["inventory_dictionary"] = updated_schema
                
                def update_ui():
                    self.btn_save_core.configure(state="normal", text="Save Core Settings")
                    self._render_inv_editor() # Visually populate the boxes with the new emojis/hex codes
                    self._finalize_save_core(old_title, new_title)
                self.after(0, update_ui)
                
            import threading
            threading.Thread(target=worker, daemon=True).start()
        else:
            self._finalize_save_core(old_title, new_title)

    def _finalize_save_core(self, old_title, new_title):
        """Handles the physical disk write and directory rename hooks after all AI processing is complete."""
        # Actual explicit save clicked by user
        self._write_to_disk()
        
        # --- TITLE RENAME HOOK ---
        if new_title and new_title != old_title:
            from tkinter import messagebox
            msg = f"You changed the title to '{new_title}'.\n\nWould you like to rename the physical folder on your hard drive to match this new title?"
            if messagebox.askyesno("Rename Folder?", msg):
                from api import TomeWeaverAPI
                from api import ADV_DIR
                current_folder = self.engine.adv_dir.relative_to(ADV_DIR).as_posix()
                app = self.winfo_toplevel()
                success, new_folder_name = TomeWeaverAPI.rename_story(current_folder, new_title)
                
                if success:
                    messagebox.showinfo("Saved", f"Folder renamed to '{new_folder_name}'.")
                    app.clear_container() 
                    from config import ENGINE_CONFIG
                    ENGINE_CONFIG["last_active_story"] = new_folder_name
                    app.open_workspace(new_folder_name)
                    return
                else:
                    messagebox.showerror("Rename Failed", new_folder_name)
                    
        from tkinter import messagebox
        messagebox.showinfo("Saved", "Core Settings updated successfully.")

    def _render_inv_editor(self):
        # Clear ONLY the rows container
        for w in self.inv_rows_container.winfo_children(): w.destroy()
        self.inv_schema_vars.clear()
        
        schema = self.engine.setup_data.get("inventory_dictionary", {})
        if not isinstance(schema, dict): schema = {}
        
        for k, info in schema.items():
            self._add_inv_row(k, info.get("val", ""), info.get("icon", "🎒"), info.get("color", "#1F6AA5"))
            
        self._update_add_button_visibility()

    def _update_add_button_visibility(self):
        """Hides the +Add button if we reach the max limit of 8."""
        if len(self.inv_schema_vars) < 8:
            # We must re-pack it into the correct position inside the header
            self.btn_add_slot.pack(side="right", padx=10)
        else:
            self.btn_add_slot.pack_forget()

    def _add_inv_row(self, key, val, icon, color):
        row = ctk.CTkFrame(self.inv_rows_container, fg_color="transparent")
        row.pack(fill="x", pady=2)
        
        k_var = ctk.StringVar(value=key)
        v_var = ctk.StringVar(value=val)
        i_var = ctk.StringVar(value=icon)
        c_var = ctk.StringVar(value=color)
        
        ctk.CTkEntry(row, textvariable=k_var, width=120, font=("Arial", 13), placeholder_text="Key (e.g. Health)").pack(side="left", padx=2)
        ctk.CTkEntry(row, textvariable=v_var, width=120, font=("Arial", 13), placeholder_text="Initial Value").pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkEntry(row, textvariable=i_var, width=40, font=("Segoe UI Emoji", 13)).pack(side="left", padx=2)
        ctk.CTkEntry(row, textvariable=c_var, width=80, font=("Arial", 13)).pack(side="left", padx=2)
        
        # --- COLOR PICKER BUTTON ---
        def open_color_picker():
            from tkinter.colorchooser import askcolor
            # askcolor returns a tuple: ((r, g, b), '#hexcode')
            # Provide the current color so the picker starts on the right shade
            current = c_var.get().strip() or "#1F6AA5"
            _, hex_code = askcolor(title="Choose Pill Color", initialcolor=current)
            if hex_code:
                c_var.set(hex_code)

        # A small, square button acting as a color swatch
        btn_color = ctk.CTkButton(row, text="", width=24, fg_color=color, hover_color=color, 
                                  border_width=1, border_color="#555555", command=open_color_picker)
        btn_color.pack(side="left", padx=(5, 0))

        # Two-way binding: If the user manually types a hex code, instantly update the button's background
        def on_hex_type(*args):
            try:
                btn_color.configure(fg_color=c_var.get().strip(), hover_color=c_var.get().strip())
            except Exception:
                pass # Ignore invalid hex strings while they are typing
                
        c_var.trace_add("write", on_hex_type)

        # Save a reference to the exact instance of the row widget and its variables
        row_tuple = (k_var, v_var, i_var, c_var)
        self.inv_schema_vars.append(row_tuple)
        
        # Using default arguments in the lambda forcibly captures the correct variable instances
        def del_row(target_row=row, target_tuple=row_tuple):
            target_row.destroy()
            if target_tuple in self.inv_schema_vars:
                self.inv_schema_vars.remove(target_tuple)
            self._update_add_button_visibility()
            
        ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=del_row).pack(side="left", padx=5)
        self._update_add_button_visibility()
        
        
    # ---------------------------------------------------------
    # PART 2: DYNAMIC LORE TAB (The Codex)
    # ---------------------------------------------------------
    def _build_custom_lore(self):
        """Constructs the master-detail UI for arbitrary JSON schema manipulation."""
        # Left Pane (List of Keys)
        self.nav_frame = ctk.CTkScrollableFrame(self.tab_custom, width=200)
        self.nav_frame.pack(side="left", fill="y", padx=10, pady=10)
        
        btn_add = ctk.CTkButton(self.nav_frame, text="+ Add New Entry", fg_color="#1F6AA5", command=self._add_new_lore_key)
        btn_add.pack(fill="x", pady=(0, 15))

        # Right Pane (The dynamic editor)
        self.editor_frame = ctk.CTkFrame(self.tab_custom)
        self.editor_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self._refresh_lore_list()

    def _refresh_lore_list(self):
        """Rebuilds the left navigation list, filtering out system-reserved keys."""
        # We must cast winfo_children to a list() to prevent skipping widgets during destruction
        for widget in list(self.nav_frame.winfo_children()):
            # To be safe, we just destroy the entire row Frame holding the RadioButton and the Delete Button
            if isinstance(widget, ctk.CTkFrame):
                widget.destroy()

        self.lore_selection = ctk.StringVar(value="")
        custom_keys = [k for k in self.engine.setup_data.keys() if k not in self.core_keys]

        for key in custom_keys:
            row = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            rb = ctk.CTkRadioButton(row, text=key, variable=self.lore_selection, value=key, command=self._render_lore_editor)
            rb.pack(side="left")
            
            btn_del = ctk.CTkButton(row, text="X", width=20, fg_color="#B71C1C", hover_color="#7F0000", command=lambda k=key: self._delete_lore_key(k))
            btn_del.pack(side="right")

    def _add_new_lore_key(self):
        """Spawns a dialog allowing the user to define a new JSON key and its data type."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Lore Entry")
        dialog.geometry("350x250")
        dialog.attributes("-topmost", True)
        
        ctk.CTkLabel(dialog, text="Entry Name (e.g., 'family_tree'):").pack(pady=(20,5))
        name_entry = ctk.CTkEntry(dialog, width=250)
        name_entry.pack()
        
        ctk.CTkLabel(dialog, text="Data Type:").pack(pady=(15,5))
        type_var = ctk.StringVar(value="String (Paragraph)")
        
        types_list = [
            "String (Paragraph)", 
            "List (Bullet Points)", 
            "Dictionary (Key-Value)", 
            "Boolean (True/False)", 
            "Number (Value)"
        ]
        ctk.CTkOptionMenu(dialog, variable=type_var, values=types_list, width=250).pack()

        def confirm():
            key = name_entry.get().strip().replace(" ", "_")
            if not key: return
            if key in self.engine.setup_data:
                messagebox.showerror("Error", "Key already exists!")
                return
                
            t = type_var.get()
            if "String" in t: self.engine.setup_data[key] = ""
            elif "List" in t: self.engine.setup_data[key] = [""]
            elif "Dictionary" in t: self.engine.setup_data[key] = {"New_Key": "New_Value"}
            elif "Boolean" in t: self.engine.setup_data[key] = True
            elif "Number" in t: self.engine.setup_data[key] = 0
            
            self._refresh_lore_list()
            self.lore_selection.set(key)
            self._render_lore_editor()
            dialog.destroy()
            
        ctk.CTkButton(dialog, text="Add", command=confirm).pack(pady=20)

    def _delete_lore_key(self, key):
        """Permanently removes a custom key from the JSON structure."""
        if messagebox.askyesno("Delete", f"Are you sure you want to delete '{key}'?"):
            del self.engine.setup_data[key]
            self._refresh_lore_list()
            self._clear_editor()

    def _clear_editor(self):
        for widget in self.editor_frame.winfo_children():
            widget.destroy()

    def _render_lore_editor(self):
        """
        The Visual JSON Engine. 
        Detects the underlying Python type of the selected key (str, list, dict, bool)
        and generates the corresponding UI widgets to edit it safely without syntax errors.
        """
        self._clear_editor()
        key = self.lore_selection.get()
        if not key or key not in self.engine.setup_data: return
        
        data = self.engine.setup_data[key]
        
        ctk.CTkLabel(self.editor_frame, text=f"Editing: {key}", font=("Arial", 18, "bold")).pack(anchor="w", padx=20, pady=15)
        
        container = ctk.CTkScrollableFrame(self.editor_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10)
        
        self.dynamic_vars = []

        # --- TYPE: STRING ---
        if isinstance(data, str):
            hdr = ctk.CTkFrame(container, fg_color="transparent")
            hdr.pack(fill="x", pady=(0, 5))
            
            btn_inspire = ctk.CTkButton(hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            btn_inspire.pack(side="right", padx=2)
            
            btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
            btn_reroll.pack(side="right", padx=2)
            
            box = ctk.CTkTextbox(container, height=300, wrap="word", font=("Arial", 14))
            box.insert("1.0", data)
            box.pack(fill="both", expand=True)
            self.dynamic_vars = box
            
            btn_reroll.configure(command=lambda k=key, w=box, btn=btn_reroll: self._generate_field_ui(k, w, btn, False))
            btn_inspire.configure(command=lambda k=key, w=box, btn=btn_inspire: self._generate_field_ui(k, w, btn, True))

        # --- TYPE: LIST ---
        elif isinstance(data, list):
            hdr = ctk.CTkFrame(container, fg_color="transparent")
            hdr.pack(fill="x", pady=(0, 5))
            
            btn_inspire = ctk.CTkButton(hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            btn_inspire.pack(side="right", padx=2)
            
            btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
            btn_reroll.pack(side="right", padx=2)
            
            btn_reroll.configure(command=lambda k=key, btn=btn_reroll: self._generate_schema_ui(k, "list", btn, False))
            btn_inspire.configure(command=lambda k=key, btn=btn_inspire: self._generate_schema_ui(k, "list", btn, True))

            def delete_list_item(target_var):
                # Save current UI state, excluding the deleted item
                self.engine.setup_data[key] = [v.get() for v in self.dynamic_vars if v != target_var]
                self._render_lore_editor()

            for i, item in enumerate(data):
                var = ctk.StringVar(value=str(item))
                row = ctk.CTkFrame(container, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text="•").pack(side="left", padx=5)
                ctk.CTkEntry(row, textvariable=var, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
                
                # Note: We must bind the variable using lambda v=var to force the closure to capture the correct reference
                btn_del = ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda v=var: delete_list_item(v))
                btn_del.pack(side="left", padx=(5, 0))
                
                self.dynamic_vars.append(var)
                
            def add_list_item():
                # Read unsaved UI state to prevent wiping user's typing when the widget redraws
                self.engine.setup_data[key] = [v.get() for v in self.dynamic_vars]
                self.engine.setup_data[key].append("")
                self._render_lore_editor()
                
            ctk.CTkButton(container, text="+ Add Bullet", fg_color="#4A4A4A", command=add_list_item).pack(pady=10)

        # --- TYPE: DICTIONARY ---
        elif isinstance(data, dict):
            hdr = ctk.CTkFrame(container, fg_color="transparent")
            hdr.pack(fill="x", pady=(0, 5))
            
            btn_inspire = ctk.CTkButton(hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            btn_inspire.pack(side="right", padx=2)
            
            btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
            btn_reroll.pack(side="right", padx=2)
            
            btn_reroll.configure(command=lambda k=key, btn=btn_reroll: self._generate_schema_ui(k, "dict", btn, False))
            btn_inspire.configure(command=lambda k=key, btn=btn_inspire: self._generate_schema_ui(k, "dict", btn, True))

            def delete_dict_item(target_k_var):
                new_dict = {}
                for vk, vv in self.dynamic_vars:
                    if vk != target_k_var:
                        safe_k = vk.get().strip() or "Key"
                        new_dict[safe_k] = vv.get()
                self.engine.setup_data[key] = new_dict
                self._render_lore_editor()

            for k, v in data.items():
                row = ctk.CTkFrame(container, fg_color="transparent")
                row.pack(fill="x", pady=2)
                var_k = ctk.StringVar(value=str(k))
                var_v = ctk.StringVar(value=str(v))
                ctk.CTkEntry(row, textvariable=var_k, width=150, font=("Arial", 14, "bold")).pack(side="left", padx=5)
                ctk.CTkEntry(row, textvariable=var_v, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
                
                # Note: Late-binding protection via lambda vk=var_k
                btn_del = ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda vk=var_k: delete_dict_item(vk))
                btn_del.pack(side="left", padx=(5, 0))
                
                self.dynamic_vars.append((var_k, var_v))
                
            def add_dict_item():
                new_dict = {}
                # 1. Save all current unsaved typing
                for vk, vv in self.dynamic_vars:
                    safe_k = vk.get().strip() or "Key"
                    # Prevent duplicate key crashes
                    orig_k = safe_k
                    c = 1
                    while safe_k in new_dict:
                        safe_k = f"{orig_k}_{c}"
                        c += 1
                    new_dict[safe_k] = vv.get()
                
                # 2. Add the new pair safely
                safe_new = "New_Key"
                c = 1
                while safe_new in new_dict:
                    safe_new = f"New_Key_{c}"
                    c += 1
                new_dict[safe_new] = "New_Value"
                
                self.engine.setup_data[key] = new_dict
                self._render_lore_editor()
                
            ctk.CTkButton(container, text="+ Add Pair", fg_color="#4A4A4A", command=add_dict_item).pack(pady=10)

        # --- TYPE: BOOLEAN ---
        elif isinstance(data, bool):
            var = ctk.BooleanVar(value=data)
            ctk.CTkSwitch(container, text="Enabled (True/False)", variable=var, font=("Arial", 16)).pack(pady=20)
            self.dynamic_vars = var

        # --- TYPE: NUMBER ---
        elif isinstance(data, (int, float)):
            var = ctk.StringVar(value=str(data))
            ctk.CTkEntry(container, textvariable=var, font=("Arial", 16), width=200).pack(pady=20)
            ctk.CTkLabel(container, text="Must be a valid integer or decimal.", text_color="gray").pack()
            self.dynamic_vars = var


        # --- SAVE BUTTON ---
        def save_lore():
            # Conditionally extracts the data back out depending on what type of widget was rendered
            if isinstance(self.dynamic_vars, ctk.CTkTextbox):
                self.engine.setup_data[key] = self.dynamic_vars.get("1.0", "end").strip()
            elif isinstance(data, list):
                self.engine.setup_data[key] = [v.get().strip() for v in self.dynamic_vars if v.get().strip()]
            elif isinstance(data, dict):
                new_dict = {}
                for vk, vv in self.dynamic_vars:
                    if vk.get().strip(): new_dict[vk.get().strip()] = vv.get().strip()
                self.engine.setup_data[key] = new_dict
            elif isinstance(data, bool):
                self.engine.setup_data[key] = self.dynamic_vars.get()
            elif isinstance(data, (int, float)):
                try:
                    val = self.dynamic_vars.get().strip()
                    self.engine.setup_data[key] = float(val) if "." in val else int(val)
                except ValueError:
                    messagebox.showerror("Invalid Input", "Please enter a valid number.")
                    return
                
            self._write_to_disk()
            messagebox.showinfo("Saved", f"'{key}' updated successfully.")
            self._render_lore_editor() # Refresh UI

        ctk.CTkButton(self.editor_frame, text="Save Lore", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=save_lore).pack(pady=15)

    def _write_to_disk(self):
        """Commits the modified setup_data back to the physical setup.json file."""
        import json
        setup_file = self.engine.adv_dir / "setup.json"
        with open(setup_file, "w", encoding="utf-8") as f:
            json.dump(self.engine.setup_data, f, indent=4)
            
    # ---------------------------------------------------------
    # PART 3: PROLOGUE / EPILOGUE TABS
    # ---------------------------------------------------------
    def _build_narrative_tab(self, parent_frame, narr_type):
        """Builds a UI tab specifically for editing prologue.txt or epilogue.txt."""
        
        # --- Contextual Description ---
        if narr_type == "prologue":
            desc = "The Prologue is the very first thing the player will read. It establishes the initial scene and atmosphere before Turn 1."
        else:
            desc = "The Epilogue is the very last thing the player will read. It triggers automatically when the final Chapter Goal is achieved, concluding the story."
            
        ctk.CTkLabel(parent_frame, text=desc, font=("Arial", 14, "italic"), text_color="#A0A0A0", justify="left").pack(anchor="w", padx=20, pady=(15, 0))

        # --- Top Control Bar ---
        ctrl_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(ctrl_frame, text="Generation Style:", font=("Arial", 14, "bold")).pack(side="left", padx=(0, 10))
        
        narr_dict = self.engine.setup_data.get("narrative", {})
        current_style = narr_dict.get(narr_type, "expand")
        style_var = ctk.StringVar(value=current_style)
        
        ctk.CTkOptionMenu(
            ctrl_frame, variable=style_var, 
            values=["expand", "as_is", "generate", "none"], width=150
        ).pack(side="left")

        # Explanation Label
        help_text = (
            "expand: AI will expand the the Content into full prose.\n"
            "as_is: The Content will be shown verbatim, exactly as written (Bypasses AI).\n"
            "generate: AI will invent the Content on-the-fly based on the world setup.\n"
            "none: Skips this phase entirely."
        )
        ctk.CTkLabel(parent_frame, text=help_text, text_color="gray", justify="left").pack(anchor="w", padx=20, pady=5)

        # --- Text Editor ---
        txt_hdr = ctk.CTkFrame(parent_frame, fg_color="transparent")
        txt_hdr.pack(fill="x", padx=20, pady=(15, 2))
        
        ctk.CTkLabel(txt_hdr, text=f"{narr_type.capitalize()} Content:", font=("Arial", 14, "bold")).pack(side="left")
        
        btn_inspire = ctk.CTkButton(txt_hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
        btn_inspire.pack(side="right", padx=2)
        Tooltip(btn_inspire, "Expand your shorthand notes into rich, cinematic prose.")
        
        btn_reroll = ctk.CTkButton(txt_hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
        btn_reroll.pack(side="right", padx=2)
        Tooltip(btn_reroll, "Generate a brand new opening/closing narrative from scratch.")
        
        txt_box = ctk.CTkTextbox(parent_frame, wrap="word", font=("Georgia", 15))
        txt_box.pack(fill="both", expand=True, padx=20, pady=5)
        
        # Map the AI tools to the appropriate key in setup.json
        field_key = "prologue_text" if narr_type == "prologue" else "epilogue_text"
        btn_reroll.configure(command=lambda k=field_key, w=txt_box, btn=btn_reroll: self._generate_field_ui(k, w, btn, False))
        btn_inspire.configure(command=lambda k=field_key, w=txt_box, btn=btn_inspire: self._generate_field_ui(k, w, btn, True))
        
        # Load content from engine memory
        content = self.engine.prologue_content if narr_type == "prologue" else self.engine.epilogue_content
        if content:
            txt_box.insert("1.0", content)

        # --- Save Button ---
        def save_narrative():
            # 1. Update setup.json
            if "narrative" not in self.engine.setup_data:
                self.engine.setup_data["narrative"] = {}
            self.engine.setup_data["narrative"][narr_type] = style_var.get()
            self._write_to_disk()
            
            # 2. Save .txt file
            text_content = txt_box.get("1.0", "end").strip()
            txt_file = self.engine.adv_dir / f"{narr_type}.txt"
            
            if text_content:
                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write(text_content)
                # Update memory
                if narr_type == "prologue": self.engine.prologue_content = text_content
                else: self.engine.epilogue_content = text_content
            else:
                # If empty, delete the file to keep directory clean
                if txt_file.exists(): txt_file.unlink()
                if narr_type == "prologue": self.engine.prologue_content = ""
                else: self.engine.epilogue_content = ""
                
            messagebox.showinfo("Saved", f"{narr_type.capitalize()} saved successfully.")

        ctk.CTkButton(parent_frame, text="Save " + narr_type.capitalize(), font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=save_narrative).pack(pady=20)
        
        
    def _build_system_prompt_tab(self):
        """Builds a UI tab to edit the AI's core instructions."""
        ctk.CTkLabel(self.tab_prompt, text="System Prompt (Core AI Rules):", font=("Arial", 14, "bold")).pack(anchor="w", padx=20, pady=(15, 5))
        ctk.CTkLabel(self.tab_prompt, text="WARNING: This dictates how the AI formats its JSON. Edit with extreme caution.", text_color="#F44336").pack(anchor="w", padx=20)
        
        txt_box = ctk.CTkTextbox(self.tab_prompt, wrap="word", font=("Consolas", 13))
        txt_box.pack(fill="both", expand=True, padx=20, pady=5)
        
        prompt_file = self.engine.adv_dir / "system_prompt.txt"
        if prompt_file.exists():
            with open(prompt_file, "r", encoding="utf-8") as f:
                txt_box.insert("1.0", f.read().strip())

        def save_prompt():
            content = txt_box.get("1.0", "end").strip()
            if content:
                with open(prompt_file, "w", encoding="utf-8") as f:
                    f.write(content)
                self.engine.system_prompt_text = content # Update active engine memory
                messagebox.showinfo("Saved", "System prompt updated safely.")

        ctk.CTkButton(self.tab_prompt, text="Save System Prompt", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=save_prompt).pack(pady=20)
        
    # ---------------------------------------------------------
    # AI FIELD GENERATION (Reroll / Inspire)
    # ---------------------------------------------------------
    def _generate_field_ui(self, field_key, widget, button, is_inspire):
        """Asynchronously calls the API to generate or expand data for a single UI field."""
        shorthand = None
        if is_inspire:
            if isinstance(widget, ctk.StringVar): shorthand = widget.get().strip()
            else: shorthand = widget.get("1.0", "end").strip()
                
            if not shorthand:
                messagebox.showwarning("Missing Input", "Type some shorthand ideas in the box first to inspire the AI!")
                return
                
        orig_text = button.cget("text")
        button.configure(state="disabled", text="...")
        
        # Pull UI edits into the engine memory so the LLM has up-to-date context, but DO NOT write to disk.
        self._save_core(memory_only=True)
        
        def worker():
            from api import TomeWeaverAPI
            success, result = TomeWeaverAPI.generate_field_data(self.engine.setup_data, field_key, shorthand)
            
            def update_ui():
                button.configure(state="normal", text=orig_text)
                if success:
                    if isinstance(widget, ctk.StringVar):
                        widget.set(result)
                    else:
                        widget.delete("1.0", "end")
                        widget.insert("1.0", result)
                else:
                    messagebox.showerror("Generation Error", result)
                    
            self.after(0, update_ui)
            
        import threading
        threading.Thread(target=worker, daemon=True).start()
        
        
    def _generate_schema_ui(self, field_key, schema_type, button, is_inspire, direct_shorthand=None):
        """Asynchronously generates complex JSON (Lists/Dicts/Inventory) and triggers a full UI redraw."""
        shorthand = direct_shorthand
        if is_inspire and not direct_shorthand:
            dialog = ctk.CTkInputDialog(text="Enter an idea for this field (e.g. 'Cyberpunk hacker gear'):", title="AI Inspiration")
            shorthand = dialog.get_input()
            if not shorthand: return
                
        orig_text = button.cget("text")
        button.configure(state="disabled", text="...")
        
        self._save_core(memory_only=True)
        
        def worker():
            from api import TomeWeaverAPI
            success, result = TomeWeaverAPI.generate_schema_data(self.engine.setup_data, schema_type, field_key, shorthand)
            
            def update_ui():
                button.configure(state="normal", text=orig_text)
                if success:
                    # Update active memory with the newly generated JSON object
                    self.engine.setup_data[field_key] = result
                    
                    # Force a UI redraw depending on which tab we are in
                    if schema_type == "inventory":
                        self._render_inv_editor()
                    else:
                        self._render_lore_editor()
                else:
                    messagebox.showerror("Generation Error", result)
                    
            self.after(0, update_ui)
            
        import threading
        threading.Thread(target=worker, daemon=True).start()