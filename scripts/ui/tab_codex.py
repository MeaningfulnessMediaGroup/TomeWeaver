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
            "starting_inventory", "lore_and_rules", "track_inventory", 
            "can_die", "allow_cheats", "plot_outline", "narrative"
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
        scroll = ctk.CTkScrollableFrame(self.tab_core, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        from ui.tooltip import Tooltip

        # Helper to create consistent labeled textboxes with tooltips
        def add_field(parent, label_text, key, is_multiline=False, tooltip_text=""):
            lbl = ctk.CTkLabel(parent, text=label_text, font=("Arial", 14, "bold"))
            lbl.pack(anchor="w", pady=(10, 2))
            if tooltip_text: Tooltip(lbl, tooltip_text)
            
            val = self.engine.setup_data.get(key, "")
            if is_multiline:
                box = ctk.CTkTextbox(parent, height=80, wrap="word", font=("Arial", 14))
                box.insert("1.0", val)
                box.pack(fill="x")
                return box
            else:
                var = ctk.StringVar(value=val)
                ctk.CTkEntry(parent, textvariable=var, font=("Arial", 14)).pack(fill="x")
                return var

        self.core_vars = {}
        
        self.core_vars["title"] = add_field(scroll, "Adventure Title:", "title", tooltip_text="The display name of your story.")
        
        # Group Author, Version, and Date into 3 neat columns
        av_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        # FIX: Explicit 15px gap above to push away from Title, 0px gap below to prevent double-spacing before Tone.
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

        self.core_vars["tone"] = add_field(scroll, "Atmosphere / Tone:", "tone", tooltip_text="Instructs the AI on the writing style (e.g., Gritty, Fast-paced, Humorous).")
        self.core_vars["main_character"] = add_field(scroll, "Main Character:", "main_character", True, tooltip_text="Name and brief description of the protagonist.")
        self.core_vars["goal"] = add_field(scroll, "Overarching Goal:", "goal", True, tooltip_text="The ultimate motivation driving the protagonist (mainly used in Sandbox).")
        self.core_vars["setting"] = add_field(scroll, "Default Setting / Location:", "setting", True, tooltip_text="The initial environment where the story begins.")
        self.core_vars["starting_situation"] = add_field(scroll, "Starting Situation (Cold Open):", "starting_situation", True, tooltip_text="Sets the immediate context for Turn 1.")
        self.core_vars["lore_and_rules"] = add_field(scroll, "Global Rules & Lore:", "lore_and_rules", True, tooltip_text="Hard rules the AI must follow (e.g., 'Magic does not exist', 'Vampires burn in sunlight').")
        
        # --- INVENTORY SCHEMA EDITOR ---
        lbl = ctk.CTkLabel(scroll, text="Inventory & State Schema (Max 8 Slots):", font=("Arial", 14, "bold"))
        lbl.pack(anchor="w", pady=(15, 2))
        Tooltip(lbl, "Define tracking slots and their visual style. The AI will strictly update these keys.")
        
        self.inv_editor_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self.inv_editor_frame.pack(fill="x", padx=10)
        self.inv_schema_vars = []
        self._render_inv_editor()
        
        # Settings Row
        
        # Settings Row
        settings_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        settings_frame.pack(fill="x", pady=20)
        
        self.var_inv = ctk.BooleanVar(value=self.engine.setup_data.get("track_inventory", False))
        ctk.CTkSwitch(settings_frame, text="Track Inventory & Health", variable=self.var_inv).pack(side="left", padx=(0, 20))
        
        self.var_die = ctk.BooleanVar(value=self.engine.setup_data.get("can_die", False))
        ctk.CTkSwitch(settings_frame, text="Allow Game Over (Death)", variable=self.var_die).pack(side="left", padx=(0, 20))
        
        self.var_cheats = ctk.BooleanVar(value=self.engine.setup_data.get("allow_cheats", False))
        ctk.CTkSwitch(settings_frame, text="Allow Editing (Cheats)", variable=self.var_cheats).pack(side="left", padx=(0, 20))
        
        # Save Button
        ctk.CTkButton(scroll, text="Save Core Settings", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=self._save_core).pack(pady=30)

    def _save_core(self):
        """Extracts data from the standard form fields and writes to disk."""
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
        for k_var, v_var, i_var, c_var in self.inv_schema_vars:
            k = k_var.get().strip().replace(" ", "_")
            if k:
                new_schema[k] = {
                    "val": v_var.get().strip(),
                    "icon": i_var.get().strip() or "🎒",
                    "color": c_var.get().strip() or "#1F6AA5"
                }
        self.engine.setup_data["inventory_dictionary"] = new_schema
        
        self._write_to_disk()
        messagebox.showinfo("Saved", "Core Settings updated successfully.")

    def _render_inv_editor(self):
        # Clear existing layout
        for w in self.inv_editor_frame.winfo_children(): w.destroy()
        self.inv_schema_vars.clear()
        
        # We need a dedicated container just for the rows so the +Add button stays firmly at the bottom
        self.inv_rows_container = ctk.CTkFrame(self.inv_editor_frame, fg_color="transparent")
        self.inv_rows_container.pack(fill="x")
        
        self.btn_add_slot = ctk.CTkButton(
            self.inv_editor_frame, text="+ Add Slot", fg_color="#4A4A4A", 
            command=lambda: self._add_inv_row("New_Key", "Empty", "📦", "#4A4A4A")
        )
        
        # Make sure we read from the new correct name!
        schema = self.engine.setup_data.get("inventory_dictionary", {})
        if not isinstance(schema, dict): schema = {}
        
        for k, info in schema.items():
            self._add_inv_row(k, info.get("val", ""), info.get("icon", "🎒"), info.get("color", "#1F6AA5"))
            
        self._update_add_button_visibility()

    def _update_add_button_visibility(self):
        """Hides the +Add button if we reach the max limit of 8."""
        if len(self.inv_schema_vars) < 8:
            self.btn_add_slot.pack(pady=10)
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
            
            self._write_to_disk()
            self._refresh_lore_list()
            self.lore_selection.set(key)
            self._render_lore_editor()
            dialog.destroy()
            
        ctk.CTkButton(dialog, text="Add", command=confirm).pack(pady=20)

    def _delete_lore_key(self, key):
        """Permanently removes a custom key from the JSON structure."""
        if messagebox.askyesno("Delete", f"Are you sure you want to delete '{key}'?"):
            del self.engine.setup_data[key]
            self._write_to_disk()
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
            box = ctk.CTkTextbox(container, height=300, wrap="word", font=("Arial", 14))
            box.insert("1.0", data)
            box.pack(fill="both", expand=True)
            self.dynamic_vars = box

        # --- TYPE: LIST ---
        elif isinstance(data, list):
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
        ctk.CTkLabel(parent_frame, text=f"{narr_type.capitalize()} Content:", font=("Arial", 14, "bold")).pack(anchor="w", padx=20, pady=(15, 5))
        
        txt_box = ctk.CTkTextbox(parent_frame, wrap="word", font=("Georgia", 15))
        txt_box.pack(fill="both", expand=True, padx=20, pady=5)
        
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