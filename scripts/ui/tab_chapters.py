"""
    TomeWeaver: Campaign Outline Editor
    -----------------------------------
    A dedicated UI tab for managing Campaign Mode chapters.
    Provides a master-detail interface where users can navigate, reorder,
    add, and modify the sequential Micro-Objectives of narrative chapters.
"""
import json
import customtkinter as ctk
from tkinter import messagebox
from ui.tooltip import Tooltip


class ChapterTab(ctk.CTkFrame):

    """
    Campaign Outline Editor
    """
    def __init__(self, parent, engine):
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        self.selected_idx = ctk.IntVar(value=-1)

        # Left Pane: Navigation List
        self.nav_frame = ctk.CTkScrollableFrame(self, width=280)
        self.nav_frame.pack(side="left", fill="y", padx=10, pady=10)

        btn_add = ctk.CTkButton(self.nav_frame, text="+ Add Chapter", fg_color="#1F6AA5", command=self._add_chapter)
        btn_add.pack(fill="x", pady=(0, 15))

        self.list_container = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        self.list_container.pack(fill="both", expand=True)

        # Right Pane: Form Editor
        self.editor_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.editor_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self.chapter_fields = {} 
        self.objective_ui_refs = []

        self._refresh_list()

    # ---------------------------------------------------------
    # LEFT PANE: LIST NAVIGATION
    # ---------------------------------------------------------

    def _refresh_list(self):
        """Clears and rebuilds the chapter navigation list in the left pane."""
        for w in list(self.list_container.winfo_children()):
            w.destroy()

        outline = self.engine.setup_data.get("plot_outline", [])
        if not outline: return

        for i, chap in enumerate(outline):
            row = ctk.CTkFrame(self.list_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            title = chap.get("title", f"Chapter {i+1}")
            display_title = title if len(title) < 18 else title[:15] + "..."
            
            rb = ctk.CTkRadioButton(row, text=f"{i+1}. {display_title}", variable=self.selected_idx, value=i, command=self._render_editor)
            rb.pack(side="left", fill="x", expand=True)

            # Reorder & Delete Buttons
            btn_frame = ctk.CTkFrame(row, fg_color="transparent")
            btn_frame.pack(side="right")
            
            ctk.CTkButton(btn_frame, text="↑", width=20, command=lambda idx=i: self._move_up(idx)).pack(side="left", padx=1)
            ctk.CTkButton(btn_frame, text="↓", width=20, command=lambda idx=i: self._move_down(idx)).pack(side="left", padx=1)
            ctk.CTkButton(btn_frame, text="X", width=20, fg_color="#B71C1C", hover_color="#7F0000", command=lambda idx=i: self._delete_chapter(idx)).pack(side="left", padx=(5,0))

        # Auto-select the first item if nothing is selected or if out of bounds
        if self.selected_idx.get() < 0 or self.selected_idx.get() >= len(outline):
            self.selected_idx.set(0)
        
        self._render_editor()

    def _move_up(self, idx):
        if idx > 0:
            outline = self.engine.setup_data["plot_outline"]
            outline[idx], outline[idx-1] = outline[idx-1], outline[idx]
            self.selected_idx.set(idx-1)
            self._refresh_list()

    def _move_down(self, idx):
        outline = self.engine.setup_data["plot_outline"]
        if idx < len(outline) - 1:
            outline[idx], outline[idx+1] = outline[idx+1], outline[idx]
            self.selected_idx.set(idx+1)
            self._refresh_list()

    def _delete_chapter(self, idx):
        outline = self.engine.setup_data["plot_outline"]
        if len(outline) <= 1:
            messagebox.showerror("Error", "Campaigns must have at least one chapter.")
            return
        if messagebox.askyesno("Delete", "Are you sure you want to delete this chapter?"):
            outline.pop(idx)
            self._refresh_list()

    def _add_chapter(self):
        outline = self.engine.setup_data.setdefault("plot_outline", [])
        outline.append({
            "title": f"Chapter {len(outline)+1}",
            "setting": "", "pov": "", "time": "",
            "objectives": [{
                "goal": "New Objective",
                "obstacles": "None",
                "setting": "",
                "pov": "",
                "status": "ACTIVE"
            }]
        })
        self.selected_idx.set(len(outline)-1)
        self._refresh_list()

    # ---------------------------------------------------------
    # RIGHT PANE: FORM EDITOR
    # ---------------------------------------------------------

    def _clear_editor(self):
        """Wipes the right-hand form editor clean."""
        for w in list(self.editor_frame.winfo_children()):
            w.destroy()
        self.chapter_fields.clear()
        self.objective_ui_refs.clear()

    def _render_editor(self):
        """Rebuilds the form fields to match the data of the currently selected chapter."""
        self._clear_editor()
        idx = self.selected_idx.get()
        outline = self.engine.setup_data.get("plot_outline", [])
        if idx < 0 or idx >= len(outline): return

        chap = outline[idx]

        # --- GLOBAL CHAPTER HEADER & BUTTONS ---
        hdr_top = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        hdr_top.pack(fill="x", padx=10, pady=(5, 15))
        
        ctk.CTkLabel(hdr_top, text=f"Editing Chapter {idx+1}", font=("Arial", 18, "bold"), text_color="#4CAF50").pack(side="left")
        
        btn_inspire_chap = ctk.CTkButton(hdr_top, text="🪄 Inspire Chapter", width=120, height=26, font=("Arial", 12, "bold"), fg_color="#00ACC1", hover_color="#00838F")
        btn_inspire_chap.pack(side="right", padx=5)
        Tooltip(btn_inspire_chap, "Generate the entire chapter based on a prompt.")
        
        btn_reroll_chap = ctk.CTkButton(hdr_top, text="⟳ Reroll Chapter", width=120, height=26, font=("Arial", 12, "bold"), fg_color="#F57C00", hover_color="#E65100")
        btn_reroll_chap.pack(side="right", padx=5)
        Tooltip(btn_reroll_chap, "Generate a completely new chapter outline.")
        
        btn_inspire_chap.configure(command=lambda: self._generate_full_chapter(True, btn_inspire_chap))
        btn_reroll_chap.configure(command=lambda: self._generate_full_chapter(False, btn_reroll_chap))

        def add_core_field(label_text, key, uid, show_ai=False):
            hdr = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
            hdr.pack(fill="x", padx=10, pady=(10, 2))
            
            lbl = ctk.CTkLabel(hdr, text=label_text, font=("Arial", 14, "bold"))
            lbl.pack(side="left")
            
            var = ctk.StringVar(value=chap.get(key, ""))
            entry = ctk.CTkEntry(self.editor_frame, textvariable=var, font=("Arial", 14))
            entry.pack(fill="x", padx=10)
            self.chapter_fields[key] = var
            
            if show_ai:
                btn_help = ctk.CTkButton(hdr, text="💡", width=24, height=20, font=("Segoe UI Emoji", 12), fg_color="#FBC02D", hover_color="#F57F17", text_color="black")
                btn_help.pack(side="right", padx=(2, 0))
                
                btn_inspire = ctk.CTkButton(hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
                btn_inspire.pack(side="right", padx=2)
                
                btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
                btn_reroll.pack(side="right", padx=2)
                
                btn_reroll.configure(command=lambda k=key, w=var, btn=btn_reroll: self._generate_chapter_field(k, w, btn, False))
                btn_inspire.configure(command=lambda k=key, w=var, btn=btn_inspire: self._generate_chapter_field(k, w, btn, True))
                
                parent_tab = self.master.master
                if hasattr(parent_tab, 'codex_tab'):
                    btn_help.configure(command=lambda u=uid, w=var, t=label_text: parent_tab.codex_tab._show_field_guide(u, w, t))

        # Core Chapter Definitions
        add_core_field("Chapter Title:", "title", "CHAP_TITLE", show_ai=True)
        add_core_field("Base Setting (Fallback location):", "setting", "CHAP_SETTING", show_ai=True)
        add_core_field("Base POV (Fallback character):", "pov", "CHAP_POV", show_ai=False)
        add_core_field("Time Jump (e.g., 'Two days later...'):", "time", "CHAP_TIME", show_ai=True)
        
        # --- THE QUEST TRACKER (Objectives Array) ---
        ctk.CTkLabel(self.editor_frame, text="Quest Tracker (Micro-Objectives)", font=("Arial", 16, "bold"), text_color="#FFCA28").pack(anchor="w", padx=10, pady=(25, 5))
        ctk.CTkLabel(self.editor_frame, text="The engine automatically tracks your progress and reveals these one at a time to the AI.", font=("Arial", 12, "italic"), text_color="gray").pack(anchor="w", padx=10, pady=(0, 10))

        self.obj_container = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        self.obj_container.pack(fill="x", padx=10)

        objectives = chap.get("objectives", [])
        for i, obj in enumerate(objectives):
            self._add_objective_card(i, obj)

        def add_blank_objective():
            self._save_chapter(memory_only=True)
            self.engine.setup_data["plot_outline"][idx].setdefault("objectives", []).append({
                "goal": "New Objective",
                "obstacles": "None",
                "setting": "",
                "pov": "",
                "status": "LOCKED"
            })
            self._render_editor()

        ctk.CTkButton(self.editor_frame, text="+ Add Objective", fg_color="#4A4A4A", command=add_blank_objective).pack(pady=(10, 20))
        ctk.CTkButton(self.editor_frame, text="Save Chapter Outline", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=self._save_chapter).pack(pady=(10, 40))

    def _move_objective_up(self, obj_idx):
        """Swaps an objective with the one above it, preserving unsaved typing."""
        if obj_idx > 0:
            self._save_chapter(memory_only=True)
            chap_idx = self.selected_idx.get()
            objs = self.engine.setup_data["plot_outline"][chap_idx]["objectives"]
            objs[obj_idx], objs[obj_idx-1] = objs[obj_idx-1], objs[obj_idx]
            self._render_editor()

    def _move_objective_down(self, obj_idx):
        """Swaps an objective with the one below it, preserving unsaved typing."""
        self._save_chapter(memory_only=True)
        chap_idx = self.selected_idx.get()
        objs = self.engine.setup_data["plot_outline"][chap_idx]["objectives"]
        if obj_idx < len(objs) - 1:
            objs[obj_idx], objs[obj_idx+1] = objs[obj_idx+1], objs[obj_idx]
            self._render_editor()

    def _add_objective_card(self, list_idx, obj_data):
        """Draws a single objective block with overrides and status dropdown."""
        card_num = len(self.objective_ui_refs) + 1
        card = ctk.CTkFrame(self.obj_container, fg_color="#2B2B2B", corner_radius=8)
        card.pack(fill="x", pady=(0, 15))

        # Header
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(hdr, text=f"Step {card_num}", font=("Arial", 14, "bold"), text_color="#00ACC1").pack(side="left")

        btn_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_frame.pack(side="right")

        def delete_obj(c_idx=list_idx):
            if messagebox.askyesno("Delete", "Remove this objective?"):
                self._save_chapter(memory_only=True)
                outline = self.engine.setup_data["plot_outline"]
                outline[self.selected_idx.get()]["objectives"].pop(c_idx)
                self._render_editor()

        ctk.CTkButton(btn_frame, text="↑", width=24, height=24, command=lambda c_idx=list_idx: self._move_objective_up(c_idx)).pack(side="left", padx=1)
        ctk.CTkButton(btn_frame, text="↓", width=24, height=24, command=lambda c_idx=list_idx: self._move_objective_down(c_idx)).pack(side="left", padx=1)
        ctk.CTkButton(btn_frame, text="X", width=24, height=24, fg_color="#B71C1C", hover_color="#7F0000", command=delete_obj).pack(side="left", padx=(5, 0))

        # Goal
        ctk.CTkLabel(card, text="Goal (Actionable):", font=("Arial", 12, "bold")).pack(anchor="w", padx=10, pady=(5,0))
        t_goal = ctk.CTkTextbox(card, height=60, wrap="word", font=("Arial", 13))
        t_goal.insert("1.0", obj_data.get("goal", ""))
        t_goal.pack(fill="x", padx=10, pady=(0, 5))

        # Obstacles
        ctk.CTkLabel(card, text="Obstacles / Threats:", font=("Arial", 12, "bold")).pack(anchor="w", padx=10)
        t_obs = ctk.CTkTextbox(card, height=60, wrap="word", font=("Arial", 13))
        t_obs.insert("1.0", obj_data.get("obstacles", ""))
        t_obs.pack(fill="x", padx=10, pady=(0, 5))

        # Overrides & Status
        ov_frame = ctk.CTkFrame(card, fg_color="transparent")
        ov_frame.pack(fill="x", padx=10, pady=(5, 15))

        ctk.CTkLabel(ov_frame, text="Setting Override:", font=("Arial", 12)).pack(side="left")
        e_set = ctk.CTkEntry(ov_frame, font=("Arial", 12), width=180, placeholder_text="(Optional)")
        e_set.insert(0, obj_data.get("setting", ""))
        e_set.pack(side="left", padx=(5, 15))

        ctk.CTkLabel(ov_frame, text="POV Override:", font=("Arial", 12)).pack(side="left")
        e_pov = ctk.CTkEntry(ov_frame, font=("Arial", 12), width=120, placeholder_text="(Optional)")
        e_pov.insert(0, obj_data.get("pov", ""))
        e_pov.pack(side="left", padx=(5, 15))
        
        # State Drodown (Director Manual Control)
        ctk.CTkLabel(ov_frame, text="Status:", font=("Arial", 12, "bold"), text_color="#FF9800").pack(side="left")
        c_status = ctk.CTkOptionMenu(ov_frame, values=["ACTIVE", "LOCKED", "COMPLETED"], width=110, fg_color="#F57C00")
        c_status.set(obj_data.get("status", "LOCKED"))
        c_status.pack(side="left", padx=(5, 0))
        Tooltip(c_status, "Use this to manually advance a quest if the AI gets stuck.")

        self.objective_ui_refs.append({
            "goal": t_goal,
            "obstacles": t_obs,
            "setting": e_set,
            "pov": e_pov,
            "status_widget": c_status
        })

    def _generate_full_chapter(self, is_inspire, button):
        """Generates the entire chapter contextually. Auto-migrates the result to array format if the LLM hallucinates strings."""
        idx = self.selected_idx.get()
        shorthand = None
        
        if is_inspire:
            msg = "Enter a prompt for this chapter:"
            if idx == 0:
                msg = "Enter a prompt for the FIRST chapter (Mandatory):"
            else:
                msg = "Enter a prompt for this chapter (Leave blank to auto-continue the plot):"
                
            dialog = ctk.CTkInputDialog(text=msg, title="Inspire Chapter")
            shorthand = dialog.get_input()
            if shorthand is None: return 
            if idx == 0 and not shorthand.strip():
                messagebox.showwarning("Missing Input", "A prompt is strictly required to inspire the first chapter.")
                return

        self.winfo_toplevel().configure(cursor="watch")
        orig_text = button.cget("text")
        button.configure(state="disabled", text="Generating...")
        self._save_chapter(memory_only=True)
        
        outline = self.engine.setup_data.get("plot_outline", [])
        prev_chap = outline[idx - 1] if idx > 0 else None
        
        def worker():
            from api import TomeWeaverAPI
            success, result = TomeWeaverAPI.generate_chapter_data(self.engine.setup_data, prev_chap, shorthand)
            
            def update_ui():
                self.winfo_toplevel().configure(cursor="")
                button.configure(state="normal", text=orig_text)
                
                if success and isinstance(result, dict):
                    # Failsafe: If the AI output the old flat string schema, migrate it safely before injecting
                    if "goal" in result and "objectives" not in result:
                        result["objectives"] = [{
                            "goal": result.pop("goal"),
                            "obstacles": result.pop("obstacles", "None"),
                            "setting": "", "pov": "", "status": "ACTIVE" if idx == 0 else "LOCKED"
                        }]
                        
                    # Push the new data to memory and redraw the entire right pane
                    outline[idx].update(result)
                    self._render_editor()
                else:
                    messagebox.showerror("Generation Error", str(result))
                    
            self.after(0, update_ui)
            
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _generate_chapter_field(self, field_key, widget, button, is_inspire):
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
        
        self._save_chapter(memory_only=True)
        
        def worker():
            from api import TomeWeaverAPI
            prompt_field = f"chapter {field_key}"
            success, result = TomeWeaverAPI.generate_field_data(self.engine.setup_data, prompt_field, shorthand)
            
            def update_ui():
                self.winfo_toplevel().configure(cursor="")
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

    def _save_chapter(self, memory_only=False):
        """Extracts data from UI fields and writes it to the active memory array."""
        idx = self.selected_idx.get()
        outline = self.engine.setup_data.get("plot_outline", [])
        if idx < 0 or idx >= len(outline): return

        # Save Base Fields
        for key, widget in self.chapter_fields.items():
            if isinstance(widget, ctk.StringVar):
                outline[idx][key] = widget.get().strip()
            else:
                outline[idx][key] = widget.get("1.0", "end").strip()

        # Save Objectives Array
        new_objs = []
        for obj_refs in self.objective_ui_refs:
            new_objs.append({
                "goal": obj_refs["goal"].get("1.0", "end").strip(),
                "obstacles": obj_refs["obstacles"].get("1.0", "end").strip(),
                "setting": obj_refs["setting"].get().strip(),
                "pov": obj_refs["pov"].get().strip(),
                "status": obj_refs["status_widget"].get()
            })
            
        outline[idx]["objectives"] = new_objs

        if not memory_only:
            from config import save_json_atomically
            setup_file = self.engine.adv_dir / "setup.json"
            save_json_atomically(self.engine.setup_data, setup_file)
            
            messagebox.showinfo("Saved", "Chapter outline updated successfully.")
            self._refresh_list()