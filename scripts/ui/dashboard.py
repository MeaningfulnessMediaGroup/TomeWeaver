"""
    TomeWeaver: Main Dashboard UI
    -----------------------------
    Serves as the primary entry point and library manager for the application.
    Handles searching, filtering, and paginating available story cartridges.
    Uses asynchronous threading to load stories from disk without freezing the UI.
"""
import math
import threading
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox, filedialog
from api import TomeWeaverAPI
from ui.tooltip import Tooltip


class DashboardFrame(ctk.CTkFrame):

    """
    Main Dashboard UI
    """
    def __init__(self, parent, app_controller, initial_dir=""):
        """Render the story library grid and creation/import actions.

        Args:
            parent: Root app or container frame.
            app_controller: :class:`TomeWeaverApp` for navigation callbacks.
            initial_dir: Optional starting folder for the file browser.
        """
        super().__init__(parent, fg_color="transparent")
        self.app = app_controller

        # --- STATE VARIABLES ---
        self.current_dir = initial_dir # CRITICAL FIX: Define this first!
        self.all_stories = []          # The master list of all metadata dictionaries loaded from disk
        self.filtered_stories = []     # The subset of stories currently matching the search/filter criteria
        self.current_page = 1
        self.items_per_page = 10
        self.is_loading = False        # Mutex flag to prevent overlapping load requests

        # --- TOP HEADER BAR ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 5))
        
        ctk.CTkLabel(header, text="TomeWeaver Library", font=("Georgia", 28, "bold")).pack(side="left")
        
        # New Feature: The Split Dropdown Button
        self.new_story_var = ctk.StringVar(value="+ Create New Story")
        
        from config import find_universe_root
        from api import get_adv_dir
        is_univ = find_universe_root(get_adv_dir() / self.current_dir) is not None
        self.new_story_var.set("+ Create Thread" if is_univ else "+ Create New Story")
        
        menu_values = ["Manual Setup...", "Generate via AI...", "Guided Wizard..."]
        if not is_univ:
            menu_values.append("Create Universe...")
            
        if not (get_adv_dir() / "Samples").exists() and self.current_dir == "":
            menu_values.append("Download Samples...")

        self.btn_new = ctk.CTkOptionMenu(
            header, 
            variable=self.new_story_var, 
            values=menu_values, 
            fg_color="#2E7D32", 
            button_color="#1B5E20", 
            button_hover_color="#0D3B13",
            command=self._handle_create_menu
        )
        self.btn_new.pack(side="right", padx=(10, 0))
        Tooltip(self.btn_new, "Initialize a new Sandbox or Campaign adventure.")
        
        btn_import = ctk.CTkButton(header, text="Import .zip", fg_color="#4A4A4A", hover_color="#333333", command=self.import_zip)
        btn_import.pack(side="right", padx=10)
        Tooltip(btn_import, "Load an adventure from a shared .zip cartridge.")
        
        btn_settings = ctk.CTkButton(header, text="⚙ Settings", width=100, fg_color="#1F6AA5", hover_color="#144870", command=self.show_global_settings)
        btn_settings.pack(side="right", padx=(0, 10))
        Tooltip(btn_settings, "Configure global AI API keys, limits, and engine rules.")

        # --- SEARCH & FILTER BAR ---
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))
        
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

        self.asc_var = ctk.BooleanVar(value=True)
        self.btn_order = ctk.CTkButton(search_right_group, text="↑ Asc", width=60, fg_color="#4A4A4A", hover_color="#333333", command=self.toggle_order)
        self.btn_order.pack(side="left", padx=(5, 0))

        # --- BREADCRUMB BAR (FOLDER NAVIGATION) ---
        self.current_dir = initial_dir
        self.breadcrumb_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.breadcrumb_frame.pack(fill="x", padx=20, pady=(0, 5))
        self.update_breadcrumbs()

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
        ctk.CTkOptionMenu(per_page_frame, variable=self.per_page_var, values=["10", "20", "50", "100"], width=70, command=self.change_items_per_page).pack(side="left")

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

        # --- UI VIRTUALIZATION POOL ---
        self.card_pool = []
        self.lbl_loading = ctk.CTkLabel(self.scroll, text="Reading library from disk... please wait.", font=("Arial", 16, "italic"), text_color="gray")
        self.lbl_empty = ctk.CTkLabel(self.scroll, text="", font=("Arial", 16, "italic"), text_color="gray")
        
        # Permanent reference to the welcome UI so it can be cleared
        self.welcome_frame = None

        # Load initial data
        self.load_data()


    def change_dir(self, new_dir):
        """Updates the active path and forces a clean refresh."""
        self.current_dir = new_dir
        self.search_var.set("") 
        self.update_breadcrumbs()
        
        # Dynamic Menu Update (Check if we stepped inside a Universe)
        from config import find_universe_root
        from api import get_adv_dir
        is_univ = find_universe_root(get_adv_dir() / self.current_dir) is not None
        
        menu_values = ["Manual Setup...", "Generate via AI...", "Guided Wizard..."]
        if not is_univ:
            menu_values.append("Create Universe...")
            
        if not (get_adv_dir() / "Samples").exists() and self.current_dir == "":
            menu_values.append("Download Samples...")
            
        self.btn_new.configure(values=menu_values)
        self.new_story_var.set("+ Create Thread" if is_univ else "+ Create New Story")
        
        self.apply_search()


    def update_breadcrumbs(self):
        """Draws the clickable folder path hierarchy."""
        for w in self.breadcrumb_frame.winfo_children(): w.destroy()
        
        ctk.CTkButton(self.breadcrumb_frame, text="🏠 Home", width=50, fg_color="transparent", 
                      hover_color="#333333", command=lambda: self.change_dir("")).pack(side="left")
                      
        if self.current_dir:
            parts = self.current_dir.split('/')
            accumulated = ""
            for p in parts:
                ctk.CTkLabel(self.breadcrumb_frame, text=" ❯ ", text_color="gray", font=("Arial", 12, "bold")).pack(side="left")
                accumulated = f"{accumulated}/{p}" if accumulated else p
                ctk.CTkButton(self.breadcrumb_frame, text=p, width=50, fg_color="transparent", 
                              hover_color="#333333", command=lambda path=accumulated: self.change_dir(path)).pack(side="left")
                              
        # Tools placed on the far right
        btn_folder = ctk.CTkButton(self.breadcrumb_frame, text="+ New Folder", width=90, fg_color="#4A4A4A", hover_color="#333333", command=self.show_create_folder_dialog)
        btn_folder.pack(side="right")
        
        btn_refresh = ctk.CTkButton(self.breadcrumb_frame, text="⟳ Refresh", width=70, fg_color="transparent", hover_color="#333333", text_color="#00BCD4", command=self.force_index_refresh)
        btn_refresh.pack(side="right", padx=(0, 10))
        from ui.tooltip import Tooltip
        Tooltip(btn_refresh, "Clears the cache and forces a deep read of the hard drive.")
                              
    # ---------------------------------------------------------
    # DATA AND PAGINATION LOGIC
    # ---------------------------------------------------------

    def load_data(self):
        """Asynchronously loads story data from disk to prevent UI freezes."""
        if getattr(self, 'is_loading', False): return
        self.is_loading = True
        
        # Show loading indicator (Fast Pack/Unpack instead of Destroy)
        for card in self.card_pool: card["frame"].pack_forget()
        self.lbl_empty.pack_forget()
        self.lbl_loading.pack(pady=50)

        # Disable pagination while loading
        self.btn_first.configure(state="disabled")
        self.btn_prev.configure(state="disabled")
        self.btn_next.configure(state="disabled")
        self.btn_last.configure(state="disabled")

        def worker():
            try:
                data = TomeWeaverAPI.get_available_stories()
            except Exception as e:
                print(f"Index Error: {e}")
                data = getattr(self, 'all_stories', []) 
            finally:
                self.after(0, lambda: self._on_data_loaded(data))
            
        threading.Thread(target=worker, daemon=True).start()
        
    def force_index_refresh(self):
        """Nukes the index.json cache file and triggers a deep reload of the OS."""
        if getattr(self, 'is_loading', False): return
        
        from api import get_index_file
        if get_index_file().exists():
            try:
                get_index_file().unlink()
            except Exception:
                pass # If OS locked, the indexer will just overwrite it anyway
                
        self.load_data()
        
    def _on_data_loaded(self, data):
        """Callback executed on the main thread when file reading is complete."""
        self.all_stories = data
        self.is_loading = False
        self.lbl_loading.pack_forget()
        self.apply_search()

    def apply_search(self, reset_page=True):
        """
        Filters, Sorts, and Organizes the stories. 
        Also scans the active directory to detect and display empty physical folders.
        """
        import os
        query = self.search_var.get().strip().lower()
        status_filter = self.status_var.get()
        
        temp_list = []
        folders_found = {} # Tracks sub-folders
        
        # Build a set of all explicit folder paths (Universes and Stories) to prevent Ghost Duplicates
        known_entities = {s['folder_name'] for s in self.all_stories}

        # --- 1. GATHER PHYSICAL FOLDERS ---
        # Discover physical directories in the current path so empty folders show up
        if not query:
            from api import get_adv_dir
            active_os_path = get_adv_dir() / self.current_dir
            if active_os_path.exists():
                for item in active_os_path.iterdir():
                    # Only add if it's NOT a story cartridge, NOT a Universe root, AND not a hidden file
                    if item.is_dir() and not (item / "setup.json").exists() and not (item / "master_setup.json").exists() and not item.name.startswith("."):
                        f_path = item.relative_to(get_adv_dir()).as_posix()
                        folders_found[f_path] = 0

        # --- 2. GATHER STORIES & TALLY COUNTS ---
        folder_children = {} # Tracks unique immediate children: f_path -> set()
        universe_counts = {} # Tracks deep counts for Universes: u_path -> int
        
        for s in self.all_stories:
            if query and query not in s.get('search_blob', s['title'].lower()): continue
            
            s_status = s.get('status', 'Unknown')
            if status_filter == "Not Started" and s_status != "Not Started": continue
            if status_filter == "In Progress" and s_status != "In Progress": continue
            if status_filter == "Complete" and s_status not in ["Victory", "Game Over"]: continue
            
            # Global Search Flattening: Ignore folders and show all hits directly
            if query:
                temp_list.append(s)
                continue
                
            # Path parsing logic
            s_path = s['folder_name']
            s_dir = os.path.dirname(s_path).replace('\\', '/')
            
            if s_dir == self.current_dir:
                # The entity lives exactly in the current directory
                temp_list.append(s)
            else:
                # Does this entity live deeper inside the current directory?
                prefix = self.current_dir + "/" if self.current_dir else ""
                if s_path.startswith(prefix):
                    rel = s_path[len(prefix):]
                    parts = rel.split('/')
                    imm_sub = parts[0]
                    if imm_sub:
                        f_path = prefix + imm_sub
                        # Is this immediate sub-directory a known Universe?
                        if f_path in known_entities:
                            # Tally deep counts for Universes
                            if s.get("type") == "story":
                                universe_counts[f_path] = universe_counts.get(f_path, 0) + 1
                        else:
                            # It's a standard generic folder
                            if f_path not in folders_found:
                                folders_found[f_path] = 0
                            if len(parts) > 1:
                                folder_children.setdefault(f_path, set()).add(parts[1])

        # Apply the unique child counts to the physical generic folders
        for f_path, children in folder_children.items():
            folders_found[f_path] += len(children)
            
        # Inject Universe deep counts into their dictionaries so render_page can read them
        for s in temp_list:
            if s.get("type") == "universe":
                s["thread_count"] = universe_counts.get(s["folder_name"], 0)

        # --- 3. BUILD FINAL LIST ---
        final_list = []
        if not query:
            if self.current_dir != "":
                parent = os.path.dirname(self.current_dir).replace('\\', '/')
                final_list.append({"is_up_dir": True, "target": parent})
                
            for f_path, count in sorted(folders_found.items()):
                final_list.append({
                    "is_folder": True,
                    "folder_name": f_path,
                    "title": os.path.basename(f_path),
                    "count": count
                })

        sort_key = self.sort_var.get().lower()
        is_asc = self.asc_var.get()
        key_map = {"title": "title", "author": "author", "date": "creation_date", "status": "status", "turns": "turns"}
        actual_key = key_map.get(sort_key, "title")

        def sort_logic(item):
            val = item.get(actual_key, "")
            if val is None: return ""
            if isinstance(val, str): return val.lower()
            return val

        temp_list.sort(key=sort_logic, reverse=not is_asc)
        final_list.extend(temp_list)

        self.filtered_stories = final_list
        if reset_page: self.current_page = 1
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
        self.sort_var.set("Title") 
        self.asc_var.set(True)     
        self.btn_order.configure(text="↑ Asc")
        self.apply_search()

    def change_items_per_page(self, new_val):
        """Update grid page size and re-render the library from page 1.

        Args:
            new_val: Selected items-per-page (string or int from the UI control).
        """
        self.items_per_page = int(new_val)
        self.current_page = 1
        self.render_page() # Bypasses sort algorithm

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
        """Draws the specific slice of stories for the current page using Virtualization."""
        # 1. HIDE ALL POTENTIAL EMPTY STATES
        self.lbl_empty.pack_forget()
        if self.welcome_frame:
            self.welcome_frame.pack_forget()
            
        for card in self.card_pool:
            card["frame"].pack_forget()

        total_items = len(self.filtered_stories)
        
        # 2. EVALUATE TRULY EMPTY (NO STORIES AND NO FOLDERS)
        if total_items == 0:
            is_truly_empty = len(self.all_stories) == 0
            if is_truly_empty and not self.search_var.get():
                self._render_empty_welcome()
            else:
                msg = "No stories match your search/filter." if (self.search_var.get() or self.status_var.get() != "All") else "No stories found in this directory."
                self.lbl_empty.configure(text=msg)
                self.lbl_empty.pack(pady=50)
            return
            
        total_pages = max(1, math.ceil(total_items / self.items_per_page))
        
        self.lbl_page.configure(text=f"Page {self.current_page} of {total_pages}")
        self.btn_first.configure(state="normal" if self.current_page > 1 else "disabled")
        self.btn_prev.configure(state="normal" if self.current_page > 1 else "disabled")
        self.btn_next.configure(state="normal" if self.current_page < total_pages else "disabled")
        self.btn_last.configure(state="normal" if self.current_page < total_pages else "disabled")

        if total_items == 0:
            # Check if adventures folder is physically empty (no stories at all)
            is_truly_empty = len(self.all_stories) == 0
            
            if is_truly_empty and not self.search_var.get():
                self.lbl_empty.pack_forget()
                self._render_empty_welcome()
            else:
                msg = "No stories match your search/filter." if (self.search_var.get() or self.status_var.get() != "All") else "No stories found in this directory."
                self.lbl_empty.configure(text=msg)
                self.lbl_empty.pack(pady=50)
            return

        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_slice = self.filtered_stories[start_idx:end_idx]

        for i, item in enumerate(page_slice):
            if i >= len(self.card_pool):
                self.card_pool.append(self._create_card_widget())
                
            refs = self.card_pool[i]
            
            # --- UPDATE SECURE STATE VARIABLES ---
            # These are read by the events bound during card creation
            refs["current_title"] = item.get("title", "")
            
            # --- RENDER LOGIC SWITCH ---
            if item.get("is_up_dir"):
                refs["current_target"] = item["target"] # State
                
                refs["story_container"].pack_forget()
                refs["folder_container"].pack(fill="both", expand=True)
                refs["f_icon_lbl"].configure(text="🔙", text_color="white")
                refs["f_title_lbl"].configure(text="[ .. ] Go back")
                refs["f_count_lbl"].configure(text="(Parent Directory)")
                refs["f_opt_menu"].pack_forget()
                
            elif item.get("is_folder") or item.get("type") == "universe":
                refs["current_target"] = item["folder_name"] 
                
                refs["story_container"].pack_forget()
                refs["folder_container"].pack(fill="both", expand=True)
                
                # --- IMAGE LOGIC (FOLDERS/UNIVERSES) ---
                from api import get_adv_dir
                from PIL import Image
                
                icon_path = get_adv_dir() / item["folder_name"] / "icon.jpg"
                fallback_emoji = "🌌" if item.get("type") == "universe" else "📁"
                fallback_color = "#B39DDB" if item.get("type") == "universe" else "#FFCA28"
                
                # FLUSH CACHE: Create a 1x1 transparent image to forcefully erase any bleeding images
                empty_img = ctk.CTkImage(Image.new("RGBA", (1, 1), (255, 255, 255, 0)), size=(1, 1))
                
                if icon_path.exists():
                    try:
                        img = Image.open(icon_path)
                        refs["img_cache"] = ctk.CTkImage(light_image=img, dark_image=img, size=(38, 38))
                        refs["f_icon_lbl"].configure(image=refs["img_cache"], text="")
                    except Exception:
                        refs["img_cache"] = empty_img
                        refs["f_icon_lbl"].configure(image=empty_img, text=fallback_emoji, text_color=fallback_color)
                else:
                    refs["img_cache"] = empty_img
                    refs["f_icon_lbl"].configure(image=empty_img, text=fallback_emoji, text_color=fallback_color)

                if item.get("type") == "universe":
                    refs["f_mode_lbl"].configure(text="UNIVERSE", text_color="#FF9800")
                    refs["f_mode_lbl"].pack(before=refs["f_title_lbl"], side="left", padx=(0, 10))
                    
                    refs["f_title_lbl"].configure(text=item["title"])
                    cnt = item.get("thread_count", 0)
                    refs["f_count_lbl"].configure(text=f"({cnt} thread{'s' if cnt != 1 else ''})", text_color="gray", font=("Arial", 12, "italic"))
                    
                    # Universes get the Export to .zip option
                    refs["f_opt_menu"].configure(values=["Options...", "Customize Icon...", "Export to .zip", "Rename", "Move...", "Delete", "Browse Here"])
                else:
                    refs["f_mode_lbl"].pack_forget()
                    
                    refs["f_title_lbl"].configure(text=item["title"])
                    cnt = item.get("count", 0)
                    refs["f_count_lbl"].configure(text=f"({cnt} item{'s' if cnt != 1 else ''})", text_color="gray", font=("Arial", 12, "italic"))
                    
                    # Generic Folders do NOT get the Export option
                    refs["f_opt_menu"].configure(values=["Options...", "Customize Icon...", "Rename", "Move...", "Delete", "Browse Here"])
                    
                refs["f_opt_menu"].pack(side="right", padx=15)
                
            else:
                refs["current_target"] = item["folder_name"] 
                refs["is_playable"] = item['mode'] != "error" 
                
                refs["folder_container"].pack_forget()
                refs["story_container"].pack(fill="both", expand=True)
                
                # --- IMAGE LOGIC (STORIES) ---
                from api import get_adv_dir
                from PIL import Image
                
                icon_path = get_adv_dir() / item["folder_name"] / "icon.jpg"
                fallback_emoji = "📖"
                empty_img = ctk.CTkImage(Image.new("RGBA", (1, 1), (255, 255, 255, 0)), size=(1, 1))
                
                if icon_path.exists():
                    try:
                        img = Image.open(icon_path)
                        refs["img_cache"] = ctk.CTkImage(light_image=img, dark_image=img, size=(38, 38))
                        refs["s_icon_lbl"].configure(image=refs["img_cache"], text="")
                    except Exception:
                        refs["img_cache"] = empty_img
                        refs["s_icon_lbl"].configure(image=empty_img, text=fallback_emoji, text_color="white")
                else:
                    refs["img_cache"] = empty_img
                    refs["s_icon_lbl"].configure(image=empty_img, text=fallback_emoji, text_color="white")
                
                mode_color = "#2196F3" if item['mode'] == "sandbox" else "#9C27B0"
                refs["mode_lbl"].configure(text=item['mode'].upper(), text_color=mode_color)
                refs["title_lbl"].configure(text=item['title'])
                
                auth_text = f"{item.get('author', 'Unknown')} • v{item.get('version', '1.0')} • {item.get('creation_date', '')}"
                refs["auth_lbl"].configure(text=auth_text)
                
                t_count = item.get('turns', 0)
                t_text = f" • {t_count} Turn{'s' if t_count != 1 else ''}" if t_count > 0 else ""
                raw_loc = str(item.get('location', 'Unknown')).replace('\n', ' ')
                display_loc = raw_loc[:75].strip() + "..." if len(raw_loc) > 75 else raw_loc
                refs["meta_lbl"].configure(text=f"[{item.get('status', 'Unknown')}]{t_text} • {display_loc}")
                
                state = "normal" if refs["is_playable"] else "disabled"
                refs["btn_play"].configure(state=state)
                
                opt_values = ["Options...", "Customize Icon...", "Restart", "Export to .zip", "Rename", "Move...", "Delete", "Browse Here"]
                refs["opt_menu"].configure(values=opt_values)
            
            refs["frame"].pack(fill="x", pady=4, padx=10)
            
        self.scroll._parent_canvas.yview_moveto(0.0)


    # ---------------------------------------------------------
    # UI COMPONENT BUILDERS
    # ---------------------------------------------------------

    def _create_card_widget(self):
        """Instantiates a single, dual-purpose (Folder/Story) reusable Card object."""
        card = ctk.CTkFrame(self.scroll, corner_radius=8, cursor="hand2")
        
        # State Dictionary for this specific card
        refs = {
            "frame": card,
            "current_target": "",
            "current_title": "",
            "is_playable": False,
            "last_click_time": 0
        }

        # --- RECURSIVE CLICK BINDER WITH DE-BOUNCE ---
        # Prevents double-clicking a folder from accidentally clicking the story that spawns underneath it
        import time
        
        def bind_recursive(widget, handler):
            """Applies the click event to the widget and every single child inside it."""
            widget.bind("<Button-1>", handler)
            for child in widget.winfo_children():
                bind_recursive(child, handler)

        # ==========================================
        # SUB-CONTAINER 1: FOLDER / UNIVERSE
        # ==========================================
        folder_container = ctk.CTkFrame(card, fg_color="transparent")
        
        folder_content = ctk.CTkFrame(folder_container, fg_color="transparent", cursor="hand2")
        folder_content.pack(side="left", fill="both", expand=True)
        
        f_icon_lbl = ctk.CTkLabel(folder_content, text="📁", font=("Segoe UI Emoji", 26), cursor="hand2")
        f_icon_lbl.pack(side="left", padx=(20, 15), pady=10)
        
        f_mode_lbl = ctk.CTkLabel(folder_content, text="", font=("Arial", 10, "bold"), cursor="hand2")
        f_mode_lbl.pack(side="left", padx=(0, 10))
        
        f_title_lbl = ctk.CTkLabel(folder_content, text="", font=("Arial", 16, "bold"), cursor="hand2")
        f_title_lbl.pack(side="left", pady=10)
        
        f_count_lbl = ctk.CTkLabel(folder_content, text="", font=("Arial", 12, "italic"), text_color="gray", cursor="hand2")
        f_count_lbl.pack(side="left", padx=10, pady=10)
        
        # Bind Folder Click
        def on_f_click(e):
            if getattr(self, 'is_loading', False): return
            
            # DE-BOUNCE: Ignore clicks if less than 300ms have passed
            current_time = time.time()
            if current_time - refs["last_click_time"] < 0.3: return
            refs["last_click_time"] = current_time
            
            if refs["current_target"] is not None:
                self.change_dir(refs["current_target"])
                
        bind_recursive(folder_content, on_f_click)
        
        # Bind Folder Menu
        f_opt_menu = ctk.CTkOptionMenu(folder_container, values=["Options...", "Customize Icon...", "Rename", "Move...", "Delete", "Browse Here"], width=110)
        f_opt_menu.pack(side="right", padx=15, pady=10)
        
        def on_f_opt(choice):
            f_opt_menu.set("Options...")
            self.handle_folder_option(choice, refs["current_target"], refs["current_title"])
        f_opt_menu.configure(command=on_f_opt)
        
        # ==========================================
        # SUB-CONTAINER 2: STORY
        # ==========================================
        story_container = ctk.CTkFrame(card, fg_color="transparent")
        
        content_frame = ctk.CTkFrame(story_container, fg_color="transparent", cursor="hand2")
        content_frame.pack(side="left", fill="both", expand=True, padx=15, pady=8)

        # The Story Icon Placeholder
        s_icon_lbl = ctk.CTkLabel(content_frame, text="📖", font=("Segoe UI Emoji", 26), cursor="hand2")
        s_icon_lbl.pack(side="left", padx=(5, 15))

        # We wrap the text in a vertical stack so it sits neatly next to the icon
        text_stack = ctk.CTkFrame(content_frame, fg_color="transparent", cursor="hand2")
        text_stack.pack(side="left", fill="both", expand=True)

        line1 = ctk.CTkFrame(text_stack, fg_color="transparent", cursor="hand2")
        line1.pack(fill="x")
        mode_lbl = ctk.CTkLabel(line1, text="", font=("Arial", 10, "bold"), cursor="hand2")
        mode_lbl.pack(side="left", padx=(0, 10))
        title_lbl = ctk.CTkLabel(line1, text="", font=("Arial", 16, "bold"), cursor="hand2")
        title_lbl.pack(side="left")
        auth_lbl = ctk.CTkLabel(line1, text="", font=("Arial", 11, "italic"), text_color="#A0A0A0", cursor="hand2")
        auth_lbl.pack(side="right")

        line2 = ctk.CTkFrame(text_stack, fg_color="transparent", cursor="hand2")
        line2.pack(fill="x", pady=(2, 0))
        meta_lbl = ctk.CTkLabel(line2, text="", font=("Arial", 12), text_color="gray", cursor="hand2")
        meta_lbl.pack(side="left")
        
        # Bind Story Click
        def on_s_click(e):
            if getattr(self, 'is_loading', False): return
            
            # DE-BOUNCE: Ignore clicks if less than 300ms have passed
            current_time = time.time()
            if current_time - refs["last_click_time"] < 0.3: return
            refs["last_click_time"] = current_time
            
            if refs["current_target"] and refs["is_playable"]:
                self.app.open_workspace(refs["current_target"])
                
        bind_recursive(content_frame, on_s_click)

        btn_frame = ctk.CTkFrame(story_container, fg_color="transparent")
        btn_frame.pack(side="right", padx=15)
        
        btn_play = ctk.CTkButton(btn_frame, text="Play", width=80)
        btn_play.pack(side="left", padx=5)
        
        def safe_play_click():
            if getattr(self, 'is_loading', False): return
            if refs["is_playable"]: self.app.open_workspace(refs["current_target"])
            
        btn_play.configure(command=safe_play_click)
        
        opt_menu = ctk.CTkOptionMenu(btn_frame, values=["Options...", "Customize Icon...", "Restart", "Export to .zip", "Rename", "Move...", "Delete", "Browse Here"], width=110)
        opt_menu.pack(side="left", padx=5)
        
        def on_s_opt(choice):
            opt_menu.set("Options...")
            self.handle_card_option(choice, refs["current_target"], refs["current_title"])
        opt_menu.configure(command=on_s_opt)

        # Store component references in the state dictionary
        refs.update({
            "folder_container": folder_container, "folder_content": folder_content,
            "f_icon_lbl": f_icon_lbl, "f_mode_lbl": f_mode_lbl, "f_title_lbl": f_title_lbl, "f_count_lbl": f_count_lbl, "f_opt_menu": f_opt_menu,
            "story_container": story_container, "content_frame": content_frame, "s_icon_lbl": s_icon_lbl,
            "mode_lbl": mode_lbl, "title_lbl": title_lbl, "auth_lbl": auth_lbl, "meta_lbl": meta_lbl,
            "btn_play": btn_play, "opt_menu": opt_menu
        })
        return refs
        
    
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
                if success:
                    messagebox.showinfo("Restarted", "Story has been reset to Turn 0.")
                    self.load_data() 
                else: 
                    messagebox.showerror("Restart Failed", msg)

        elif choice == "Export to .zip":
            path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=f"{folder_name}.zip", filetypes=[("ZIP files", "*.zip")])
            if path:
                success, msg = TomeWeaverAPI.export_to_zip(folder_name, path)
                if success: messagebox.showinfo("Export Successful", f"Cartridge saved to:\n{path}")
                else: messagebox.showerror("Export Failed", msg)

        elif choice == "Rename":
            self._show_rename_dialog(folder_name, current_title, is_folder=False)
            
        elif choice == "Move...":
            self._show_move_dialog(folder_name, current_title)

        elif choice == "Customize Icon...":
            self._prompt_custom_icon(folder_name)

        elif choice == "Delete":
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete '{current_title}'?"):
                success, msg = TomeWeaverAPI.delete_story(folder_name)
                if success: 
                    messagebox.showinfo("Deleted", f"'{current_title}' has been successfully deleted.")
                    self.is_loading = False 
                    self.all_stories = [s for s in self.all_stories if s.get("folder_name") != folder_name]
                    self.apply_search()
                else: 
                    messagebox.showerror("Delete Failed", f"Could not delete folder: {msg}")
                    
        elif choice == "Browse Here":
            TomeWeaverAPI.browse_path(folder_name)

    def handle_folder_option(self, choice, folder_path, current_title):
        """Routes actions from the 'Options...' dropdown on physical folder cards and Universes."""
        if choice == "Browse Here":
            TomeWeaverAPI.browse_path(folder_path)
            
        elif choice == "Customize Icon...":
            self._prompt_custom_icon(folder_path)
            
        elif choice == "Export to .zip":
            # Native Save Dialog, defaulting to the Universe's display name
            path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=f"{current_title}.zip", filetypes=[("ZIP Cartridges", "*.zip")])
            if path:
                success, msg = TomeWeaverAPI.export_to_zip(folder_path, path)
                if success: messagebox.showinfo("Export Successful", f"Universe exported to:\n{path}")
                else: messagebox.showerror("Export Failed", msg)
            
        elif choice == "Rename":
            self._show_rename_dialog(folder_path, current_title, is_folder=True)
            
        elif choice == "Move...":
            self._show_move_dialog(folder_path, current_title)

        elif choice == "Delete":
            warn_msg = (
                f"Are you sure you want to permanently delete '{current_title}'?\n\n"
                "WARNING: This will recursively delete EVERY STORY inside this folder. "
                "This action cannot be undone!"
            )
            if messagebox.askyesno("Confirm Deep Delete", warn_msg, icon='warning'):
                success, msg = TomeWeaverAPI.delete_folder(folder_path)
                if success:
                    messagebox.showinfo("Deleted", f"Folder '{current_title}' has been deleted.")
                    self.is_loading = False 
                    self.load_data()
                else:
                    messagebox.showerror("Delete Failed", msg)

    # --- REUSABLE UTILITY MODALS ---

    def _prompt_custom_icon(self, rel_path):
        """Opens a file dialog to select an image, processes it via API, and redraws the UI."""
        path = filedialog.askopenfilename(
            title="Select Custom Icon",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.webp")]
        )
        if path:
            success, msg = TomeWeaverAPI.set_custom_icon(rel_path, path)
            if success:
                self.is_loading = False
                self.load_data() # Force disk-reload so the new image is cached
            else:
                messagebox.showerror("Icon Error", f"Failed to set custom icon: {msg}")

    def _show_rename_dialog(self, path, current_title, is_folder):
        """Unified rename modal for stories and folders."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Rename {'Folder' if is_folder else 'Story'}")
        dialog.geometry("400x200")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Enter new name:", font=("Arial", 14, "bold")).pack(pady=(20, 10))
        
        new_title_var = ctk.StringVar(value=current_title)
        entry = ctk.CTkEntry(dialog, textvariable=new_title_var, width=300, font=("Arial", 14))
        entry.pack(pady=10)
        entry.focus()
        entry.select_range(0, 'end')

        def on_rename():
            new_title = new_title_var.get().strip()
            if not new_title or new_title == current_title:
                dialog.destroy()
                return
            
            dialog.destroy()
            if is_folder:
                success, msg = TomeWeaverAPI.rename_folder(path, new_title)
            else:
                success, msg = TomeWeaverAPI.rename_story(path, new_title)
            
            if success:
                self.is_loading = False 
                self.load_data()
            else:
                messagebox.showerror("Rename Failed", msg)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#D32F2F", hover_color="#9A0007", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Rename", width=100, fg_color="#2E7D32", hover_color="#1B5E20", command=on_rename).pack(side="right", padx=10)

    def _show_move_dialog(self, source_path, current_title):
        """Unified Move modal allowing any folder, universe, or story to be moved safely."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Move Item")
        dialog.geometry("450x450")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=f"Move '{current_title}'", font=("Arial", 16, "bold")).pack(pady=(15, 5))
        
        dialog_path_lbl = ctk.CTkLabel(dialog, text=f"Destination: /{self.current_dir}", font=("Arial", 12, "italic"), text_color="#00ACC1")
        dialog_path_lbl.pack(pady=(0, 10))

        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.pack(fill="both", expand=True, padx=20, pady=5)
        
        state = {"active_dir": self.current_dir, "selected_dir": self.current_dir}
        ui_rows = [] 

        def render_folders():
            for w in scroll.winfo_children(): w.destroy()
            ui_rows.clear()
            
            from api import get_adv_dir
            import os
            from config import find_universe_root
            
            # Determine if the item we are moving is a Universe itself
            is_moving_universe = (get_adv_dir() / source_path / "master_setup.json").exists()
            
            if state["active_dir"] != "":
                parent = os.path.dirname(state["active_dir"]).replace('\\', '/')
                _build_dialog_row(parent, "[ .. ] Go Up", is_up=True)
                
            active_os_path = get_adv_dir() / state["active_dir"]
            available_folders = []
            
            if active_os_path.exists():
                for item in active_os_path.iterdir():
                    # Identify valid container folders (Standard folders AND Universes)
                    if item.is_dir() and not (item / "setup.json").exists() and not item.name.startswith("."):
                        rel_path = item.relative_to(get_adv_dir()).as_posix()
                        
                        # --- PARADOX PREVENTION ---
                        # 1. You cannot move a folder into itself.
                        # 2. You cannot move a folder into one of its own children/grandchildren!
                        if rel_path == source_path or rel_path.startswith(source_path + "/"):
                            continue
                            
                        # --- UNIVERSE CONTAINMENT ENFORCEMENT ---
                        # You cannot move a Universe inside another Universe.
                        if is_moving_universe and find_universe_root(item):
                            continue
                            
                        available_folders.append(rel_path)
                            
            for f_path in sorted(available_folders):
                # Optionally add a visual indicator in the move dialog if it's a Universe
                display_name = f"🌌 {os.path.basename(f_path)}" if (get_adv_dir() / f_path / "master_setup.json").exists() else os.path.basename(f_path)
                _build_dialog_row(f_path, display_name, is_up=False)
                
                
        def _build_dialog_row(target_path, display_name, is_up):
            row = ctk.CTkFrame(scroll, fg_color="#2B2B2B" if state["selected_dir"] == target_path else "transparent", corner_radius=6, cursor="hand2")
            row.pack(fill="x", pady=2, padx=2)
            ui_rows.append((target_path, row))
            
            icon = "🔙" if is_up else "📁"
            color = "white" if is_up else "#FFCA28"
            ctk.CTkLabel(row, text=icon, font=("Segoe UI Emoji", 20), text_color=color, cursor="hand2").pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(row, text=display_name, font=("Arial", 14, "bold"), cursor="hand2").pack(side="left", pady=8)
            
            import time
            row.last_click_time = 0
            
            def on_click(e, t_path=target_path, r_widget=row):
                current_time = time.time()
                if current_time - r_widget.last_click_time < 0.3:
                    state["active_dir"] = t_path
                    state["selected_dir"] = t_path
                    dialog_path_lbl.configure(text=f"Destination: /{t_path}")
                    render_folders()
                    return
                    
                r_widget.last_click_time = current_time
                state["selected_dir"] = t_path
                dialog_path_lbl.configure(text=f"Destination: /{t_path}")
                
                for path, r in ui_rows:
                    r.configure(fg_color="#2B2B2B" if path == t_path else "transparent")
                    
            row.bind("<Button-1>", on_click)
            for child in row.winfo_children():
                child.bind("<Button-1>", on_click)

        def on_confirm_move():
            target = state["selected_dir"]
            import os
            current_parent = os.path.dirname(source_path).replace('\\', '/')
            
            if current_parent.strip('/') == target.strip('/'):
                messagebox.showinfo("Move", "The item is already in that folder.")
                return
                
            dialog.destroy()
            
            from api import get_adv_dir
            # Intelligent routing: if it has setup.json, it's a story. Otherwise it's a structural folder/universe.
            if (get_adv_dir() / source_path / "setup.json").exists():
                success, msg = TomeWeaverAPI.move_story(source_path, target)
            else:
                success, msg = TomeWeaverAPI.move_folder(source_path, target)
                
            if success:
                messagebox.showinfo("Moved", f"'{current_title}' successfully moved.")
                self.is_loading = False 
                self.load_data() 
            else:
                messagebox.showerror("Move Failed", msg)

        render_folders()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#D32F2F", hover_color="#9A0007", command=dialog.destroy).pack(side="left")
        ctk.CTkButton(btn_frame, text="Move Here", width=100, fg_color="#1F6AA5", hover_color="#144870", command=on_confirm_move).pack(side="right")
        
    def show_create_folder_dialog(self):
        """Spawns a modal to create a physical sub-directory."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Create New Folder")
        dialog.geometry("400x200")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Enter folder name:", font=("Arial", 14, "bold")).pack(pady=(20, 10))
        name_var = ctk.StringVar()
        entry = ctk.CTkEntry(dialog, textvariable=name_var, width=300, font=("Arial", 14))
        entry.pack(pady=10)
        entry.focus()

        def on_create():
            f_name = name_var.get().strip()
            if not f_name: return
            
            dialog.destroy()
            success, msg = TomeWeaverAPI.create_folder(self.current_dir, f_name)
            if success:
                self.is_loading = False 
                self.load_data() # Force disk re-scan to discover the new empty folder
            else:
                messagebox.showerror("Error", msg)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#D32F2F", hover_color="#9A0007", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Create", width=100, fg_color="#2E7D32", hover_color="#1B5E20", command=on_create).pack(side="right", padx=10)

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

    def _handle_create_menu(self, choice):
        """Intercepts the dropdown selection and resets the button text."""
        from config import find_universe_root
        from api import get_adv_dir
        is_univ = find_universe_root(get_adv_dir() / self.current_dir) is not None
        self.new_story_var.set("+ Create Thread" if is_univ else "+ Create New Story")
        
        if choice == "Manual Setup...":
            self.show_create_dialog()
        elif choice == "Generate via AI...":
            self.show_ai_create_dialog()
        elif choice == "Guided Wizard...":
            self.show_wizard_dialog()
        elif choice == "Create Universe...":
            self._show_create_universe_dialog()
        elif choice == "Download Samples...":
            self._trigger_sample_download()

    def _show_create_universe_dialog(self):
        """Spawns the modal to create a new Shared Universe container."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Create Shared Universe")
        dialog.geometry("450x450")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Create a Universe", font=("Arial", 18, "bold"), text_color="#B39DDB").pack(pady=(15, 5))
        ctk.CTkLabel(dialog, text="A container where multiple stories share the same World Lore and Memory.", text_color="gray", wraplength=400).pack(pady=(0, 15))
        
        ctk.CTkLabel(dialog, text="Universe Name:", font=("Arial", 14, "bold")).pack(anchor="w", padx=20)
        v_title = ctk.StringVar()
        ctk.CTkEntry(dialog, textvariable=v_title, font=("Arial", 14)).pack(fill="x", padx=20, pady=(2, 15))
        
        ctk.CTkLabel(dialog, text="Author Name:", font=("Arial", 14, "bold")).pack(anchor="w", padx=20)
        
        from config import INSTANCE_CONFIG, ROOT_DIR
        last_author = INSTANCE_CONFIG.get("last_author", "Anonymous")
        
        v_author = ctk.StringVar(value=last_author)
        ctk.CTkEntry(dialog, textvariable=v_author, font=("Arial", 14)).pack(fill="x", padx=20, pady=(2, 15))
        
        ctk.CTkLabel(dialog, text="Global Tone & Atmosphere:", font=("Arial", 14, "bold")).pack(anchor="w", padx=20)
        v_tone = ctk.StringVar()
        ctk.CTkEntry(dialog, textvariable=v_tone, font=("Arial", 14), placeholder_text="e.g. Gritty, high-fantasy, suspenseful").pack(fill="x", padx=20, pady=(2, 15))
        
        ctk.CTkLabel(dialog, text="Global Rules & Lore:", font=("Arial", 14, "bold")).pack(anchor="w", padx=20)
        t_lore = ctk.CTkTextbox(dialog, height=80, wrap="word", font=("Arial", 14))
        t_lore.pack(fill="x", padx=20, pady=(2, 15))

        def on_create():
            title = v_title.get().strip()
            if not title: return
            
            from config import INSTANCE_CONFIG, ROOT_DIR, save_json_atomically
            author_val = v_author.get().strip()
            INSTANCE_CONFIG["last_author"] = author_val
            save_json_atomically(INSTANCE_CONFIG, ROOT_DIR / "configs" / "instance_config.json")
            
            success, msg = TomeWeaverAPI.create_universe(title, author_val, v_tone.get(), t_lore.get("1.0", "end"), self.current_dir)
            if success:
                dialog.destroy()
                self.is_loading = False
                self.load_data()
                # Auto-navigate into the newly created universe
                self.after(500, lambda: self.change_dir(msg))
            else:
                messagebox.showerror("Creation Failed", msg)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#D32F2F", hover_color="#9A0007", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Create Universe", width=140, font=("Arial", 14, "bold"), fg_color="#673AB7", hover_color="#4A148C", command=on_create).pack(side="right", padx=10)

    def show_wizard_dialog(self):
        """Spawns the step-by-step guided narrative builder."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Story Creation Wizard")
        dialog.geometry("600x550")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # Data State
        v_title = ctk.StringVar()
        v_author = ctk.StringVar()
        v_mode = ctk.StringVar(value="sandbox")
        v_inv = ctk.BooleanVar(value=False)
        v_die = ctk.BooleanVar(value=False)
        
        main_container = ctk.CTkFrame(dialog, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        steps = []
        current_step = [0]
        
        # --- Step 0: Basics ---
        f0 = ctk.CTkFrame(main_container, fg_color="transparent")
        ctk.CTkLabel(f0, text="Step 1: The Basics", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(0, 20))
        
        ctk.CTkLabel(f0, text="Adventure Title (Required):", font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkEntry(f0, textvariable=v_title, width=300, font=("Arial", 14)).pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(f0, text="Author Name:", font=("Arial", 14, "bold")).pack(anchor="w")
        
        from config import INSTANCE_CONFIG, ROOT_DIR
        last_author = INSTANCE_CONFIG.get("last_author", "Anonymous")
        
        v_author = ctk.StringVar(value=last_author)
        ctk.CTkEntry(f0, textvariable=v_author, width=300, font=("Arial", 14)).pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(f0, text="Game Mode:", font=("Arial", 14, "bold")).pack(anchor="w")
        mf = ctk.CTkFrame(f0, fg_color="transparent")
        mf.pack(fill="x", pady=(0, 15))
        ctk.CTkRadioButton(mf, text="Sandbox (Open-World)", variable=v_mode, value="sandbox").pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(mf, text="Campaign (Plot-Driven)", variable=v_mode, value="campaign").pack(side="left")
        
        ctk.CTkLabel(f0, text="Engine Rules:", font=("Arial", 14, "bold")).pack(anchor="w")
        rf = ctk.CTkFrame(f0, fg_color="transparent")
        rf.pack(fill="x", pady=(0, 15))
        ctk.CTkSwitch(rf, text="Track Inventory", variable=v_inv).pack(side="left", padx=(0, 20))
        ctk.CTkSwitch(rf, text="Allow Death", variable=v_die).pack(side="left")
        
        steps.append(f0)
        
        # --- Step 1: Protagonist ---
        f1 = ctk.CTkFrame(main_container, fg_color="transparent")
        ctk.CTkLabel(f1, text="Step 2: The Protagonist", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(0, 10))
        ctk.CTkLabel(f1, text="Who is the main character?", font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(f1, text="Tip: The AI performs best when you include personality traits and physical limitations.\n(e.g., 'A cynical, aging detective with a bad knee.')", text_color="gray", justify="left").pack(anchor="w", pady=(0, 10))
        t_char = ctk.CTkTextbox(f1, height=150, wrap="word", font=("Arial", 14))
        t_char.pack(fill="x")
        steps.append(f1)
        
        # --- Step 2: Setting & Lore ---
        f2 = ctk.CTkFrame(main_container, fg_color="transparent")
        ctk.CTkLabel(f2, text="Step 3: The World", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(0, 10))
        ctk.CTkLabel(f2, text="Where does the story start?", font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(f2, text="Tip: Location, time, period, etc. Sensory details (lighting, smell, architecture).", text_color="gray", justify="left").pack(anchor="w", pady=(0, 5))
        t_set = ctk.CTkTextbox(f2, height=120, wrap="word", font=("Arial", 14))
        t_set.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(f2, text="What are the rules of this world? (Lore)", font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(f2, text="Tip: (e.g., 'Magic is illegal', 'Zombies are blind but hear well')", text_color="gray", justify="left").pack(anchor="w", pady=(0, 5))
        t_lore = ctk.CTkTextbox(f2, height=120, wrap="word", font=("Arial", 14))
        t_lore.pack(fill="x")
        steps.append(f2)
        
        # --- Step 3: Objective ---
        f3 = ctk.CTkFrame(main_container, fg_color="transparent")
        ctk.CTkLabel(f3, text="Step 4: The Objective", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(0, 10))
        ctk.CTkLabel(f3, text="What is the primary goal?", font=("Arial", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(f3, text="Give the character a reason to move forward.", text_color="gray", justify="left").pack(anchor="w", pady=(0, 10))
        t_goal = ctk.CTkTextbox(f3, height=150, wrap="word", font=("Arial", 14))
        t_goal.pack(fill="x")
        steps.append(f3)
        
        # --- Navigation Footer ---
        nav_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        nav_frame.pack(fill="x", side="bottom", padx=20, pady=20)
        
        btn_back = ctk.CTkButton(nav_frame, text="< Back", width=100, fg_color="#4A4A4A", hover_color="#333333")
        btn_back.pack(side="left")
        
        btn_next = ctk.CTkButton(nav_frame, text="Next >", width=100, fg_color="#1F6AA5", hover_color="#144870")
        btn_next.pack(side="right")
        
        def update_view():
            idx = current_step[0]
            for f in steps: f.pack_forget()
            steps[idx].pack(fill="both", expand=True)
            
            btn_back.configure(state="normal" if idx > 0 else "disabled")
            
            if idx == len(steps) - 1:
                btn_next.configure(text="Finish & Build World", fg_color="#2E7D32", hover_color="#1B5E20")
            else:
                btn_next.configure(text="Next >", fg_color="#1F6AA5", hover_color="#144870")
                
            # Disable next if on Step 1 and Title is missing
            if idx == 0 and not v_title.get().strip():
                btn_next.configure(state="disabled")
            else:
                btn_next.configure(state="normal")
                
        def on_title_change(*args):
            if current_step[0] == 0: update_view()
                
        v_title.trace_add("write", on_title_change)
        
        def go_next():
            idx = current_step[0]
            if idx < len(steps) - 1:
                current_step[0] += 1
                update_view()
            else:
                on_finish()
                
        def go_back():
            idx = current_step[0]
            if idx > 0:
                current_step[0] -= 1
                update_view()
                
        btn_next.configure(command=go_next)
        btn_back.configure(command=go_back)
        
        def on_finish():
            title = v_title.get().strip()
            if not title: return
            
            from config import INSTANCE_CONFIG, ROOT_DIR, save_json_atomically
            author_val = v_author.get().strip()
            INSTANCE_CONFIG["last_author"] = author_val
            save_json_atomically(INSTANCE_CONFIG, ROOT_DIR / "configs" / "instance_config.json")
            
            rules_cfg = {
                "track_inventory": v_inv.get(),
                "can_die": v_die.get(),
                "allow_cheats": True if v_mode.get() == "sandbox" else False
            }
            
            # Extract Textbox values
            extra_data = {
                "main_character": t_char.get("1.0", "end").strip(),
                "setting": t_set.get("1.0", "end").strip(),
                "lore_and_rules": t_lore.get("1.0", "end").strip(),
                "goal": t_goal.get("1.0", "end").strip()
            }
            
            success, msg = TomeWeaverAPI.create_story(
                title, v_author.get().strip(), v_mode.get(), rules_cfg, self.current_dir, extra_data
            )
            
            if success:
                dialog.destroy()
                self.load_data()
                # Dump the user straight into the World Builder to review their answers
                self.app.open_workspace(msg, target_tab="World Builder")
            else:
                messagebox.showerror("Creation Failed", msg)

        update_view()

    def show_create_dialog(self):
        """Spawns the modal dialog for initializing a new, empty adventure framework."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Create New Story (Manual)")
        dialog.geometry("400x360")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Adventure Title:", font=("Arial", 14)).pack(pady=(15, 2))
        
        title_var = ctk.StringVar()
        title_entry = ctk.CTkEntry(dialog, textvariable=title_var, width=300)
        title_entry.pack(pady=5)
        
        ctk.CTkLabel(dialog, text="Author Name:", font=("Arial", 14)).pack(pady=(10, 2))
        
        from config import INSTANCE_CONFIG, ROOT_DIR
        last_author = INSTANCE_CONFIG.get("last_author", "Anonymous")
        
        author_var = ctk.StringVar(value=last_author)
        author_entry = ctk.CTkEntry(dialog, textvariable=author_var, width=300)
        author_entry.pack(pady=5)

        ctk.CTkLabel(dialog, text="Select Mode:", font=("Arial", 14)).pack(pady=(15, 2))
        mode_var = ctk.StringVar(value="sandbox")
        
        radio_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        radio_frame.pack()
        ctk.CTkRadioButton(radio_frame, text="Sandbox (Open-World)", variable=mode_var, value="sandbox").pack(side="left", padx=10)
        ctk.CTkRadioButton(radio_frame, text="Campaign (Plot-Driven)", variable=mode_var, value="campaign").pack(side="left", padx=10)
        
        # Engine Rules Toggles
        rules_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        rules_frame.pack(pady=15)
        
        inv_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(rules_frame, text="Track Inventory", variable=inv_var).pack(side="left", padx=(0, 20))
        
        die_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(rules_frame, text="Allow Death", variable=die_var).pack(side="left")

        # Instantiate button early so the tracker can modify it
        btn_create = ctk.CTkButton(dialog, text="Create")
        
        def check_title(*args):
            """Real-time validation: Disable the button if the title is empty."""
            if title_var.get().strip():
                btn_create.configure(state="normal")
            else:
                btn_create.configure(state="disabled")
                
        title_var.trace_add("write", check_title)

        def on_create():
            title = title_var.get().strip()
            if not title: return
            
            from config import INSTANCE_CONFIG, ROOT_DIR, save_json_atomically
            author_val = author_var.get().strip()
            INSTANCE_CONFIG["last_author"] = author_val
            save_json_atomically(INSTANCE_CONFIG, ROOT_DIR / "configs" / "instance_config.json")
                
            rules_cfg = {
                "track_inventory": inv_var.get(),
                "can_die": die_var.get(),
                "allow_cheats": True if mode_var.get() == "sandbox" else False
            }
                
            success, msg = TomeWeaverAPI.create_story(title, author_val, mode_var.get(), rules_cfg, self.current_dir)
            
            if success:
                dialog.destroy() # Only close the window if the folder was successfully created
                self.load_data()
                # Route directly to the World Builder tab
                self.app.open_workspace(msg, target_tab="World Builder")
            else:
                # If folder exists, pop an error but leave the form open so the user can fix the title
                messagebox.showerror("Creation Failed", msg)

        btn_create.configure(command=on_create, state="disabled", width=150, height=36) # Start disabled
        btn_create.pack(pady=25)
        
    def show_ai_create_dialog(self):
        """Spawns the advanced AI Generator modal."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("AI World Generator")
        dialog.geometry("550x630") # Made slightly taller to fit the new Universe checkbox
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="AI World Generator", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(15, 5))
        ctk.CTkLabel(dialog, text="Describe your concept. The AI will construct the setup and plot.", font=("Arial", 12, "italic"), text_color="gray").pack(pady=(0, 10))

        # Title & Author
        ta_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        ta_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(ta_frame, text="Title:", width=60, anchor="e").pack(side="left", padx=(0, 5))
        title_entry = ctk.CTkEntry(ta_frame)
        title_entry.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(ta_frame, text="Author:", width=50, anchor="e").pack(side="left", padx=(10, 5))
        
        from config import INSTANCE_CONFIG, ROOT_DIR
        last_author = INSTANCE_CONFIG.get("last_author", "Anonymous")
        
        author_var = ctk.StringVar(value=last_author)
        author_entry = ctk.CTkEntry(ta_frame, textvariable=author_var, width=120)
        author_entry.pack(side="left")

        # Mode Selection
        mode_var = ctk.StringVar(value="sandbox")
        mode_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        mode_frame.pack(pady=5)
        
        def on_mode_change():
            if mode_var.get() == "sandbox":
                chk_epi.deselect()
                chk_epi.configure(state="disabled")
            else:
                chk_epi.configure(state="normal")
                
        ctk.CTkRadioButton(mode_frame, text="Sandbox", variable=mode_var, value="sandbox", command=on_mode_change).pack(side="left", padx=10)
        ctk.CTkRadioButton(mode_frame, text="Campaign", variable=mode_var, value="campaign", command=on_mode_change).pack(side="left", padx=10)

        # AI Prompt
        ctk.CTkLabel(dialog, text="Adventure Prompt:").pack(anchor="w", padx=20, pady=(5, 0))
        prompt_box = ctk.CTkTextbox(dialog, height=200, wrap="word", font=("Arial", 14)) 
        prompt_box.pack(fill="x", padx=20, pady=0)
        prompt_box.insert("1.0", "A dark fantasy heist where a master thief must break into the crypt of the Sunken King to steal a cursed ruby.")

        # Narrative Generation Toggles
        chk_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        chk_frame.pack(fill="x", padx=20, pady=5) 
        
        gen_pro_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(chk_frame, text="Generate Prologue", variable=gen_pro_var).pack(side="left", padx=(0, 20))
        
        gen_epi_var = ctk.BooleanVar(value=False)
        chk_epi = ctk.CTkSwitch(chk_frame, text="Generate Epilogue", variable=gen_epi_var, state="disabled")
        chk_epi.pack(side="left")
        
        # --- NEW: UNIVERSE CONTEXT CHECKBOX ---
        from config import find_universe_root
        from api import get_adv_dir
        univ_root = find_universe_root(get_adv_dir() / self.current_dir)
        read_univ_var = ctk.BooleanVar(value=True) # Default to true if inside a universe
        
        if univ_root:
            univ_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            univ_frame.pack(fill="x", padx=20, pady=(5, 0))
            ctk.CTkSwitch(univ_frame, text="Inspire from Universe Lore (Read master_setup.json)", variable=read_univ_var, progress_color="#FF9800").pack(side="left")
            from ui.tooltip import Tooltip
            Tooltip(univ_frame, "If checked, the AI will read the global Universe rules and tone, ensuring this new story fits perfectly into the existing world.")
        else:
            # Force false if we are just making a normal standalone story
            read_univ_var.set(False)
        
        # Engine Rules Toggles
        rules_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        rules_frame.pack(fill="x", padx=20, pady=(10, 0))
        
        inv_var = ctk.BooleanVar(value=False)
        inv_chk = ctk.CTkSwitch(rules_frame, text="Track Inventory/Status", variable=inv_var)
        inv_chk.pack(side="left", padx=(0, 20))
        
        die_var = ctk.BooleanVar(value=False)
        die_chk = ctk.CTkSwitch(rules_frame, text="Allow Game Over (Death)", variable=die_var)
        die_chk.pack(side="left")

        # Status Label
        status_lbl = ctk.CTkLabel(dialog, text="", font=("Arial", 12, "italic"))
        status_lbl.pack(pady=(5, 0)) 

        # Submit Button
        def on_generate():
            raw_title = title_entry.get().strip()
            title = raw_title if raw_title else "AI Draft"
            prompt = prompt_box.get("1.0", "end").strip()
            if not prompt:
                from tkinter import messagebox
                messagebox.showwarning("Missing Info", "Please enter an adventure concept prompt.")
                return

            from config import INSTANCE_CONFIG, ROOT_DIR, save_json_atomically
            author_val = author_var.get().strip()
            INSTANCE_CONFIG["last_author"] = author_val
            try:
                save_json_atomically(INSTANCE_CONFIG, ROOT_DIR / "configs" / "instance_config.json")
            except Exception: pass

            dialog.configure(cursor="watch") 
            btn_gen.configure(state="disabled", text="Saving draft & connecting...")
            status_lbl.configure(text="Securing your draft to disk...", text_color="#00ACC1")
            
            rules_cfg = {
                "track_inventory": inv_var.get(),
                "can_die": die_var.get(),
                "allow_cheats": True if mode_var.get() == "sandbox" else False
            }
            
            # --- STEP 1: CREATE THE PHYSICAL DRAFT FIRST (ZERO DATA LOSS) ---
            # We inject the prompt directly into the setup.json file so it's immortalized on disk!
            from api import TomeWeaverAPI
            extra = {"ai_generation_prompt": prompt}
            success, folder_or_err = TomeWeaverAPI.create_story(
                title, author_val, mode_var.get(), rules_cfg, self.current_dir, extra_data=extra
            )
            
            if not success:
                from tkinter import messagebox
                messagebox.showerror("Disk Error", f"Failed to save draft to disk: {folder_or_err}")
                dialog.configure(cursor="") 
                btn_gen.configure(state="normal", text="✨ Generate World")
                status_lbl.configure(text="", text_color="white")
                return
                
            folder_name = folder_or_err
            
            # --- STEP 2: OFF-LOAD THE AI HEAVY LIFTING TO THE BACKGROUND ---
            def worker():
                # Load the engine for the safe draft we just created on disk
                engine = TomeWeaverAPI.load_engine(folder_name)
                
                # Fetch universe lore context if requested
                univ_lore_str = ""
                if read_univ_var.get() and univ_root:
                    from config import load_json_safely
                    master_setup = load_json_safely(univ_root / "master_setup.json", "master_setup.json")
                    u_title = master_setup.get("universe_title", "The Universe")
                    u_tone = master_setup.get("tone", "")
                    u_rules = master_setup.get("lore_and_rules", "")
                    univ_lore_str = f"UNIVERSE CONTEXT ({u_title}):\nTone: {u_tone}\nLore: {u_rules}\n"
                
                # Use the OVERHAUL method to safely mutate the engine we just created
                self.after(0, lambda: status_lbl.configure(text="Contacting LLM... This may take up to a minute."))
                success_ai, msg = TomeWeaverAPI.overhaul_active_story(engine, prompt, gen_pro_var.get(), gen_epi_var.get(), universe_lore=univ_lore_str)
                
                def on_complete():
                    if success_ai:
                        dialog.destroy() 
                        self.load_data() 
                        self.app.open_workspace(folder_name, target_tab="Story World") 
                    else:
                        from tkinter import messagebox
                        dialog.configure(cursor="") 
                        btn_gen.configure(state="normal", text="✨ Try Again")
                        status_lbl.configure(text="Connection failed. Draft safely stored in library.", text_color="#F44336")
                        
                        warn_msg = f"The AI failed to respond, but your prompt was safely saved to a new folder called '{title}'.\n\nEnsure LM Studio is running, open the story from your Library, and click 'Overhaul Story' to try again.\n\nError: {msg}"
                        messagebox.showerror("AI Generation Error", warn_msg)
                        self.load_data() # Force UI refresh so the new draft appears behind the modal!
                        
                self.after(0, on_complete)

            import threading
            threading.Thread(target=worker, daemon=True).start()

        btn_gen = ctk.CTkButton(dialog, text="✨ Generate World", font=("Arial", 16, "bold"), fg_color="#00ACC1", hover_color="#00838F", width=220, height=45, command=on_generate)
        btn_gen.pack(pady=20)
        
    def show_global_settings(self):
        """Opens a modal to edit configs/engine_config.json."""
        from config import load_engine_config, ROOT_DIR, ENGINE_CONFIG, get_adventures_dir, get_default_adventures_dir
        from ui.tooltip import Tooltip
        from tkinter import filedialog
        import json
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Global Engine Settings")
        dialog.geometry("600x820")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Global API & Engine Configuration", font=("Arial", 18, "bold")).pack(pady=(20, 10))
        
        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)

        current_config = load_engine_config()
        fields = {}
        old_adv_root = str(get_adventures_dir())

        def add_field(label_text, key_name, is_bool=False, is_number=False, tooltip_text=""):
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
        ctk.CTkLabel(scroll, text="--- Data & Storage ---", text_color="gray").pack(pady=(10, 5))

        adv_row = ctk.CTkFrame(scroll, fg_color="transparent")
        adv_row.pack(fill="x", pady=5)
        lbl_adv = ctk.CTkLabel(adv_row, text="Adventures Library:", font=("Arial", 14, "bold"), width=200, anchor="e")
        lbl_adv.pack(side="left", padx=(0, 15))
        Tooltip(lbl_adv, "Root folder for all story cartridges, universes, and index.json. Leave empty for the default ./adventures next to the app.")

        adventures_var = ctk.StringVar(value=str(get_adventures_dir()))
        adv_entry = ctk.CTkEntry(adv_row, textvariable=adventures_var, font=("Arial", 13), width=220)
        adv_entry.pack(side="left", expand=True, fill="x")

        def browse_adventures_dir():
            initial = adventures_var.get().strip() or str(get_default_adventures_dir())
            if not Path(initial).exists():
                initial = str(get_default_adventures_dir())
            picked = filedialog.askdirectory(title="Select Adventures Library Folder", initialdir=initial)
            if picked:
                adventures_var.set(str(Path(picked).resolve()))

        btn_browse_adv = ctk.CTkButton(adv_row, text="Browse...", width=80, command=browse_adventures_dir)
        btn_browse_adv.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            scroll,
            text=f"Default when empty: {get_default_adventures_dir()}  •  index.json lives inside this folder.",
            font=("Arial", 11, "italic"),
            text_color="gray",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 5))

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
        add_field("Context & Memory Window (Turns):", "context_window", is_number=True, tooltip_text="How many past turns the AI remembers. This also dictates how often the background memory engine runs.")
        add_field("Memory Decay Threshold (Turns):", "memory_decay_threshold", is_number=True, tooltip_text="Entities not mentioned in this many turns are auto-archived to save tokens. Pinned entities ignore this.")
        
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
        add_field("Text Wrap Margin (Pixels):", "ui_wrap_margin", is_number=True, tooltip_text="Adjusts the right-side padding for text in the timeline. Increase this if your text is being cut off on the right.")
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

            adv_raw = adventures_var.get().strip()
            if adv_raw:
                adv_path = Path(adv_raw).expanduser().resolve()
                new_config["adventures_dir"] = "" if adv_path == get_default_adventures_dir() else str(adv_path)
            else:
                new_config["adventures_dir"] = ""
            
            # Hard-delete the legacy chunk size if it exists in the active UI payload
            if "memory_chunk_size" in new_config: del new_config["memory_chunk_size"]
            
            try:
                # 1. Save to disk
                config_path = ROOT_DIR / "configs" / "engine_config.json"
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(new_config, f, indent=4)
                    
                # 2. Mutate active memory globally (CRITICAL FIX)
                ENGINE_CONFIG.clear()
                ENGINE_CONFIG.update(new_config)

                if str(get_adventures_dir()) != old_adv_root:
                    self.current_dir = ""
                    if hasattr(self.app, "last_dashboard_dir"):
                        self.app.last_dashboard_dir = ""
                    self.load_data()
                    
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
        
        
    def _render_empty_welcome(self):
        """Displays a large welcome screen with a Download Samples button."""
        # Reuse existing frame if possible to save memory
        if not self.welcome_frame:
            self.welcome_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
            
            ctk.CTkLabel(self.welcome_frame, text="Welcome to TomeWeaver", font=("Georgia", 32, "bold")).pack()
            ctk.CTkLabel(self.welcome_frame, text="Your library is currently empty.", font=("Arial", 16), text_color="gray").pack(pady=(5, 30))
            
            btn_dl = ctk.CTkButton(self.welcome_frame, text="📦 Download Sample Adventures", font=("Arial", 16, "bold"), 
                                   height=50, fg_color="#1F6AA5", command=self._trigger_sample_download)
            btn_dl.pack()

        self.welcome_frame.pack(expand=True, pady=100)
        
    def _trigger_sample_download(self):
        self.lbl_loading.pack(pady=50)
        
        def worker():
            success, msg = TomeWeaverAPI.download_samples(lambda status: self.after(0, lambda: self.lbl_loading.configure(text=status)))
            def complete():
                self.lbl_loading.pack_forget()
                if success:
                    # Update the dropdown values to remove the Download option now that they exist
                    new_vals = ["Manual Setup...", "Generate via AI...", "Guided Wizard..."]
                    self.btn_new.configure(values=new_vals)
                    
                    messagebox.showinfo("Success", msg)
                    self.load_data()
                else:
                    messagebox.showerror("Error", msg)
            self.after(0, complete)
            
        threading.Thread(target=worker, daemon=True).start()