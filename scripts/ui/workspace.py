"""
    TomeWeaver: Active Story Workspace
    ----------------------------------
    The main container for an actively loaded story. Holds the tab view 
    that lets the user switch between Story Mode, Console, and World Builder.
"""
import customtkinter as ctk
from ui.tab_console import ConsoleTab
from ui.tab_story import StoryTab
from ui.tab_codex import CodexTab  
from ui.tab_chapters import ChapterTab
from ui.tooltip import Tooltip
from ui.theme_utils import apply_workspace_chrome, resolve_theme


class WorkspaceFrame(ctk.CTkFrame):

    """
    Active Story Workspace
    """
    def __init__(self, parent, app, engine, folder_name=""):
        """Host story tabs (story, memory, codex, chapters, console) for one cartridge.

        Args:
            parent: Root application window.
            app: :class:`TomeWeaverApp` controller.
            engine: Active :class:`SandboxEngine` or :class:`CampaignEngine`.
            folder_name: Adventure directory name under ``adventures/``.
        """
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.engine = engine
        self.folder_name = folder_name # Store the exact string passed from Dashboard

       # --- Top Header ---
        header = ctk.CTkFrame(self)
        self.header_frame = header
        header.pack(fill="x", padx=10, pady=5)
        
        # Determine Mode and Color
        mode_str = str(self.engine.setup_data.get('mode', 'sandbox')).upper()
        mode_color = "#2196F3" if mode_str == "SANDBOX" else "#9C27B0"
        
        # Split into two labels so the Mode can be uniquely colored
        mode_lbl = ctk.CTkLabel(header, text=f"{mode_str}:", font=("Arial", 16, "bold"), text_color=mode_color)
        mode_lbl.pack(side="left", padx=(15, 5), pady=10)
        
        title_lbl = ctk.CTkLabel(header, text=engine.setup_data.get('title', 'Unknown'), font=("Arial", 16, "bold"))
        title_lbl.pack(side="left", pady=10)
        
        btn_close = ctk.CTkButton(header, text="Close Workspace", command=self.close_workspace, width=120, fg_color="#B71C1C", hover_color="#7F0000")
        btn_close.pack(side="right", padx=15)
        Tooltip(btn_close, "Safely save and return to the Dashboard.")
        
        # Combined Options Menu
        self.opt_var = ctk.StringVar(value="Options...")
        opt_menu = ctk.CTkOptionMenu(
            header, 
            variable=self.opt_var, 
            values=["Generate Recap", "Generate Missing Bridges", "Fork Thread (Slice Chapters)...", "Import Turns...", "Export Story", "Restart Story"], 
            width=200,
            command=self._handle_options_menu
        )
        opt_menu.pack(side="right", padx=10)

        # ONLY show Test Mode for Campaigns. Sandbox has no defined 'end' to test against.
        if self.engine.is_campaign:
            self.btn_test = ctk.CTkButton(header, text="▶︎ Auto-Play", command=self._toggle_test, width=90, fg_color="#4A4A4A", hover_color="#333333")
            self.btn_test.pack(side="right", padx=10)
            Tooltip(self.btn_test, "Autopilot: Automatically select the first choice until the game ends. Useful for stress-testing campaign goals.")

        # --- Tab Control ---
        self.tabs = ctk.CTkTabview(self, command=self._on_tab_change)
        self.tabview = self.tabs
        self.tabs.pack(fill="both", expand=True, padx=10, pady=5)

        self.t_story = self.tabs.add("Story Mode")
        self.t_console = self.tabs.add("Developer Console")
        
        if self.engine.is_universe_thread:
            self.t_univ = self.tabs.add("Universe")
            
        self.t_codex = self.tabs.add("Story World")
        self.t_memory = self.tabs.add("Memory & Lore") 

        if self.engine.is_campaign:
            self.t_chapters = self.tabs.add("Chapter Outline")

        # --- INTEGRITY WARNING POPUP ---
        if getattr(self.engine, 'integrity_warnings', []):
            # Wait half a second for the UI to fully draw before popping the modal
            self.after(500, self._show_integrity_warnings)
            

        # --- Initialize Tabs (Lazy Loading) ---
        def safe_status_update(msg):
            if hasattr(self, 'story_tab') and self.story_tab is not None:
                self.after(0, lambda: self.story_tab.status_var.set(msg))

        # Always load Console first to catch stdout
        self.console_tab = ConsoleTab(self.t_console, self.engine, status_callback=safe_status_update) 
        self.console_tab.pack(fill="both", expand=True)
        
        # Always load Story Mode as it is the default view
        self.story_tab = StoryTab(self.t_story, self.engine, self)
        self.story_tab.pack(fill="both", expand=True)
        
        # DEFER HEAVY UI TABS (Lazy Loading)
        self.univ_tab = None
        self.codex_tab = None
        self.memory_tab = None
        self.chapters_tab = None

        self._active_theme = resolve_theme()
        self.apply_visual_theme(self._active_theme)

    def apply_visual_theme(self, theme=None):
        """Paint workspace chrome + story card from the global theme preset."""
        if theme is None:
            theme = resolve_theme()
        self._active_theme = theme
        apply_workspace_chrome(self, theme)
        if hasattr(self, "story_tab") and self.story_tab is not None:
            self.story_tab.apply_theme(theme)

    def _show_integrity_warnings(self):
        """Displays a modal listing data corruptions caught and healed by the engine on boot."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Data Integrity Warning")
        dialog.geometry("650x400")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="⚠️ Data Corruption Healed", font=("Arial", 18, "bold"), text_color="#FF9800").pack(pady=(20, 10))
        ctk.CTkLabel(dialog, text="The engine detected invalid or hallucinated data in your memory files during boot. The corrupted entries have been safely quarantined and removed to prevent crashes.", wraplength=600).pack(padx=20, pady=(0, 15))

        box = ctk.CTkTextbox(dialog, wrap="word", font=("Consolas", 13), fg_color="#1A1A1B", text_color="#FFCA28")
        box.pack(fill="both", expand=True, padx=20, pady=5)
        
        for w in self.engine.integrity_warnings:
            box.insert("end", f"• {w}\n")
            
        box.configure(state="disabled")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        ctk.CTkButton(btn_frame, text="Acknowledge", font=("Arial", 14, "bold"), fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack()
        
    def close_workspace(self):
        """Safely shuts down the workspace and returns to the dashboard context."""
        self.console_tab.restore_stdout()
        
        from config import INSTANCE_CONFIG, ROOT_DIR
        import json
        INSTANCE_CONFIG["last_active_story"] = ""
        try:
            with open(ROOT_DIR / "configs" / "instance_config.json", "w", encoding="utf-8") as f:
                json.dump(INSTANCE_CONFIG, f, indent=4)
        except Exception:
            pass
            
        self.app.open_dashboard()
        
    def _on_tab_change(self):
        """Triggers instantly whenever the user clicks a different tab at the top. Lazy-loads UI heavy tabs and resets scrollbars."""
        target = self.tabs.get()
        
        if target == "Story Mode" and self.story_tab is not None:
            self.story_tab.refresh_timeline()
            
        elif target == "Universe":
            if self.univ_tab is None:
                from ui.tab_universe import UniverseTab
                self.univ_tab = UniverseTab(self.t_univ, self.engine)
                self.univ_tab.pack(fill="both", expand=True)
            # Reset both scrollable frames in the Universe Tab
            self.after(10, lambda: self.univ_tab.tab_core.winfo_children()[1]._parent_canvas.yview_moveto(0.0))
            if hasattr(self.univ_tab, 'nav_frame'): self.after(10, lambda: self.univ_tab.nav_frame._parent_canvas.yview_moveto(0.0))
                
        elif target == "Story World":
            if self.codex_tab is None:
                from ui.tab_codex import CodexTab
                self.codex_tab = CodexTab(self.t_codex, self.engine)
                self.codex_tab.pack(fill="both", expand=True)
            # Reset both scrollable frames in the Story World Tab
            if hasattr(self.codex_tab, 'core_scroll_frame'): self.after(10, lambda: self.codex_tab.core_scroll_frame._parent_canvas.yview_moveto(0.0))
            if hasattr(self.codex_tab, 'nav_frame'): self.after(10, lambda: self.codex_tab.nav_frame._parent_canvas.yview_moveto(0.0))
                
        elif target == "Memory & Lore":
            if self.memory_tab is None:
                from ui.tab_memory import MemoryTab
                self.memory_tab = MemoryTab(self.t_memory, self.engine)
                self.memory_tab.pack(fill="both", expand=True)
            else:
                engine_save_time = getattr(self.engine, 'last_save_time', 0)
                if engine_save_time > self.memory_tab._last_render_time:
                    self.memory_tab._refresh_nav()
            # Reset all scrollable frames in the Memory Tab
            if hasattr(self.memory_tab, 'nav_frame'): self.after(10, lambda: self.memory_tab.nav_frame._parent_canvas.yview_moveto(0.0))
            if hasattr(self.memory_tab, 'editor_frame'): self.after(10, lambda: self.memory_tab.editor_frame._parent_canvas.yview_moveto(0.0))
                    
        elif target == "Chapter Outline":
            if self.chapters_tab is None:
                from ui.tab_chapters import ChapterTab
                self.chapters_tab = ChapterTab(self.t_chapters, self.engine)
                self.chapters_tab.pack(fill="both", expand=True)
            # Reset both scrollable frames in the Chapters Tab
            if hasattr(self.chapters_tab, 'nav_frame'): self.after(10, lambda: self.chapters_tab.nav_frame._parent_canvas.yview_moveto(0.0))
            if hasattr(self.chapters_tab, 'editor_frame'): self.after(10, lambda: self.chapters_tab.editor_frame._parent_canvas.yview_moveto(0.0))
            
    # ---------------------------------------------------------
    # WORKSPACE UTILITIES (Recap & Export)
    # ---------------------------------------------------------

    def _handle_options_menu(self, choice):
        """Routes actions from the combined workspace options dropdown."""
        self.opt_var.set("Options...") # Reset label immediately
        if choice == "Generate Recap":
            self._generate_recap()
        elif choice == "Generate Missing Bridges":
            self._generate_missing_bridges()
        elif choice == "Import Turns...":
            self._show_import_dialog()
        elif choice == "Export Story":
            self._export_dialog()
        elif choice == "Fork Thread (Slice Chapters)...":
            self._show_slice_dialog()
        elif choice == "Restart Story":
            self._restart_story()

    def _generate_missing_bridges(self):
        """Manually triggers the background worker to patch all missing narrative bridges."""
        from tkinter import messagebox
        
        if len(self.engine.history) < 2:
            messagebox.showinfo("Narrative Bridges", "Not enough history to generate bridges.")
            return

        warn_msg = (
            "This will scan your entire history and ask the AI to generate "
            "missing narrative transitions between your actions and the prose.\n\n"
            "This may take several minutes depending on the length of your story, "
            "and will consume API tokens. Proceed?"
        )
        if not messagebox.askyesno("Generate Missing Bridges", warn_msg):
            return

        # Lock the UI visually to indicate processing
        if hasattr(self, 'story_tab'):
            self.story_tab._lock_ui("Generating missing bridges... Please wait.")
        else:
            self.winfo_toplevel().configure(cursor="watch")

        def worker():
            # Call the existing backend method (silent=False prints progress to the Developer Console tab)
            self.engine.novelize_history(silent=False)
            
            def update_ui():
                # Unlock and refresh the UI safely
                if hasattr(self, 'story_tab'):
                    self.story_tab._unlock_ui("Ready.")
                    self.story_tab.refresh_timeline()
                else:
                    self.winfo_toplevel().configure(cursor="")
                    
                messagebox.showinfo("Complete", "Finished generating missing narrative bridges.\nCheck the Developer Console for details.")
                
            self.after(0, update_ui)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _generate_recap(self):
        """Asks the LLM to generate a summary of the adventure on a background thread."""
        if not self.engine.history:
            messagebox.showinfo("Recap", "The story hasn't started yet!")
            return
            
        import threading
        from tkinter import messagebox
        
        # Change status in the StoryTab if it's active
        if hasattr(self, 'story_tab'):
            self.story_tab.status_var.set("Generating recap, please wait...")
            
        def worker():
            recap_text = self.engine.request_recap()
            self.after(0, lambda: self._show_recap_modal(recap_text))
            
        threading.Thread(target=worker, daemon=True).start()

    def _show_recap_modal(self, text):
        """Spawns a reading dialog when the recap generation completes."""
        if hasattr(self, 'story_tab'):
            self.story_tab.status_var.set("Ready.")
            
        dialog = ctk.CTkToplevel(self)
        dialog.title("The Story So Far...")
        dialog.geometry("700x600")
        dialog.attributes("-topmost", True)
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())
        
        box = ctk.CTkTextbox(dialog, wrap="word", font=("Georgia", 15))
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkButton(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 20))

            
    def _export_dialog(self):
        """Opens a configuration dialog allowing the user to select their export format."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Export Storybook")
        dialog.geometry("350x250")
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Select Format:", font=("Arial", 14, "bold")).pack(pady=(20, 5))
        fmt_var = ctk.StringVar(value="3. HTML (Web Book)")
        ctk.CTkOptionMenu(dialog, variable=fmt_var, values=["1. TXT (Plain Text)", "2. MD (Markdown)", "3. HTML (Web Book)"]).pack(pady=5)

        nov_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(dialog, text="Use Seamless Novelization", variable=nov_var).pack(pady=20)

        def on_export():
            from tkinter import filedialog, messagebox
            
            fmt_choice = int(fmt_var.get()[0]) # 1, 2, or 3
            
            # Determine extension based on choice
            ext_map = {1: (".txt", "Text File"), 2: (".md", "Markdown File"), 3: (".html", "HTML Web Book")}
            ext, label = ext_map[fmt_choice]

            # 1. Open Cross-Platform Native Save Dialog
            target_path = filedialog.asksaveasfilename(
                title="Save Storybook",
                initialfile=f"{self.engine.setup_data.get('title', 'Adventure')}{ext}",
                defaultextension=ext,
                filetypes=[(label, f"*{ext}"), ("All Files", "*.*")]
            )

            # 2. Proceed only if the user didn't cancel the dialog
            if target_path:
                try:
                    # We pass the custom path to the exporter
                    path = self.engine.export_adventure(fmt_choice, nov_var.get(), custom_path=target_path)
                    messagebox.showinfo("Success", f"Story exported successfully!")
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Export Error", f"Failed to write file: {e}")

        ctk.CTkButton(dialog, text="Export", fg_color="#4CAF50", hover_color="#388E3C", command=on_export).pack(pady=10)
        
    def _restart_story(self):
        """Wipes history, resets chapters, and allows granular wiping of Long-Term Memory."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Restart Adventure")
        dialog.geometry("450x400")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="⚠️ Restart Adventure", font=("Arial", 18, "bold"), text_color="#D32F2F").pack(pady=(20, 10))
        ctk.CTkLabel(dialog, text="This will permanently delete all gameplay turns, choices, and the session log. You will return to Turn 0.", wraplength=400).pack(padx=20, pady=(0, 10))
        ctk.CTkLabel(dialog, text="How should the Long-Term Memory (Lore Bible) be handled?", font=("Arial", 12, "bold"), text_color="#00ACC1").pack(pady=(10, 5))

        # Default to Nuclear Wipe for Campaigns to prevent premature goal completion
        default_mem_action = "nuclear" if self.engine.is_campaign else "wipe_ai"
        v_mem = ctk.StringVar(value=default_mem_action)
        
        rb1 = ctk.CTkRadioButton(dialog, text="Wipe AI Events (Keep Names & Author Notes)", variable=v_mem, value="wipe_ai")
        rb1.pack(anchor="w", padx=40, pady=10)
        Tooltip(rb1, "Deletes the chronological events the AI tracked, but keeps all the Characters/Locations and any notes you manually typed.")
        
        rb2 = ctk.CTkRadioButton(dialog, text="Nuclear Wipe (Delete Everything)", variable=v_mem, value="nuclear")
        rb2.pack(anchor="w", padx=40, pady=10)
        Tooltip(rb2, "Total reset. Deletes all Characters, Locations, Artifacts, and Factions. A completely blank slate.")
        
        rb3 = ctk.CTkRadioButton(dialog, text="Do Not Touch Memory", variable=v_mem, value="keep")
        rb3.pack(anchor="w", padx=40, pady=10)
        Tooltip(rb3, "Start at Turn 1, but the AI will still remember everything that happened in the previous playthrough.")

        def apply_restart():
            from logger import log_event
            log_event(self.engine.adv_dir, "Command: RESTART ADVENTURE")
            
            # 1. Wipe History and Bookmarks
            self.engine.history.clear()
            from config import INSTANCE_CONFIG
            INSTANCE_CONFIG.get("story_bookmarks", {}).pop(self.folder_name, None)
            
            # 2. Reset Chapters (Completely rebuild the state tracker)
            if self.engine.is_campaign:
                outline = self.engine.setup_data.get("plot_outline", [])
                first_chap = outline[0] if outline else {}
                
                # Build the fresh objectives array for Chapter 1
                objs = []
                for i, o in enumerate(first_chap.get("objectives", [])):
                    o_copy = o.copy()
                    o_copy["status"] = "ACTIVE" if i == 0 else "LOCKED"
                    objs.append(o_copy)
                    
                self.engine.chapters = [{
                    "chapter_number": 1,
                    "title": first_chap.get("title", "Chapter 1"),
                    "start_turn": 1, 
                    "end_turn": None,
                    "objectives": objs
                }]
            else:
                self.engine.chapters = [self.engine.chapters[0]]
                self.engine.chapters[0]["start_turn"] = 1
                self.engine.chapters[0]["end_turn"] = None
                
           # 3. Handle Memory (STRICTLY LOCAL SCOPE)
            mode = v_mem.get()
            self.engine.memory["plot_ledger"] = []
            self.engine.memory["chapter_ledger"] = []
            
            ledgers = ["character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"]
            
            if mode == "nuclear":
                # Nuclear Restart ONLY wipes the LOCAL bucket
                for l in ledgers:
                    self.engine.memory[l]["local"] = {}
                self.engine.memory["aliases"]["local"] = {l: {} for l in ledgers}
                # Also reset local visibility states for global characters
                self.engine.memory["global_states"] = {}
                
            elif mode == "wipe_ai":
                # Wipe events but keep notes/traits in the LOCAL bucket
                for l in ledgers:
                    for k in self.engine.memory[l].get("local", {}): 
                        self.engine.memory[l]["local"][k]["ledger"] = []
                # Also reset local visibility states for global characters
                self.engine.memory["global_states"] = {}
            
            # 4. Flush the session log file
            log_file = self.engine.adv_dir / "session_log.txt"
            if log_file.exists():
                try: log_file.unlink() 
                except Exception: pass

            self.engine.save_state()
            dialog.destroy()
            
            # 5. Redraw the UI
            if hasattr(self, 'story_tab'):
                self.story_tab.refresh_timeline()
            if hasattr(self, 'memory_tab'):
                self.memory_tab.active_selection.set("PLOT_LEDGER")
                self.memory_tab._refresh_nav()
                
            from tkinter import messagebox
            messagebox.showinfo("Reset Complete", "The story has been reverted to Turn 0.\n\nYou may edit your world in the World Builder before clicking Start Adventure.")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Restart Game", width=120, font=("Arial", 14, "bold"), fg_color="#B71C1C", hover_color="#7F0000", command=apply_restart).pack(side="right", padx=10)
            
    def _toggle_test(self):
        """Switches autopilot on or off."""
        is_active = not self.engine.is_test_mode
        self.engine.toggle_test_mode(is_active)
        
        if is_active:
            self.btn_test.configure(text="🛑 Stop Auto-Play", fg_color="#D32F2F", hover_color="#9A0007")
            # If we are in Story Mode, trigger the first auto-step immediately
            if self.tabs.get() == "Story Mode" and hasattr(self, 'story_tab'):
                # Calling _unlock_ui forces the Autopilot hook to immediately evaluate the active card
                self.story_tab._unlock_ui("Autopilot engaged. Starting sequence...")
        else:
            self.btn_test.configure(text="▶︎ Auto-Play", fg_color="#4A4A4A", hover_color="#333333")
            
            
    def _show_import_dialog(self):
        """Spawns a modal allowing the user to paste raw text to be parsed into turns."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Import External Story")
        dialog.geometry("800x650")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Mass Import Turns", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(15, 5))
        
        help_text = (
            "Paste a linear story from MS Word, AI Dungeon, or ChatGPT below.\n"
            "The engine will automatically split it into Turn Cards. Use a chevron '>' at the start of a line to indicate a player action.\n\n"
            "Example:\n"
            "> walk in the cavern\n"
            "The knight walked into the dark cavern.\n"
            "> Light the torch\n"
            "The cavern illuminated, revealing a goblin horde!"
        )
        ctk.CTkLabel(dialog, text=help_text, wraplength=700, text_color="gray", justify="left").pack(padx=20, pady=(0, 10))

        # Anchor Context Info
        insert_idx = self.story_tab.current_turn_idx if hasattr(self, 'story_tab') and self.story_tab else len(self.engine.history) - 1
        t_num = self.engine.history[insert_idx].get("turn", 0) if insert_idx >= 0 and self.engine.history else 0
        ctk.CTkLabel(dialog, text=f"Data will be appended immediately after Turn {t_num}.", font=("Arial", 12, "bold"), text_color="#F57C00").pack(anchor="w", padx=20)

        box = ctk.CTkTextbox(dialog, wrap="word", font=("Arial", 14))
        box.pack(fill="both", expand=True, padx=20, pady=10)

        def on_import():
            raw_text = box.get("1.0", "end").strip()
            if not raw_text: return
            
            dialog.destroy()
            
            if hasattr(self, 'story_tab') and self.story_tab:
                self.story_tab._lock_ui("Parsing and importing turns...")
                
            def worker():
                success, msg = self.engine.import_turns(raw_text, insert_idx)
                
                def update_ui():
                    from tkinter import messagebox
                    
                    if success:
                        messagebox.showinfo("Import Successful", msg)
                        if hasattr(self, 'story_tab') and self.story_tab:
                            self.story_tab.refresh_timeline(go_to_last=True)
                            
                        # --- CRITICAL RAG TRIGGER ---
                        # Because we just injected bulk history, we almost certainly crossed a chunk threshold.
                        # We trigger the compiler silently in the background!
                        def on_progress(current, total, s_turn=None, e_turn=None):
                            if current == "Seeding": stat = "Extracting Base Lore..."
                            elif current == "Condensing": stat = f"{total}..."
                            elif current == "Reconciling": stat = "Merging duplicates..."
                            elif current == "Syncing": stat = "Recalculating Timestamps..."
                            else: stat = f"Processing Chunk {current}/{total}..."
                            if hasattr(self, 'story_tab') and self.story_tab:
                                self.after(0, lambda: self.story_tab.status_var.set(f"Background Task: {stat}"))
                                
                        def on_complete(s, m):
                            if hasattr(self, 'story_tab') and self.story_tab:
                                self.after(0, lambda: self.story_tab.status_var.set("Ready."))

                        self.engine._trigger_memory_compilation(progress_callback=on_progress, completion_callback=on_complete)
                    else:
                        if hasattr(self, 'story_tab') and self.story_tab:
                            self.story_tab._unlock_ui("Ready.")
                        messagebox.showerror("Import Failed", msg)
                        
                self.after(0, update_ui)
                
            import threading
            threading.Thread(target=worker, daemon=True).start()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left")
        ctk.CTkButton(btn_frame, text="Import & Splice Timeline", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=on_import).pack(side="right")

        
    def _show_slice_dialog(self):
        """Spawns the checklist modal to extract specific chapters into a new thread."""
        if not self.engine.chapters or len(self.engine.history) == 0:
            messagebox.showinfo("Fork Thread", "You need to play some turns before you can slice the timeline!")
            return
            
        dialog = ctk.CTkToplevel(self)
        dialog.title("Fork Timeline Thread")
        dialog.geometry("600x550")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        ctk.CTkLabel(dialog, text="Extract Chapters to New Thread", font=("Arial", 18, "bold"), text_color="#00ACC1").pack(pady=(15, 5))
        ctk.CTkLabel(dialog, text="Select the chapters you want to extract. They will be seamlessly glued together into a brand new, sequential story inside this folder's parent directory.", wraplength=500, text_color="gray").pack(pady=(0, 15))

        # --- Details Form ---
        f_top = ctk.CTkFrame(dialog, fg_color="transparent")
        f_top.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(f_top, text="New Thread Title:", font=("Arial", 12, "bold")).pack(side="left")
        v_title = ctk.StringVar(value=f"{self.engine.setup_data.get('title')} (Fork)")
        ctk.CTkEntry(f_top, textvariable=v_title, font=("Arial", 14), width=250).pack(side="left", padx=10)
        
        ctk.CTkLabel(f_top, text="Author:", font=("Arial", 12, "bold")).pack(side="left")
        v_author = ctk.StringVar(value=self.engine.setup_data.get('author', 'Anonymous'))
        ctk.CTkEntry(f_top, textvariable=v_author, font=("Arial", 14), width=100).pack(side="left", padx=10)

        # --- Chapter Checklist ---
        scroll = ctk.CTkScrollableFrame(dialog, fg_color="#2B2B2B")
        scroll.pack(fill="both", expand=True, padx=20, pady=10)

        checkbox_vars = {}
        for c in self.engine.chapters:
            if c.get("start_turn") is None: continue # Skip unplayed chapters
                
            c_num = c.get("chapter_number")
            c_title = c.get("title", f"Chapter {c_num}")
            t_start = c.get("start_turn")
            t_end = c.get("end_turn", "Ongoing")
            
            # Find the POV for this chapter to help the user choose
            c_pov = "Unknown POV"
            for t in self.engine.history:
                if t.get("turn") == t_start:
                    c_pov = t.get("pov_character", "Unknown POV")
                    break

            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            var = ctk.BooleanVar(value=False)
            checkbox_vars[c_num] = var
            
            lbl_text = f"Chapter {c_num}: {c_title}  (Turns {t_start} - {t_end}) | {c_pov}"
            ctk.CTkCheckBox(row, text=lbl_text, variable=var, font=("Arial", 13)).pack(anchor="w", padx=10, pady=5)

        def on_confirm():
            selected = [c_num for c_num, var in checkbox_vars.items() if var.get()]
            if not selected:
                messagebox.showwarning("Error", "You must select at least one chapter to extract.")
                return
                
            new_title = v_title.get().strip()
            if not new_title: return
            
            from api import TomeWeaverAPI
            success, msg = TomeWeaverAPI.slice_thread(self.folder_name, selected, new_title, v_author.get().strip())
            
            if success:
                dialog.destroy()
                messagebox.showinfo("Fork Successful", f"Thread successfully forked!\n\nThe new story is located at:\n{msg}")
                
                # CRITICAL REFRESH: The slicing operation modified the Source story's history.json
                # and chapters.json on disk. We must completely close and reload the current workspace 
                # to prevent the UI's old RAM state from corrupting the newly healed files.
                self.app.clear_container()
                self.app.open_workspace(self.folder_name, target_tab="Story Mode")
                
            else:
                messagebox.showerror("Error", f"Failed to fork thread: {msg}")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#D32F2F", hover_color="#9A0007", command=dialog.destroy).pack(side="left")
        ctk.CTkButton(btn_frame, text="Extract & Fork", width=140, font=("Arial", 14, "bold"), fg_color="#1F6AA5", hover_color="#144870", command=on_confirm).pack(side="right")