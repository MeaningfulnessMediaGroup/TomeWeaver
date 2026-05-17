import json
import customtkinter as ctk
from tkinter import messagebox

class ChapterTab(ctk.CTkFrame):
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
        """Clears and rebuilds the chapter list."""
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

        # Auto-select the first item if nothing is selected
        if self.selected_idx.get() < 0 or self.selected_idx.get() >= len(outline):
            self.selected_idx.set(0)
        
        self._render_editor()

    def _move_up(self, idx):
        if idx > 0:
            outline = self.engine.setup_data["plot_outline"]
            outline[idx], outline[idx-1] = outline[idx-1], outline[idx]
            self.selected_idx.set(idx-1)
            self._write_to_disk()
            self._refresh_list()

    def _move_down(self, idx):
        outline = self.engine.setup_data["plot_outline"]
        if idx < len(outline) - 1:
            outline[idx], outline[idx+1] = outline[idx+1], outline[idx]
            self.selected_idx.set(idx+1)
            self._write_to_disk()
            self._refresh_list()

    def _delete_chapter(self, idx):
        outline = self.engine.setup_data["plot_outline"]
        if len(outline) <= 1:
            messagebox.showerror("Error", "Campaigns must have at least one chapter.")
            return
        if messagebox.askyesno("Delete", "Are you sure you want to delete this chapter?"):
            outline.pop(idx)
            self._write_to_disk()
            self._refresh_list()

    def _add_chapter(self):
        outline = self.engine.setup_data.setdefault("plot_outline", [])
        outline.append({
            "title": f"Chapter {len(outline)+1}",
            "setting": "", "pov": "", "time": "",
            "goal": "New Goal", "obstacles": "None"
        })
        self.selected_idx.set(len(outline)-1)
        self._write_to_disk()
        self._refresh_list()

    # ---------------------------------------------------------
    # RIGHT PANE: FORM EDITOR
    # ---------------------------------------------------------

    def _clear_editor(self):
        for w in list(self.editor_frame.winfo_children()):
            w.destroy()
        self.fields.clear()

    def _render_editor(self):
        self._clear_editor()
        idx = self.selected_idx.get()
        outline = self.engine.setup_data.get("plot_outline", [])
        if idx < 0 or idx >= len(outline): return

        chap = outline[idx]

        ctk.CTkLabel(self.editor_frame, text=f"Editing Chapter {idx+1}", font=("Arial", 18, "bold"), text_color="#4CAF50").pack(anchor="w", padx=10, pady=(5, 15))

        def add_entry(label_text, key):
            ctk.CTkLabel(self.editor_frame, text=label_text, font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
            var = ctk.StringVar(value=chap.get(key, ""))
            ctk.CTkEntry(self.editor_frame, textvariable=var, font=("Arial", 14)).pack(fill="x", padx=10)
            self.fields[key] = var

        def add_textbox(label_text, key):
            ctk.CTkLabel(self.editor_frame, text=label_text, font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
            box = ctk.CTkTextbox(self.editor_frame, height=100, wrap="word", font=("Arial", 14))
            box.insert("1.0", chap.get(key, ""))
            box.pack(fill="x", padx=10)
            self.fields[key] = box

        add_entry("Chapter Title:", "title")
        add_entry("Setting Override (Leave blank to keep current):", "setting")
        add_entry("POV Override (Leave blank to keep current):", "pov")
        add_entry("Time Jump (e.g., 'Two days later...'):", "time")
        add_textbox("Chapter Goal (Required):", "goal")
        add_textbox("Obstacles (Required):", "obstacles")

        ctk.CTkButton(self.editor_frame, text="Save Chapter", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=self._save_chapter).pack(pady=30)

    def _save_chapter(self):
        idx = self.selected_idx.get()
        outline = self.engine.setup_data.get("plot_outline", [])
        if idx < 0 or idx >= len(outline): return

        for key, widget in self.fields.items():
            if isinstance(widget, ctk.StringVar):
                outline[idx][key] = widget.get().strip()
            else:
                outline[idx][key] = widget.get("1.0", "end").strip()

        self._write_to_disk()
        messagebox.showinfo("Saved", "Chapter outline updated successfully.")
        self._refresh_list() 

    def _write_to_disk(self):
        setup_file = self.engine.adv_dir / "setup.json"
        with open(setup_file, "w", encoding="utf-8") as f:
            json.dump(self.engine.setup_data, f, indent=4)