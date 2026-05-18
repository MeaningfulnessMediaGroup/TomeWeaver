"""
    TomeWeaver: Main Dashboard UI
    -----------------------------
    Serves as the primary entry point and library manager for the application.
    Handles searching, filtering, and paginating available story cartridges.
    Uses asynchronous threading to load stories from disk without freezing the UI.
"""
import math
import threading
import customtkinter as ctk
from tkinter import messagebox, filedialog
from api import TomeWeaverAPI
from ui.tooltip import Tooltip


class DashboardFrame(ctk.CTkFrame):

    """
    Main Dashboard UI
    """
    def __init__(self, parent, app_controller):
        super().__init__(parent, fg_color="transparent")
        self.app = app_controller

        # --- STATE VARIABLES ---
        self.all_stories = []          # The master list of all metadata dictionaries loaded from disk
        self.filtered_stories = []     # The subset of stories currently matching the search/filter criteria
        self.current_page = 1
        self.items_per_page = 10
        self.is_loading = False        # Mutex flag to prevent overlapping load requests

        # --- TOP HEADER BAR ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 5))
        
        ctk.CTkLabel(header, text="TomeWeaver Library", font=("Georgia", 28, "bold")).pack(side="left")
        
        btn_new = ctk.CTkButton(header, text="+ Create New Story", fg_color="#2E7D32", hover_color="#1B5E20", command=self.show_create_dialog)
        btn_new.pack(side="right", padx=(10, 0))
        Tooltip(btn_new, "Initialize a new Sandbox or Campaign adventure.")
        
        btn_import = ctk.CTkButton(header, text="Import .zip", fg_color="#4A4A4A", hover_color="#333333", command=self.import_zip)
        btn_import.pack(side="right", padx=10)
        Tooltip(btn_import, "Load an adventure from a shared .zip cartridge.")
        
        btn_settings = ctk.CTkButton(header, text="⚙ Settings", width=100, fg_color="#1F6AA5", hover_color="#144870", command=self.show_global_settings)
        btn_settings.pack(side="right", padx=(0, 10))
        Tooltip(btn_settings, "Configure global AI API keys, limits, and engine rules.")

        # --- SEARCH & FILTER BAR ---
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(5, 10))
        
        # --- Group 1: SEARCH ACTION (Left Aligned) ---
        search_left_group = ctk.CTkFrame(search_frame, fg_color="transparent")
        search_left_group.pack(side="left")

        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(search_left_group, textvariable=self.search_var, placeholder_text="Search by keywords...", font=("Arial", 14), width=250)
        search_entry.pack(side="left")
        search_entry.bind("<Return>", lambda e: self.apply_search())
        
        ctk.CTkButton(search_left_group, text="Search", width=70, command=self.apply_search).pack(side="left", padx=10)
        ctk.CTkButton(search_left_group, text="Clear", width=70, fg_color="#4A4A4A", command=self.clear_search).pack(side="left")

        # --- Group 2: VIEW PREFERENCES (Right Aligned) ---
        search_right_group = ctk.CTkFrame(search_frame, fg_color="transparent")
        search_right_group.pack(side="right")

        # Status Filter
        ctk.CTkLabel(search_right_group, text="Status:", font=("Arial", 12)).pack(side="left", padx=(10, 5))
        self.status_var = ctk.StringVar(value="All")
        status_menu = ctk.CTkOptionMenu(
            search_right_group, variable=self.status_var, 
            values=["All", "Not Started", "In Progress", "Complete"], 
            width=110, command=lambda _: self.apply_search()
        )
        status_menu.pack(side="left")

        # Sort Dropdown
        ctk.CTkLabel(search_right_group, text="Sort:", font=("Arial", 12)).pack(side="left", padx=(10, 5))
        self.sort_var = ctk.StringVar(value="Title")
        sort_menu = ctk.CTkOptionMenu(
            search_right_group, variable=self.sort_var,
            values=["Title", "Author", "Date", "Status", "Turns"],
            width=90, command=lambda _: self.apply_search()
        )
        sort_menu.pack(side="left")

        # Order Toggle
        self.asc_var = ctk.BooleanVar(value=True)
        self.btn_order = ctk.CTkButton(
            search_right_group, text="↑ Asc", width=60, 
            fg_color="#4A4A4A", hover_color="#333333",
            command=self.toggle_order
        )
        self.btn_order.pack(side="left", padx=(5, 0))

        # --- STORY GRID (SCROLLABLE) ---
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20, pady=5)

        # --- PAGINATION FOOTER ---
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=10)

        # Items per page dropdown
        per_page_frame = ctk.CTkFrame(footer, fg_color="transparent")
        per_page_frame.pack(side="left")
        ctk.CTkLabel(per_page_frame, text="Show:", font=("Arial", 12)).pack(side="left", padx=(0, 5))
        
        self.per_page_var = ctk.StringVar(value="10")
        per_page_menu = ctk.CTkOptionMenu(
            per_page_frame, variable=self.per_page_var, values=["10", "20", "50", "100"], width=70,
            command=self.change_items_per_page
        )
        per_page_menu.pack(side="left")

        # Page Controls
        page_ctrl_frame = ctk.CTkFrame(footer, fg_color="transparent")
        page_ctrl_frame.pack(side="right")

        self.btn_first = ctk.CTkButton(page_ctrl_frame, text="<<", width=40, fg_color="#4A4A4A", command=lambda: self.change_page(exact=1))
        self.btn_first.pack(side="left", padx=2)
        
        self.btn_prev = ctk.CTkButton(page_ctrl_frame, text="<", width=40, fg_color="#4A4A4A", command=lambda: self.change_page(delta=-1))
        self.btn_prev.pack(side="left", padx=(2, 15))
        
        self.lbl_page = ctk.CTkLabel(page_ctrl_frame, text="Page 1 of 1", font=("Arial", 12, "bold"))
        self.lbl_page.pack(side="left", padx=5)
        
        self.btn_next = ctk.CTkButton(page_ctrl_frame, text=">", width=40, fg_color="#4A4A4A", command=lambda: self.change_page(delta=1))
        self.btn_next.pack(side="left", padx=(15, 2))
        
        self.btn_last = ctk.CTkButton(page_ctrl_frame, text=">>", width=40, fg_color="#4A4A4A", command=lambda: self.change_page(exact=-1))
        self.btn_last.pack(side="left", padx=2)

        # Load initial data
        self.load_data()


    # ---------------------------------------------------------
    # DATA AND PAGINATION LOGIC
    # ---------------------------------------------------------

    def load_data(self):
        """Asynchronously loads story data from disk to prevent UI freezes."""
        if self.is_loading: return
        self.is_loading = True
        
        # Show loading indicator
        for widget in self.scroll.winfo_children(): widget.destroy()
        self.lbl_loading = ctk.CTkLabel(self.scroll, text="Reading library from disk... please wait.", font=("Arial", 16, "italic"), text_color="gray")
        self.lbl_loading.pack(pady=50)

        # Disable pagination while loading
        self.btn_first.configure(state="disabled")
        self.btn_prev.configure(state="disabled")
        self.btn_next.configure(state="disabled")
        self.btn_last.configure(state="disabled")

        # Spawn background thread to read files via the Autonomous Index in api.py
        def worker():
            data = TomeWeaverAPI.get_available_stories()
            # Push the data back to the main GUI thread safely using `after`
            self.after(0, lambda: self._on_data_loaded(data))
            
        threading.Thread(target=worker, daemon=True).start()

    def _on_data_loaded(self, data):
        """Callback executed on the main thread when file reading is complete."""
        self.all_stories = data
        self.is_loading = False
        if hasattr(self, 'lbl_loading'): self.lbl_loading.destroy()
        self.apply_search() 

    def apply_search(self):
        """
        Filters and Sorts the stories based on UI selections.
        Utilizes the 'search_blob' created by the API for deep keyword matching across lore and titles.
        """
        query = self.search_var.get().strip().lower()
        status_filter = self.status_var.get()
        
        # --- 1. FILTERING ---
        temp_list = []
        for s in self.all_stories:
            # Match against the pre-compiled hidden search string
            if query and query not in s.get('search_blob', s['title'].lower()): continue
            
            s_status = s.get('status', 'Unknown')
            if status_filter == "Not Started" and s_status != "New": continue
            if status_filter == "In Progress" and s_status != "In Progress": continue
            if status_filter == "Complete" and s_status not in ["Victory", "Game Over"]: continue
            temp_list.append(s)

        # --- 2. SORTING ---
        sort_key = self.sort_var.get().lower()
        is_asc = self.asc_var.get()
        
        # Map UI labels to JSON dictionary keys
        key_map = {
            "title": "title",
            "author": "author",
            "date": "creation_date",
            "status": "status",
            "turns": "turns"
        }
        actual_key = key_map.get(sort_key, "title")

        def sort_logic(item):
            val = item.get(actual_key, "")
            # Ensure "Unknown" or None values don't crash comparison algorithms
            if val is None: return ""
            if isinstance(val, str): return val.lower()
            return val

        temp_list.sort(key=sort_logic, reverse=not is_asc)

        self.filtered_stories = temp_list
        self.current_page = 1
        self.render_page()

    def toggle_order(self):
        """Swaps between Ascending and Descending order."""
        new_state = not self.asc_var.get()
        self.asc_var.set(new_state)
        self.btn_order.configure(text="↑ Asc" if new_state else "↓ Desc")
        self.apply_search()

    def clear_search(self):
        """Resets all search fields to their default states and re-renders the list."""
        self.search_var.set("")
        self.status_var.set("All")
        self.sort_var.set("Title") # Reset Sort
        self.asc_var.set(True)     # Reset Order
        self.btn_order.configure(text="↑ Asc")
        self.apply_search()

    def change_items_per_page(self, new_val):
        self.items_per_page = int(new_val)
        self.current_page = 1
        self.render_page()

    def change_page(self, delta=0, exact=None):
        """Handles pagination mathematics and bounds-checking before rendering."""
        total_pages = max(1, math.ceil(len(self.filtered_stories) / self.items_per_page))
        
        if exact is not None:
            self.current_page = total_pages if exact == -1 else exact
        else:
            self.current_page += delta
            
        # Clamp bounds
        if self.current_page < 1: self.current_page = 1
        if self.current_page > total_pages: self.current_page = total_pages
            
        self.render_page()

    def render_page(self):
        """Draws the specific slice of stories for the current page."""
        for widget in self.scroll.winfo_children():
            widget.destroy()

        total_items = len(self.filtered_stories)
        total_pages = max(1, math.ceil(total_items / self.items_per_page))
        
        # Update Pagination UI state
        self.lbl_page.configure(text=f"Page {self.current_page} of {total_pages}")
        self.btn_first.configure(state="normal" if self.current_page > 1 else "disabled")
        self.btn_prev.configure(state="normal" if self.current_page > 1 else "disabled")
        self.btn_next.configure(state="normal" if self.current_page < total_pages else "disabled")
        self.btn_last.configure(state="normal" if self.current_page < total_pages else "disabled")

        if total_items == 0:
            msg = "No stories match your search/filter." if (self.search_var.get() or self.status_var.get() != "All") else "No stories found. Create one to begin!"
            ctk.CTkLabel(self.scroll, text=msg, font=("Arial", 16, "italic"), text_color="gray").pack(pady=50)
            return

        # Slice data to memory-friendly page chunk
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_slice = self.filtered_stories[start_idx:end_idx]

        for story in page_slice:
            self.build_story_card(story)
            
        # Snap scroll view back to the top
        self.scroll._parent_canvas.yview_moveto(0.0)


    # ---------------------------------------------------------
    # UI COMPONENT BUILDERS
    # ---------------------------------------------------------

    def build_story_card(self, story):
        """Renders an individual story summary card for the dashboard list."""
        card = ctk.CTkFrame(self.scroll, corner_radius=8)
        card.pack(fill="x", pady=4, padx=10)

        # Content Container (Left/Center)
        content_frame = ctk.CTkFrame(card, fg_color="transparent")
        content_frame.pack(side="left", fill="both", expand=True, padx=15, pady=8)

        # --- LINE 1: [Badge] Title (Left) | Author • v • Date (Right) ---
        line1 = ctk.CTkFrame(content_frame, fg_color="transparent")
        line1.pack(fill="x")

        # Mode Badge
        mode_color = "#2196F3" if story['mode'] == "sandbox" else "#9C27B0"
        mode_lbl = ctk.CTkLabel(line1, text=story['mode'].upper(), font=("Arial", 10, "bold"), text_color=mode_color)
        mode_lbl.pack(side="left", padx=(0, 10))

        # Title
        title_lbl = ctk.CTkLabel(line1, text=story['title'], font=("Arial", 16, "bold"))
        title_lbl.pack(side="left")

        # Author/Version/Date (Right Aligned)
        auth_text = f"{story.get('author', 'Unknown')} • v{story.get('version', '1.0')} • {story.get('creation_date', '')}"
        auth_lbl = ctk.CTkLabel(line1, text=auth_text, font=("Arial", 11, "italic"), text_color="#A0A0A0")
        auth_lbl.pack(side="right")

        # --- LINE 2: Status • Turns • Location ---
        line2 = ctk.CTkFrame(content_frame, fg_color="transparent")
        line2.pack(fill="x", pady=(2, 0))

        t_count = story.get('turns', 0)
        t_label = "Turn" if t_count == 1 else "Turns"
        t_text = f" • {t_count} {t_label}" if t_count > 0 else ""
        
        meta_text = f"[{story.get('status', 'Unknown')}]{t_text} • {story.get('location', 'Unknown')}"
        ctk.CTkLabel(line2, text=meta_text, font=("Arial", 12), text_color="gray").pack(side="left")

        # --- RIGHT SIDE: ACTION BUTTONS ---
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=15)

        state = "normal" if story['mode'] != "error" else "disabled"
        btn_play = ctk.CTkButton(btn_frame, text="Play", width=80, state=state, command=lambda f=story['folder_name']: self.app.open_workspace(f))
        btn_play.pack(side="left", padx=5)

        # Dropdown options for managing the cartridge
        opt_menu = ctk.CTkOptionMenu(
            btn_frame, 
            values=["Options...", "Restart", "Export to .zip", "Rename", "Delete"],
            width=110,
            command=lambda choice, f=story['folder_name'], t=story['title']: self.handle_card_option(choice, f, t)
        )
        opt_menu.pack(side="left", padx=5)
        opt_menu.set("Options...")


    # ---------------------------------------------------------
    # ACTION HANDLERS
    # ---------------------------------------------------------

    def handle_card_option(self, choice, folder_name, current_title):
        """Routes actions from the 'Options...' dropdown on individual story cards."""
        if choice == "Restart":
            warn_msg = (
                f"Are you sure you want to RESTART '{current_title}'?\n\n"
                "This will permanently DELETE all played turns and choices. "
                "The story will revert to the beginning. This cannot be undone!"
            )
            if messagebox.askyesno("Confirm Restart", warn_msg, icon='warning'):
                success, msg = TomeWeaverAPI.restart_story(folder_name)
                if success: self.load_data() # Refresh turns/status on Dashboard
                else: messagebox.showerror("Restart Failed", msg)

        elif choice == "Export to .zip":
            path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=f"{folder_name}.zip", filetypes=[("ZIP files", "*.zip")])
            if path:
                success, msg = TomeWeaverAPI.export_to_zip(folder_name, path)
                if success: messagebox.showinfo("Export Successful", f"Cartridge saved to:\n{path}")
                else: messagebox.showerror("Export Failed", msg)

        elif choice == "Rename":
            dialog = ctk.CTkInputDialog(text="Enter new title:", title="Rename Story")
            new_title = dialog.get_input()
            if new_title and new_title != current_title:
                success, msg = TomeWeaverAPI.rename_story(folder_name, new_title)
                if success: self.load_data() 
                else: messagebox.showerror("Rename Failed", msg)

        elif choice == "Delete":
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete '{current_title}'?"):
                success, msg = TomeWeaverAPI.delete_story(folder_name)
                if success: self.load_data() 
                else: messagebox.showerror("Delete Failed", msg)

    def import_zip(self):
        """Opens a file dialog to import a shared adventure cartridge."""
        path = filedialog.askopenfilename(filetypes=[("ZIP Cartridges", "*.zip")])
        if path:
            success, msg = TomeWeaverAPI.import_from_zip(path)
            if success:
                messagebox.showinfo("Import Successful", f"Story imported: {msg}")
                self.load_data()
            else:
                messagebox.showerror("Import Failed", msg)

    def show_create_dialog(self):
        """Spawns the modal dialog for initializing a new adventure framework."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Create New Story")
        dialog.geometry("400x360")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Adventure Title:", font=("Arial", 14)).pack(pady=(15, 2))
        title_entry = ctk.CTkEntry(dialog, width=300)
        title_entry.pack(pady=5)
        
        ctk.CTkLabel(dialog, text="Author Name:", font=("Arial", 14)).pack(pady=(10, 2))
        author_entry = ctk.CTkEntry(dialog, width=300, placeholder_text="Anonymous")
        author_entry.pack(pady=5)

        ctk.CTkLabel(dialog, text="Select Mode:", font=("Arial", 14)).pack(pady=(15, 2))
        mode_var = ctk.StringVar(value="sandbox")
        
        radio_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        radio_frame.pack()
        ctk.CTkRadioButton(radio_frame, text="Sandbox (Open-World)", variable=mode_var, value="sandbox").pack(side="left", padx=10)
        ctk.CTkRadioButton(radio_frame, text="Campaign (Plot-Driven)", variable=mode_var, value="campaign").pack(side="left", padx=10)

        def on_create():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("Missing Info", "Please enter a title.")
                return
            success, msg = TomeWeaverAPI.create_story(title, author_entry.get(), mode_var.get())
            if success:
                self.load_data()
                dialog.destroy()
            else:
                messagebox.showerror("Creation Failed", msg)

        ctk.CTkButton(dialog, text="Create", command=on_create).pack(pady=25)
        
        
    def show_global_settings(self):
        """Opens a modal to edit configs/engine_config.json containing global AI and UI behaviors."""
        from config import load_engine_config, ROOT_DIR, ENGINE_CONFIG
        from ui.tooltip import Tooltip
        import json
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Global Engine Settings")
        dialog.geometry("600x750")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Global API & Engine Configuration", font=("Arial", 18, "bold")).pack(pady=(20, 10))
        
        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)

        current_config = load_engine_config()
        fields = {}

        def add_field(label_text, key_name, is_bool=False, is_number=False, tooltip_text=""):
            """Helper closure to procedurally generate settings form rows."""
            val = current_config.get(key_name)
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=5)
            
            lbl = ctk.CTkLabel(row, text=label_text, font=("Arial", 14, "bold"), width=200, anchor="e")
            lbl.pack(side="left", padx=(0, 15))
            if tooltip_text:
                Tooltip(lbl, tooltip_text)
            
            if is_bool:
                var = ctk.BooleanVar(value=bool(val))
                ctk.CTkSwitch(row, text="", variable=var).pack(side="left")
                fields[key_name] = var
            else:
                var = ctk.StringVar(value=str(val) if val is not None else "")
                show_star = "*" if "key" in key_name.lower() else ""
                entry = ctk.CTkEntry(row, textvariable=var, font=("Arial", 14), width=300, show=show_star)
                entry.pack(side="left", expand=True, fill="x")
                fields[key_name] = (var, is_number)

        # Build Fields (Categorized)
        ctk.CTkLabel(scroll, text="--- API Connection ---", text_color="gray").pack(pady=(10, 5))
        
        from config import get_api_profiles, load_api_profile
        profiles = get_api_profiles()
        
        api_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        api_frame.pack(fill="x", pady=5)
        
        lbl_api = ctk.CTkLabel(api_frame, text="Active API Profile:", font=("Arial", 14, "bold"), width=200, anchor="e")
        lbl_api.pack(side="left", padx=(0, 15))
        Tooltip(lbl_api, "Select the cloud or local LLM connection to use for generating stories.")
        
        api_var = ctk.StringVar(value=current_config.get("active_api_profile", "LM_Studio"))
        if api_var.get() not in profiles and profiles: api_var.set(profiles[0])
        
        api_menu = ctk.CTkOptionMenu(api_frame, variable=api_var, values=profiles, width=200)
        api_menu.pack(side="left", padx=(0, 10))
        
        # Pass the active profile string directly to the manager so it opens focused on it
        btn_cfg_api = ctk.CTkButton(api_frame, text="⚙ Configure", width=90, fg_color="#1F6AA5", command=lambda: self.show_api_manager(api_menu, api_var.get()))
        btn_cfg_api.pack(side="left")
        
        ctk.CTkLabel(scroll, text="--- LLM Parameters ---", text_color="gray").pack(pady=(20, 5))
        add_field("Base Temperature:", "temperature_base", is_number=True, tooltip_text="Base creativity (0.0 to 2.0). Lower is more logical, higher is more chaotic.")
        add_field("Context Window (Turns):", "context_window", is_number=True, tooltip_text="How many previous turns the AI remembers. Higher context costs more tokens.")
        
        ctk.CTkLabel(scroll, text="--- Engine Rules ---", text_color="gray").pack(pady=(20, 5))
        add_field("Max Retries (Healer):", "max_retries", is_number=True, tooltip_text="How many times the engine attempts to self-heal broken JSON before giving up.")
        add_field("Enable Auto-Polish:", "auto_polish", is_bool=True, tooltip_text="Automatically runs a second copy-editing pass on every turn for novel-quality prose.")
        add_field("Auto Narrative Bridge:", "auto_narrative_bridge", is_bool=True, tooltip_text="Automatically patches missing prose bridges in the background when opening a story and during normal play.")
        
        ctk.CTkLabel(scroll, text="--- Application UI ---", text_color="gray").pack(pady=(20, 5))
        
        safe_fonts = ["Georgia", "Arial", "Times New Roman", "Courier New", "Consolas", "Trebuchet MS", "Verdana"]
        row_font = ctk.CTkFrame(scroll, fg_color="transparent")
        row_font.pack(fill="x", pady=5)
        lbl_font = ctk.CTkLabel(row_font, text="Story Font Family:", font=("Arial", 14, "bold"), width=200, anchor="e")
        lbl_font.pack(side="left", padx=(0, 15))
        Tooltip(lbl_font, "The font face used for the story timeline and editors.")
        
        # Pull font directly from OptionMenu to prevent StringVar bugs
        font_menu = ctk.CTkOptionMenu(row_font, values=safe_fonts, width=300)
        font_menu.set(current_config.get("prose_font_family", "Georgia"))
        font_menu.pack(side="left", expand=True, fill="x")

        add_field("UI Scaling (e.g., 1.0, 1.25):", "ui_scaling", is_number=True, tooltip_text="Scales the entire application interface for 4K/high-res monitors. Requires restart.")
        add_field("Story Font Size:", "prose_font_size", is_number=True, tooltip_text="The point size of the prose text in the main workspace.")
        ctk.CTkLabel(scroll, text="(Requires application restart to fully apply UI scaling)", font=("Arial", 11, "italic"), text_color="gray").pack()

        ctk.CTkLabel(scroll, text="--- Developer Logging ---", text_color="gray").pack(pady=(20, 5))
        add_field("Enable Session Log:", "logging_enabled", is_bool=True, tooltip_text="Master switch to record all game events and API calls to session_log.txt.")
        add_field("Log Verbose (Prompts):", "log_verbose", is_bool=True, tooltip_text="Includes the full, massive context prompt sent to the LLM in the session log.")
        add_field("Log Raw JSON on Fail:", "log_raw_json_on_failure", is_bool=True, tooltip_text="Logs the exact broken string the AI outputted if it fails to parse.")

        def save_config():
            """Gathers all variables and performs an atomic save to engine_config.json."""
            new_config = {}
            for k, w in fields.items():
                if isinstance(w, ctk.BooleanVar):
                    new_config[k] = w.get()
                else:
                    var, is_num = w
                    val = var.get().strip()
                    if is_num:
                        try: new_config[k] = float(val) if "." in val else int(val)
                        except ValueError: new_config[k] = 0
                    else:
                        new_config[k] = val
            
            new_config["prose_font_family"] = font_menu.get().strip()
            
            # Read the selected API profile and inject its connection details into the engine config
            selected_prof = api_var.get()
            new_config["active_api_profile"] = selected_prof
            prof_data = load_api_profile(selected_prof)
            
            new_config["api_url"] = prof_data.get("api_url", "")
            new_config["api_key"] = prof_data.get("api_key", "")
            new_config["model"] = prof_data.get("model", "")
            new_config["max_query_per_minute"] = prof_data.get("max_query_per_minute", 0)
            new_config["max_tokens"] = prof_data.get("max_tokens", 2000)
            
            try:
                # 1. Save to disk
                config_path = ROOT_DIR / "configs" / "engine_config.json"
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(new_config, f, indent=4)
                    
                # 2. Mutate active memory globally (CRITICAL FIX)
                ENGINE_CONFIG.clear()
                ENGINE_CONFIG.update(new_config)
                    
                messagebox.showinfo("Saved", "Global Engine Settings saved successfully.")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save config: {e}")

        ctk.CTkButton(dialog, text="Save Global Settings", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=save_config).pack(pady=20)
        
    def show_api_manager(self, parent_dropdown, active_profile_name):
        """Opens the Connections Manager to add/edit/delete API profiles."""
        from config import API_CONFIGS_DIR, get_api_profiles, load_api_profile
        from api import sanitize_foldername
        from ui.tooltip import Tooltip
        import json
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("API Connections Manager")
        dialog.geometry("850x550")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # Layout
        left_pane = ctk.CTkScrollableFrame(dialog, width=250)
        left_pane.pack(side="left", fill="y", padx=10, pady=10)

        right_pane = ctk.CTkFrame(dialog)
        right_pane.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # Start with the currently active profile
        api_selection = ctk.StringVar(value=active_profile_name)
        
        url_var = ctk.StringVar()
        key_var = ctk.StringVar()
        mod_var = ctk.StringVar()
        qpm_var = ctk.StringVar()
        tok_var = ctk.StringVar()
        
        def render_editor():
            """Rebuilds the right-hand panel form when a different API profile is selected."""
            for w in right_pane.winfo_children(): w.destroy()
            prof_name = api_selection.get()
            if not prof_name: return
            
            data = load_api_profile(prof_name)
            url_var.set(data.get("api_url", ""))
            key_var.set(data.get("api_key", ""))
            mod_var.set(data.get("model", ""))
            qpm_var.set(str(data.get("max_query_per_minute", 0)))
            tok_var.set(str(data.get("max_tokens", 2000)))
            
            ctk.CTkLabel(right_pane, text=f"Editing Profile: {prof_name}", font=("Arial", 18, "bold")).pack(anchor="w", padx=20, pady=(20, 10))
            
            form = ctk.CTkFrame(right_pane, fg_color="transparent")
            form.pack(fill="both", expand=True, padx=20)
            
            lbl_url = ctk.CTkLabel(form, text="API URL:", font=("Arial", 14, "bold"))
            lbl_url.pack(anchor="w", pady=(10, 2))
            Tooltip(lbl_url, "Endpoint for your LLM (e.g., http://localhost:1234/v1/chat/completions).")
            ctk.CTkEntry(form, textvariable=url_var, font=("Arial", 14)).pack(fill="x")
            
            lbl_key = ctk.CTkLabel(form, text="API Key (Hidden):", font=("Arial", 14, "bold"))
            lbl_key.pack(anchor="w", pady=(10, 2))
            Tooltip(lbl_key, "Your secret API key. Leave blank if using a local provider like LM Studio.")
            ctk.CTkEntry(form, textvariable=key_var, font=("Arial", 14), show="*").pack(fill="x")
            
            lbl_mod = ctk.CTkLabel(form, text="Model ID:", font=("Arial", 14, "bold"))
            lbl_mod.pack(anchor="w", pady=(10, 2))
            Tooltip(lbl_mod, "The exact model identifier (e.g., loaded-model, gpt-4o, claude-3-5-sonnet).")
            ctk.CTkEntry(form, textvariable=mod_var, font=("Arial", 14)).pack(fill="x")
            
            lbl_tok = ctk.CTkLabel(form, text="Max Tokens (Context length per response):", font=("Arial", 14, "bold"))
            lbl_tok.pack(anchor="w", pady=(10, 2))
            Tooltip(lbl_tok, "Maximum length of the AI's generated response per turn.")
            ctk.CTkEntry(form, textvariable=tok_var, font=("Arial", 14)).pack(fill="x")
            
            lbl_qpm = ctk.CTkLabel(form, text="API Queries/Min (Rate Limit, 0=Unlimited):", font=("Arial", 14, "bold"))
            lbl_qpm.pack(anchor="w", pady=(10, 2))
            Tooltip(lbl_qpm, "Rate limit for strict cloud APIs to prevent 429 errors. 0 = Unlimited.")
            ctk.CTkEntry(form, textvariable=qpm_var, font=("Arial", 14)).pack(fill="x")
            
            def save_profile():
                fpath = API_CONFIGS_DIR / f"{prof_name}.json"
                try:
                    qpm = int(qpm_var.get().strip())
                    tok = int(tok_var.get().strip())
                except ValueError:
                    messagebox.showerror("Error", "Max Tokens and Queries/Min must be valid integers.")
                    return
                    
                payload = {
                    "api_url": url_var.get().strip(), 
                    "api_key": key_var.get().strip(), 
                    "model": mod_var.get().strip(),
                    "max_query_per_minute": qpm,
                    "max_tokens": tok
                }
                
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4)
                messagebox.showinfo("Saved", f"Profile '{prof_name}' saved.")
                
            ctk.CTkButton(right_pane, text="Save Profile", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=save_profile).pack(pady=20)

        def add_profile():
            dialog_add = ctk.CTkInputDialog(text="Enter new profile name (e.g., 'Groq', 'TogetherAI'):", title="Add Profile")
            name = dialog_add.get_input()
            if name:
                name = sanitize_foldername(name)
                fpath = API_CONFIGS_DIR / f"{name}.json"
                if not fpath.exists():
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump({"api_url": "", "api_key": "", "model": ""}, f, indent=4)
                    refresh_list()
                    api_selection.set(name)
                    render_editor()

        def delete_profile(name):
            if messagebox.askyesno("Delete", f"Are you sure you want to delete profile '{name}'?"):
                fpath = API_CONFIGS_DIR / f"{name}.json"
                if fpath.exists(): fpath.unlink()
                refresh_list()
                render_editor()

        def refresh_list():
            for w in left_pane.winfo_children(): w.destroy()
            
            ctk.CTkButton(left_pane, text="+ Add Profile", fg_color="#1F6AA5", command=add_profile).pack(fill="x", pady=(0, 15))
            
            profiles = get_api_profiles()
            for p in profiles:
                row = ctk.CTkFrame(left_pane, fg_color="transparent")
                row.pack(fill="x", pady=2)
                
                rb = ctk.CTkRadioButton(row, text=p, variable=api_selection, value=p, command=render_editor)
                rb.pack(side="left", fill="x", expand=True)
                
                btn_del = ctk.CTkButton(row, text="X", width=24, fg_color="#B71C1C", hover_color="#7F0000", command=lambda name=p: delete_profile(name))
                btn_del.pack(side="right")
                
            parent_dropdown.configure(values=profiles)
            if parent_dropdown.get() not in profiles and profiles:
                parent_dropdown.set(profiles[0])

        # 1. Build the list of radio buttons
        refresh_list()
        
        # 2. Force the right-hand panel to render the active selection immediately
        render_editor()