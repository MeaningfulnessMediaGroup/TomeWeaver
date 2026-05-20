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


class WorkspaceFrame(ctk.CTkFrame):

    """
    Active Story Workspace
    """
    def __init__(self, parent, app, engine, folder_name=""):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.engine = engine
        self.folder_name = folder_name # Store the exact string passed from Dashboard

       # --- Top Header ---
        header = ctk.CTkFrame(self)
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
            values=["Generate Recap", "Generate Missing Bridges", "Export Story", "Restart Story"], 
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
        self.tabs.pack(fill="both", expand=True, padx=10, pady=5)

        self.t_story = self.tabs.add("Story Mode")
        self.t_console = self.tabs.add("Developer Console")
        self.t_codex = self.tabs.add("World Builder")
        self.t_memory = self.tabs.add("Memory & Lore") 
        
        if self.engine.is_campaign:
            self.t_chapters = self.tabs.add("Chapter Outline")

        # --- Initialize Tabs ---
        # We create a thread-safe callback to pass engine prints to the UI status bar
        def safe_status_update(msg):
            if hasattr(self, 'story_tab'):
                # Must use after(0) because stdout writes happen in a background thread
                self.after(0, lambda: self.story_tab.status_var.set(msg))

        # Initialize console first so it catches stdout immediately
        self.console_tab = ConsoleTab(self.t_console, self.engine, status_callback=safe_status_update) 
        self.console_tab.pack(fill="both", expand=True)
        
        self.story_tab = StoryTab(self.t_story, self.engine, self)
        self.story_tab.pack(fill="both", expand=True)

        # Stage 3: The World Builder
        self.codex_tab = CodexTab(self.t_codex, self.engine)
        self.codex_tab.pack(fill="both", expand=True)
        
        # Stage 4: Memory & Lore Viewer
        from ui.tab_memory import MemoryTab
        self.memory_tab = MemoryTab(self.t_memory, self.engine)
        self.memory_tab.pack(fill="both", expand=True)
        
        # Stage 5: Chapter Outline (Only visible in Campaign Mode)
        if self.engine.is_campaign:
            self.chapters_tab = ChapterTab(self.t_chapters, self.engine)
            self.chapters_tab.pack(fill="both", expand=True)

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
            
        # Tell the app to open the dashboard with NO overrides. Let the App handle the memory.
        self.app.open_dashboard()
        
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
        elif choice == "Export Story":
            self._export_dialog()
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
        
    def _on_tab_change(self):
        """Triggers instantly whenever the user clicks a different tab at the top."""
        if self.tabs.get() == "Story Mode" and hasattr(self, 'story_tab'):
            # Instantly re-evaluate setup.json and redraw the buttons/UI
            self.story_tab.refresh_timeline()
            
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
        """Wipes history and returns the adventure to the Start Button state."""
        from tkinter import messagebox
        warn_msg = (
            "Are you sure you want to RESTART this adventure?\n\n"
            "This will permanently DELETE all current turns, choices, and the session log. "
            "You will be returned to the very beginning. This action cannot be undone!"
        )
        if messagebox.askyesno("Confirm Restart", warn_msg, icon='warning'):
            # 1. Wipe the backend state but do NOT generate a new turn
            from logger import log_event
            log_event(self.engine.adv_dir, "Command: RESTART ADVENTURE")
            
            self.engine.history.clear()
            
            # Reset Chapter bounds depending on Mode
            if self.engine.is_campaign:
                for c in self.engine.chapters:
                    c["start_turn"] = 1 if c["chapter_number"] == 1 else None
                    c["end_turn"] = None
            else:
                self.engine.chapters = [self.engine.chapters[0]]
                self.engine.chapters[0]["start_turn"] = 1
                self.engine.chapters[0]["end_turn"] = None
            
            # Flush the session log file
            log_file = self.engine.adv_dir / "session_log.txt"
            if log_file.exists():
                try: log_file.unlink() 
                except Exception: pass

            self.engine.save_state()
            
            # 2. Redraw the UI to show the big "Start Adventure" button
            if hasattr(self, 'story_tab'):
                self.story_tab.refresh_timeline()
            
            messagebox.showinfo("Reset Complete", "The story has been reverted. You may edit your world in the World Builder before clicking Start Adventure.")
            
            
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
            