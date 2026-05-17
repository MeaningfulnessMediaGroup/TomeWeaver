import customtkinter as ctk
from ui.tab_console import ConsoleTab
from ui.tab_story import StoryTab
from ui.tab_codex import CodexTab  
from ui.tab_chapters import ChapterTab
from ui.tooltip import Tooltip


class WorkspaceFrame(ctk.CTkFrame):
    def __init__(self, parent, app, engine):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.engine = engine

        # --- Top Header ---
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=10, pady=5)
        
        title_lbl = ctk.CTkLabel(header, text=f"Playing: {engine.setup_data.get('title', 'Unknown')}", font=("Arial", 16, "bold"))
        title_lbl.pack(side="left", padx=15, pady=10)
        
        btn_close = ctk.CTkButton(header, text="Close Workspace", command=self.close_workspace, width=120, fg_color="#B71C1C", hover_color="#7F0000")
        btn_close.pack(side="right", padx=15)
        Tooltip(btn_close, "Safely save and return to the Dashboard.")
        
        btn_export = ctk.CTkButton(header, text="Export Story", command=self._export_dialog, width=100, fg_color="#4CAF50", hover_color="#388E3C")
        btn_export.pack(side="right", padx=10)
        Tooltip(btn_export, "Convert your played adventure into a readable TXT, MD, or HTML book.")
        
        btn_recap = ctk.CTkButton(header, text="Generate Recap", command=self._generate_recap, width=120, fg_color="#FF9800", hover_color="#F57C00")
        btn_recap.pack(side="right", padx=10)
        Tooltip(btn_recap, "Ask the AI to read your history and generate a 'Story So Far' summary.")

        # --- Tab Control ---
        self.tabs = ctk.CTkTabview(self, command=self._on_tab_change)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=5)

        self.t_story = self.tabs.add("Story Mode")
        self.t_console = self.tabs.add("Developer Console")
        self.t_codex = self.tabs.add("World Builder")
        
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
        
        # Stage 4: Chapter Outline (Only visible in Campaign Mode)
        if self.engine.is_campaign:
            self.chapters_tab = ChapterTab(self.t_chapters, self.engine)
            self.chapters_tab.pack(fill="both", expand=True)

    def close_workspace(self):
        """Safely shuts down the workspace and returns to the dashboard."""
        # CRITICAL: We must release the stdout redirector, or the app will crash 
        # trying to print to a destroyed widget when returning to the dashboard.
        self.console_tab.restore_stdout()
        self.app.open_dashboard()
        
    # ---------------------------------------------------------
    # WORKSPACE UTILITIES (Recap & Export)
    # ---------------------------------------------------------

    def _generate_recap(self):
        """Asks the LLM to generate a summary of the adventure."""
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
        if hasattr(self, 'story_tab'):
            self.story_tab.status_var.set("Ready.")
            
        dialog = ctk.CTkToplevel(self)
        dialog.title("The Story So Far...")
        dialog.geometry("700x600")
        dialog.attributes("-topmost", True)
        
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
        """Opens a dialog to configure and export the story."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Export Storybook")
        dialog.geometry("350x250")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Select Format:", font=("Arial", 14, "bold")).pack(pady=(20, 5))
        fmt_var = ctk.StringVar(value="3. HTML (Web Book)")
        ctk.CTkOptionMenu(dialog, variable=fmt_var, values=["1. TXT (Plain Text)", "2. MD (Markdown)", "3. HTML (Web Book)"]).pack(pady=5)

        nov_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(dialog, text="Use Seamless Novelization", variable=nov_var).pack(pady=20)

        def on_export():
            fmt_choice = int(fmt_var.get()[0]) # Extract the 1, 2, or 3
            try:
                path = self.engine.export_adventure(fmt_choice, nov_var.get())
                from tkinter import messagebox
                messagebox.showinfo("Success", f"Story exported successfully to:\n{path}")
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Export Failed", str(e))
            dialog.destroy()

        ctk.CTkButton(dialog, text="Export", fg_color="#4CAF50", hover_color="#388E3C", command=on_export).pack(pady=10)