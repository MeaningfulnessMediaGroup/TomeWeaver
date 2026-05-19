"""
    TomeWeaver: Campaign Outline Editor
    -----------------------------------
    A dedicated UI tab for managing Campaign Mode chapters.
    Provides a master-detail interface where users can navigate, reorder,
    add, and modify the goals and constraints of narrative chapters.
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

        self.fields = {} # Holds references to the UI input variables

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
        """Swaps a chapter with the one above it in the plot array."""
        if idx > 0:
            outline = self.engine.setup_data["plot_outline"]
            outline[idx], outline[idx-1] = outline[idx-1], outline[idx]
            self.selected_idx.set(idx-1)
            self._refresh_list()

    def _move_down(self, idx):
        """Swaps a chapter with the one below it in the plot array."""
        outline = self.engine.setup_data["plot_outline"]
        if idx < len(outline) - 1:
            outline[idx], outline[idx+1] = outline[idx+1], outline[idx]
            self.selected_idx.set(idx+1)
            self._refresh_list()

    def _delete_chapter(self, idx):
        """Removes a chapter from the array with safety checks."""
        outline = self.engine.setup_data["plot_outline"]
        if len(outline) <= 1:
            messagebox.showerror("Error", "Campaigns must have at least one chapter.")
            return
        if messagebox.askyesno("Delete", "Are you sure you want to delete this chapter?"):
            outline.pop(idx)
            self._refresh_list()

    def _add_chapter(self):
        """Appends a new blank chapter template to the end of the array."""
        outline = self.engine.setup_data.setdefault("plot_outline", [])
        outline.append({
            "title": f"Chapter {len(outline)+1}",
            "setting": "", "pov": "", "time": "",
            "goal": "New Goal", "obstacles": "None"
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
        self.fields.clear()

    def _render_editor(self):
        """Rebuilds the form fields to match the data of the currently selected chapter."""
        self._clear_editor()
        idx = self.selected_idx.get()
        outline = self.engine.setup_data.get("plot_outline", [])
        if idx < 0 or idx >= len(outline): return

        chap = outline[idx]

        ctk.CTkLabel(self.editor_frame, text=f"Editing Chapter {idx+1}", font=("Arial", 18, "bold"), text_color="#4CAF50").pack(anchor="w", padx=10, pady=(5, 15))

        def add_field(label_text, key, is_multiline=False, show_ai=False):
            hdr = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
            hdr.pack(fill="x", padx=10, pady=(10, 2))
            
            lbl = ctk.CTkLabel(hdr, text=label_text, font=("Arial", 14, "bold"))
            lbl.pack(side="left")
            
            if is_multiline:
                box = ctk.CTkTextbox(self.editor_frame, height=100, wrap="word", font=("Arial", 14))
                box.insert("1.0", chap.get(key, ""))
                box.pack(fill="x", padx=10)
                widget = box
            else:
                var = ctk.StringVar(value=chap.get(key, ""))
                entry = ctk.CTkEntry(self.editor_frame, textvariable=var, font=("Arial", 14))
                entry.pack(fill="x", padx=10)
                widget = var
                
            self.fields[key] = widget
            
            if show_ai:
                btn_inspire = ctk.CTkButton(hdr, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
                btn_inspire.pack(side="right", padx=2)
                Tooltip(btn_inspire, "Expand your shorthand text into a rich description.")
                
                btn_reroll = ctk.CTkButton(hdr, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
                btn_reroll.pack(side="right", padx=2)
                Tooltip(btn_reroll, "Generate a completely new, creative idea for this field.")
                
                btn_reroll.configure(command=lambda k=key, w=widget, btn=btn_reroll: self._generate_chapter_field(k, w, btn, False))
                btn_inspire.configure(command=lambda k=key, w=widget, btn=btn_inspire: self._generate_chapter_field(k, w, btn, True))

        add_field("Chapter Title:", "title", show_ai=True)
        add_field("Setting Override (Leave blank to keep current):", "setting", show_ai=True)
        add_field("POV Override (Leave blank to keep current):", "pov", show_ai=False)
        add_field("Time Jump (e.g., 'Two days later...'):", "time", show_ai=True)
        add_field("Chapter Goal (Required):", "goal", is_multiline=True, show_ai=True)
        add_field("Obstacles (Required):", "obstacles", is_multiline=True, show_ai=True)

        ctk.CTkButton(self.editor_frame, text="Save Chapter", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=self._save_chapter).pack(pady=30)

    def _generate_chapter_field(self, field_key, widget, button, is_inspire):
        """Asynchronously calls the API to generate or expand data for a single Chapter field."""
        shorthand = None
        if is_inspire:
            if isinstance(widget, ctk.StringVar): shorthand = widget.get().strip()
            else: shorthand = widget.get("1.0", "end").strip()
                
            if not shorthand:
                messagebox.showwarning("Missing Input", "Type some shorthand ideas in the box first to inspire the AI!")
                return
                
        orig_text = button.cget("text")
        button.configure(state="disabled", text="...")
        
        # Save memory temporarily so the AI context is perfectly up to date
        self._save_chapter(memory_only=True)
        
        def worker():
            from api import TomeWeaverAPI
            # Prefix the key so the AI prompt understands the context (e.g., "chapter goal")
            prompt_field = f"chapter {field_key}"
            success, result = TomeWeaverAPI.generate_field_data(self.engine.setup_data, prompt_field, shorthand)
            
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

    def _save_chapter(self, memory_only=False):
        """Extracts data from UI fields and writes it to the active memory array."""
        idx = self.selected_idx.get()
        outline = self.engine.setup_data.get("plot_outline", [])
        if idx < 0 or idx >= len(outline): return

        for key, widget in self.fields.items():
            if isinstance(widget, ctk.StringVar):
                outline[idx][key] = widget.get().strip()
            else:
                outline[idx][key] = widget.get("1.0", "end").strip()

        if not memory_only:
            self._write_to_disk()
            messagebox.showinfo("Saved", "Chapter outline updated successfully.")
            self._refresh_list() 

    def _write_to_disk(self):
        """Commits the active memory dict to setup.json."""
        setup_file = self.engine.adv_dir / "setup.json"
        with open(setup_file, "w", encoding="utf-8") as f:
            json.dump(self.engine.setup_data, f, indent=4)