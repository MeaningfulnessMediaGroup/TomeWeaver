"""
    TomeWeaver: Universe Editor Tab
    -------------------------------
    Allows editing of the master_setup.json file from within an active thread.
    Includes Core Settings and a Dynamic Custom Lore (Codex) builder.
"""
import json
import customtkinter as ctk
from tkinter import messagebox
from config import save_json_atomically
from ui.tooltip import Tooltip

class UniverseTab(ctk.CTkFrame):
    """Shared-universe settings editor (master lore and thread metadata)."""

    def __init__(self, parent, engine):
        """Build universe-level codex controls bound to the active engine.

        Args:
            parent: Parent CTk container (workspace tab host).
            engine: Loaded engine with ``is_universe_thread`` context.
        """
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        
        # Keys that are hardcoded into the UI and shouldn't appear in the Custom Lore list
        self.core_keys = ["universe_title", "author", "tone", "lore_and_rules", "creation_date"]

        # --- TABS ---
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_core = self.tabs.add("Core Settings")
        self.tab_custom = self.tabs.add("Custom Lore (Codex)")

        self._build_core_settings()
        self._build_custom_lore()

    # ---------------------------------------------------------
    # PART 1: CORE SETTINGS TAB
    # ---------------------------------------------------------

    def _build_core_settings(self):
        sticky_hdr = ctk.CTkFrame(self.tab_core, fg_color="transparent")
        sticky_hdr.pack(fill="x", padx=20, pady=(10, 0))
        
        btn_save = ctk.CTkButton(sticky_hdr, text="💾 Save Universe", font=("Arial", 14, "bold"), fg_color="#E65100", hover_color="#BF360C", command=self._save_core)
        btn_save.pack(side="left")
        
        center_frame = ctk.CTkFrame(sticky_hdr, fg_color="transparent")
        center_frame.pack(side="left", expand=True)
        ctk.CTkLabel(center_frame, text="🌌 Global Universe Settings", font=("Arial", 20, "bold"), text_color="#FF9800").pack()
        
        btn_master_ai = ctk.CTkButton(sticky_hdr, text="✨ Overhaul Universe", font=("Arial", 14, "bold"), fg_color="#00ACC1", hover_color="#00838F", command=self._show_master_ai_dialog)
        btn_master_ai.pack(side="right")
        Tooltip(btn_master_ai, "Completely overhaul the global rules and tone of this Universe. (Warning: Destructive)")

        # CRITICAL FIX: Use a standard CTkFrame so the Textbox can mathematically 'expand' 
        # to fill the bottom of the screen without getting trapped by a Scrollable layout.
        content_frame = ctk.CTkFrame(self.tab_core, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        ctk.CTkLabel(content_frame, text="Changes made here will instantly affect ALL stories inside this Universe.", text_color="#FF9800", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 15))

        self.u_vars = {}

        def add_field(label_text, key, uid, is_multiline=False, tooltip_text="", show_ai=False):
            hdr = ctk.CTkFrame(content_frame, fg_color="transparent")
            # For the multiline box, we want its header frame to sit normally, but the BOX itself to expand.
            hdr.pack(fill="x", pady=(10, 2))
            
            lbl = ctk.CTkLabel(hdr, text=label_text, font=("Arial", 14, "bold"))
            lbl.pack(side="left")
            if tooltip_text: Tooltip(lbl, tooltip_text)
            
            val = self.engine.master_setup_data.get(key, "")
            if is_multiline:
                # The container for the textbox must expand to fill the bottom of content_frame
                box_container = ctk.CTkFrame(content_frame, fg_color="transparent")
                box_container.pack(fill="both", expand=True, padx=10, pady=(0, 20))
                
                box = ctk.CTkTextbox(box_container, wrap="word", font=("Arial", 14))
                box.insert("1.0", val)
                box.pack(fill="both", expand=True)
                widget = box
            else:
                var = ctk.StringVar(value=val)
                entry = ctk.CTkEntry(hdr, textvariable=var, font=("Arial", 14))
                entry.pack(side="left", fill="x", expand=True, padx=10)
                widget = var
                
            if show_ai:
                btn_help = ctk.CTkButton(hdr, text="💡", width=24, height=20, font=("Segoe UI Emoji", 12), fg_color="#FBC02D", hover_color="#F57F17", text_color="black")
                btn_help.pack(side="right", padx=(2, 0))
                Tooltip(btn_help, "Help / Template Ideas")
                
                btn_inspire = ctk.CTkButton(hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
                btn_inspire.pack(side="right", padx=2)
                Tooltip(btn_inspire, "Expand your shorthand text into a rich description.")
                
                btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
                btn_reroll.pack(side="right", padx=2)
                Tooltip(btn_reroll, "Generate a completely new, creative idea for this field.")
                
                btn_reroll.configure(command=lambda k=key, w=widget, btn=btn_reroll: self._generate_field_ui(k, w, btn, False))
                btn_inspire.configure(command=lambda k=key, w=widget, btn=btn_inspire: self._generate_field_ui(k, w, btn, True))
                
                parent_ws = self.master.master
                if hasattr(parent_ws, 'codex_tab'):
                    btn_help.configure(command=lambda u=uid, w=widget, t=label_text: parent_ws.codex_tab._show_field_guide(u, w, t))

            self.u_vars[key] = widget
            return widget

        add_field("Universe Name:", "universe_title", "TITLE", tooltip_text="The display name of your shared universe.", show_ai=True)
        
        av_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        av_frame.pack(fill="x", pady=(15, 0))
        
        auth_frame = ctk.CTkFrame(av_frame, fg_color="transparent")
        auth_frame.pack(side="left", fill="x", expand=True, padx=(0, 15))
        ctk.CTkLabel(auth_frame, text="Author:", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 2))
        self.u_vars["author"] = ctk.StringVar(value=self.engine.master_setup_data.get("author", "Unknown"))
        ctk.CTkEntry(auth_frame, textvariable=self.u_vars["author"], font=("Arial", 14)).pack(fill="x")
        
        date_frame = ctk.CTkFrame(av_frame, fg_color="transparent")
        date_frame.pack(side="left")
        ctk.CTkLabel(date_frame, text="Creation Date:", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 2))
        self.u_vars["creation_date"] = ctk.StringVar(value=self.engine.master_setup_data.get("creation_date", "Unknown"))
        ctk.CTkEntry(date_frame, textvariable=self.u_vars["creation_date"], font=("Arial", 14), width=120).pack(fill="x")

        add_field("Global Tone / Atmosphere:", "tone", "TONE", tooltip_text="Sets the overarching mood for all stories.", show_ai=True)
        add_field("Global Lore & Hard Rules:", "lore_and_rules", "LORE", is_multiline=True, tooltip_text="Hard rules the AI must follow across all threads.", show_ai=True)

    def _save_core(self, silent=False):
        for key, widget in self.u_vars.items():
            if isinstance(widget, ctk.StringVar):
                self.engine.master_setup_data[key] = widget.get().strip()
            else:
                self.engine.master_setup_data[key] = widget.get("1.0", "end").strip()
                
        if hasattr(self.engine, "master_setup_file") and self.engine.master_setup_file:
            save_json_atomically(self.engine.master_setup_data, self.engine.master_setup_file)
            
            # --- TITLE RENAME HOOK ---
            target_name = self.engine.master_setup_data.get("universe_title", "").strip()
            from api import ADV_DIR, sanitize_foldername
            current_folder_name = self.engine.master_setup_file.parent.name
            
            # Use sanitized matching to guarantee we catch visual changes even if the OS normalizes them
            if not silent and target_name and sanitize_foldername(target_name) != sanitize_foldername(current_folder_name):
                msg = f"You changed the Universe Name to '{target_name}'.\n\nWould you like to rename the physical folder on your hard drive to match?"
                if messagebox.askyesno("Rename Folder?", msg):
                    from api import TomeWeaverAPI
                    current_rel_path = self.engine.master_setup_file.parent.relative_to(ADV_DIR).as_posix()
                    success, new_folder_rel_path = TomeWeaverAPI.rename_folder(current_rel_path, target_name)
                    
                    if success:
                        messagebox.showinfo("Saved", f"Universe folder renamed to '{target_name}'.")
                        
                        # CRITICAL PATH FIX: Update the engine's internal path so subsequent saves don't write to the old ghost directory!
                        self.engine.master_setup_file = ADV_DIR / new_folder_rel_path / "master_setup.json"
                        
                        app = self.winfo_toplevel()
                        app.clear_container() 
                        
                        story_name = self.engine.adv_dir.name
                        new_story_rel_path = f"{new_folder_rel_path}/{story_name}"
                        
                        from config import ENGINE_CONFIG
                        ENGINE_CONFIG["last_active_story"] = new_story_rel_path
                        app.open_workspace(new_story_rel_path, target_tab="Universe")
                        return
                    else:
                        messagebox.showerror("Rename Failed", new_folder_rel_path)
            
            if not silent: messagebox.showinfo("Saved", "Universe settings updated globally.")
        else:
            if not silent: messagebox.showerror("Error", "Could not locate master_setup.json")

    def _show_master_ai_dialog(self):
        """Spawns the AI World Generator modal, pre-configured for the Universe."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("AI Universe Overhaul")
        dialog.geometry("550x350")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="AI Universe Overhaul", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(15, 5))
        ctk.CTkLabel(dialog, text="⚠️ WARNING: This will overwrite the Global Lore and Tone. Local story settings will remain intact.", font=("Arial", 12, "bold"), text_color="#FF9800", wraplength=450).pack(pady=(0, 10))

        ctk.CTkLabel(dialog, text="Overhaul Prompt:").pack(anchor="w", padx=20, pady=(5, 0))
        prompt_box = ctk.CTkTextbox(dialog, height=120, wrap="word", font=("Arial", 14))
        prompt_box.pack(fill="x", padx=20, pady=5)
        
        active_title = self.engine.master_setup_data.get("universe_title", "")
        if active_title: prompt_box.insert("1.0", f"A vast universe titled '{active_title}' where...")

        status_lbl = ctk.CTkLabel(dialog, text="", font=("Arial", 12, "italic"))
        status_lbl.pack(pady=(5, 0)) 

        def on_generate():
            prompt = prompt_box.get("1.0", "end").strip()
            if not prompt: return

            btn_gen.configure(state="disabled", text="Overhauling... Please wait.")
            status_lbl.configure(text="Contacting LLM... This may take up to a minute.", text_color="#00ACC1")
            
            def worker():
                from api import TomeWeaverAPI
                from api import ADV_DIR
                
                success, msg = TomeWeaverAPI.overhaul_active_universe(self.engine, prompt)
                
                def on_complete():
                    if success:
                        dialog.destroy() 
                        folder_name = self.engine.adv_dir.relative_to(ADV_DIR).as_posix()
                        app = self.winfo_toplevel()
                        app.clear_container() 
                        app.open_workspace(folder_name, target_tab="Universe")
                        messagebox.showinfo("Success", "Universe successfully overhauled!")
                    else:
                        btn_gen.configure(state="normal", text="✨ Overhaul Universe")
                        status_lbl.configure(text="Generation failed. Check prompt and try again.", text_color="#F44336")
                        messagebox.showerror("AI Generation Error", msg)
                        
                self.after(0, on_complete)

            import threading
            threading.Thread(target=worker, daemon=True).start()

        btn_gen = ctk.CTkButton(dialog, text="✨ Overhaul Universe", font=("Arial", 16, "bold"), fg_color="#E65100", hover_color="#BF360C", width=220, height=45, command=on_generate)
        btn_gen.pack(pady=20)


    def _generate_field_ui(self, field_key, widget, button, is_inspire):
        """Asynchronously calls the API to generate or expand data for a single UI field."""
        shorthand = None
        if is_inspire:
            if isinstance(widget, ctk.StringVar): shorthand = widget.get().strip()
            else: shorthand = widget.get("1.0", "end").strip()
            if not shorthand:
                messagebox.showwarning("Missing Input", "Type some shorthand ideas in the box first to inspire the AI!")
                return
                
        self.winfo_toplevel().configure(cursor="watch")
        orig_text = button.cget("text")
        button.configure(state="disabled", text="...")
        self._save_core(silent=True)
        
        def worker():
            from api import TomeWeaverAPI
            # We must trick the API into thinking it's generating for a setup.json file by passing the master dict
            success, result = TomeWeaverAPI.generate_field_data(self.engine.master_setup_data, field_key, shorthand)
            def update_ui():
                self.winfo_toplevel().configure(cursor="")
                button.configure(state="normal", text=orig_text)
                if success:
                    if isinstance(widget, ctk.StringVar): widget.set(result)
                    else:
                        widget.delete("1.0", "end")
                        widget.insert("1.0", result)
                else: messagebox.showerror("Generation Error", result)
            self.after(0, update_ui)
            
        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------
    # PART 2: DYNAMIC CUSTOM LORE TAB
    # ---------------------------------------------------------
    def _build_custom_lore(self):
        self.nav_frame = ctk.CTkScrollableFrame(self.tab_custom, width=200)
        self.nav_frame.pack(side="left", fill="y", padx=10, pady=10)
        
        btn_add = ctk.CTkButton(self.nav_frame, text="+ Add New Entry", fg_color="#1F6AA5", command=self._add_new_lore_key)
        btn_add.pack(fill="x", pady=(0, 15))

        self.editor_frame = ctk.CTkFrame(self.tab_custom)
        self.editor_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self._refresh_lore_list()

    def _refresh_lore_list(self):
        for widget in list(self.nav_frame.winfo_children()):
            if isinstance(widget, ctk.CTkFrame):
                widget.destroy()

        self.lore_selection = ctk.StringVar(value="")
        custom_keys = [k for k in self.engine.master_setup_data.keys() if k not in self.core_keys]

        for key in custom_keys:
            row = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            rb = ctk.CTkRadioButton(row, text=key, variable=self.lore_selection, value=key, command=self._render_lore_editor)
            rb.pack(side="left")
            
            btn_del = ctk.CTkButton(row, text="X", width=20, fg_color="#B71C1C", hover_color="#7F0000", command=lambda k=key: self._delete_lore_key(k))
            btn_del.pack(side="right")

    def _add_new_lore_key(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Global Lore Entry")
        dialog.geometry("350x250")
        dialog.attributes("-topmost", True)
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())
        
        ctk.CTkLabel(dialog, text="Entry Name (e.g., 'magic_system'):").pack(pady=(20,5))
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
            if key in self.engine.master_setup_data:
                messagebox.showerror("Error", "Key already exists!")
                return
                
            t = type_var.get()
            if "String" in t: self.engine.master_setup_data[key] = ""
            elif "List" in t: self.engine.master_setup_data[key] = [""]
            elif "Dictionary" in t: self.engine.master_setup_data[key] = {"New_Key": "New_Value"}
            elif "Boolean" in t: self.engine.master_setup_data[key] = True
            elif "Number" in t: self.engine.master_setup_data[key] = 0
            
            self._refresh_lore_list()
            self.lore_selection.set(key)
            self._render_lore_editor()
            dialog.destroy()
            
        ctk.CTkButton(dialog, text="Add", command=confirm).pack(pady=20)

    def _delete_lore_key(self, key):
        if messagebox.askyesno("Delete", f"Are you sure you want to delete '{key}'?"):
            del self.engine.master_setup_data[key]
            self._refresh_lore_list()
            for widget in self.editor_frame.winfo_children(): widget.destroy()

    def _render_lore_editor(self):
        for widget in self.editor_frame.winfo_children(): widget.destroy()
        
        key = self.lore_selection.get()
        if not key or key not in self.engine.master_setup_data: return
        
        data = self.engine.master_setup_data[key]
        
        ctk.CTkLabel(self.editor_frame, text=f"Editing Global: {key}", font=("Arial", 18, "bold"), text_color="#FF9800").pack(anchor="w", padx=20, pady=15)
        
        container = ctk.CTkScrollableFrame(self.editor_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10)
        
        self.dynamic_vars = []

        if isinstance(data, str):
            box = ctk.CTkTextbox(container, height=300, wrap="word", font=("Arial", 14))
            box.insert("1.0", data)
            box.pack(fill="both", expand=True)
            self.dynamic_vars = box

        elif isinstance(data, list):
            def delete_list_item(target_var):
                self.engine.master_setup_data[key] = [v.get() for v in self.dynamic_vars if v != target_var]
                self._render_lore_editor()

            for i, item in enumerate(data):
                var = ctk.StringVar(value=str(item))
                row = ctk.CTkFrame(container, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text="•").pack(side="left", padx=5)
                ctk.CTkEntry(row, textvariable=var, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
                btn_del = ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda v=var: delete_list_item(v))
                btn_del.pack(side="left", padx=(5, 0))
                self.dynamic_vars.append(var)
                
            def add_list_item():
                self.engine.master_setup_data[key] = [v.get() for v in self.dynamic_vars]
                self.engine.master_setup_data[key].append("")
                self._render_lore_editor()
                
            ctk.CTkButton(container, text="+ Add Bullet", fg_color="#4A4A4A", command=add_list_item).pack(pady=10)

        elif isinstance(data, dict):
            def delete_dict_item(target_k_var):
                new_dict = {}
                for vk, vv in self.dynamic_vars:
                    if vk != target_k_var:
                        new_dict[vk.get().strip() or "Key"] = vv.get()
                self.engine.master_setup_data[key] = new_dict
                self._render_lore_editor()

            for k, v in data.items():
                row = ctk.CTkFrame(container, fg_color="transparent")
                row.pack(fill="x", pady=2)
                var_k = ctk.StringVar(value=str(k))
                var_v = ctk.StringVar(value=str(v))
                ctk.CTkEntry(row, textvariable=var_k, width=150, font=("Arial", 14, "bold")).pack(side="left", padx=5)
                ctk.CTkEntry(row, textvariable=var_v, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
                btn_del = ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda vk=var_k: delete_dict_item(vk))
                btn_del.pack(side="left", padx=(5, 0))
                self.dynamic_vars.append((var_k, var_v))
                
            def add_dict_item():
                new_dict = {}
                for vk, vv in self.dynamic_vars:
                    safe_k = vk.get().strip() or "Key"
                    orig_k = safe_k
                    c = 1
                    while safe_k in new_dict:
                        safe_k = f"{orig_k}_{c}"
                        c += 1
                    new_dict[safe_k] = vv.get()
                
                safe_new = "New_Key"
                c = 1
                while safe_new in new_dict:
                    safe_new = f"New_Key_{c}"
                    c += 1
                new_dict[safe_new] = "New_Value"
                
                self.engine.master_setup_data[key] = new_dict
                self._render_lore_editor()
                
            ctk.CTkButton(container, text="+ Add Pair", fg_color="#4A4A4A", command=add_dict_item).pack(pady=10)

        elif isinstance(data, bool):
            var = ctk.BooleanVar(value=data)
            ctk.CTkSwitch(container, text="Enabled (True/False)", variable=var, font=("Arial", 16)).pack(pady=20)
            self.dynamic_vars = var

        elif isinstance(data, (int, float)):
            var = ctk.StringVar(value=str(data))
            ctk.CTkEntry(container, textvariable=var, font=("Arial", 16), width=200).pack(pady=20)
            ctk.CTkLabel(container, text="Must be a valid integer or decimal.", text_color="gray").pack()
            self.dynamic_vars = var

        def save_lore():
            if isinstance(self.dynamic_vars, ctk.CTkTextbox):
                self.engine.master_setup_data[key] = self.dynamic_vars.get("1.0", "end").strip()
            elif isinstance(data, list):
                self.engine.master_setup_data[key] = [v.get().strip() for v in self.dynamic_vars if v.get().strip()]
            elif isinstance(data, dict):
                new_dict = {}
                for vk, vv in self.dynamic_vars:
                    if vk.get().strip(): new_dict[vk.get().strip()] = vv.get().strip()
                self.engine.master_setup_data[key] = new_dict
            elif isinstance(data, bool):
                self.engine.master_setup_data[key] = self.dynamic_vars.get()
            elif isinstance(data, (int, float)):
                try:
                    val = self.dynamic_vars.get().strip()
                    self.engine.master_setup_data[key] = float(val) if "." in val else int(val)
                except ValueError:
                    messagebox.showerror("Invalid Input", "Please enter a valid number.")
                    return
                
            save_json_atomically(self.engine.master_setup_data, self.engine.master_setup_file)
            messagebox.showinfo("Saved", f"'{key}' updated globally.")
            self._render_lore_editor()

        ctk.CTkButton(self.editor_frame, text="Save Lore", font=("Arial", 14, "bold"), fg_color="#E65100", hover_color="#BF360C", command=save_lore).pack(pady=15)
        