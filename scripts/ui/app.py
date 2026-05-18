"""
    TomeWeaver: Root Application
    ----------------------------
    The top-level window manager for the application. Controls window scaling,
    saved geometries, and handles switching between the Dashboard and Active Workspaces.
"""
import json
import customtkinter as ctk
from tkinter import messagebox
from pathlib import Path
from api import TomeWeaverAPI
from config import create_boilerplate_files, ENGINE_CONFIG, ROOT_DIR
from ui.dashboard import DashboardFrame


class TomeWeaverApp(ctk.CTk):

    """
    Root Application
    """
    def __init__(self, startup_story=None):
        super().__init__()

        self.title("TomeWeaver")
        self.minsize(900, 600)
        
        # --- RESTORE SAVED WINDOW GEOMETRY ---
        saved_geom = ENGINE_CONFIG.get("window_geometry", "1100x750")
        saved_state = ENGINE_CONFIG.get("window_state", "normal")
        
        # Apply Width, Height, and X/Y Screen Coordinates
        self.geometry(saved_geom)
        
        # Apply Maximized state safely (Cross-platform compatibility)
        if saved_state == "zoomed":
            try:
                self.state("zoomed") # Windows
            except Exception:
                try:
                    self.attributes("-zoomed", True) # Linux X11
                except Exception:
                    pass

        # Hook the OS 'X' close button to our custom save method
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self.active_frame = None

        self.active_frame = None

        if startup_story:
            self.open_workspace(startup_story)
        else:
            # Auto-Resume last played session
            last_story = ENGINE_CONFIG.get("last_active_story", "")
            if last_story and (Path("adventures") / last_story).exists():
                self.open_workspace(last_story)
            else:
                self.open_dashboard()

    def _save_config_silently(self):
        """Helper to safely dump global config to disk."""
        try:
            with open(ROOT_DIR / "configs" / "engine_config.json", "w", encoding="utf-8") as f:
                json.dump(ENGINE_CONFIG, f, indent=4)
        except Exception:
            pass

    def _on_closing(self):
        """Fires exactly when the user clicks the X to close the app. Saves window state."""
        current_state = self.state()
        
        if current_state == "iconic":
            current_state = "normal"
            
        ENGINE_CONFIG["window_state"] = current_state
        ENGINE_CONFIG["window_geometry"] = self.geometry()
        
        self._save_config_silently()
        self.destroy()
        
    def clear_container(self):
        """Destroys the current active view to make room for a new one."""
        if self.active_frame is not None:
            self.active_frame.destroy()

    def open_dashboard(self):
        """Loads the Screen 1: Dashboard."""
        self.clear_container()
        self.active_frame = DashboardFrame(self.container, self)
        self.active_frame.pack(fill="both", expand=True)

    def open_workspace(self, folder_name):
        """Loads the Screen 2: Workspace for a specific story."""
        setup_file = Path("adventures") / folder_name / "setup.json"
        
        if not setup_file.exists():
            self._prompt_boilerplate_initialization(folder_name)
            return

        try:
            engine = TomeWeaverAPI.load_engine(folder_name)
            self.clear_container()
            
            from ui.workspace import WorkspaceFrame
            self.active_frame = WorkspaceFrame(self.container, self, engine)
            self.active_frame.pack(fill="both", expand=True)
            
            # Save this workspace as the active session for next boot
            ENGINE_CONFIG["last_active_story"] = folder_name
            self._save_config_silently()
            
        except Exception as e:
            # If the engine fails to load, ensure we don't trap the user in a crash loop
            ENGINE_CONFIG["last_active_story"] = ""
            self._save_config_silently()
            
            messagebox.showerror("Engine Error", f"Failed to load story: {e}")
            self.open_dashboard()
            
    def _prompt_boilerplate_initialization(self, folder_name):
        """GUI replacement for the console-based setup wizard in main.py."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Initialize New Folder")
        dialog.geometry("400x250")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=f"Folder '{folder_name}' is empty.\nHow would you like to initialize it?", font=("Arial", 14)).pack(pady=20)
        
        mode_var = ctk.StringVar(value="sandbox")
        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack()
        ctk.CTkRadioButton(frame, text="Sandbox (Open-World)", variable=mode_var, value="sandbox").pack(side="left", padx=10)
        ctk.CTkRadioButton(frame, text="Campaign (Plot-Driven)", variable=mode_var, value="campaign").pack(side="left", padx=10)

        def on_init():
            create_boilerplate_files(Path("adventures") / folder_name, mode_var.get())
            dialog.destroy()
            messagebox.showinfo("Success", "Files created! Please edit setup.json before playing.")
            self.open_dashboard()

        ctk.CTkButton(dialog, text="Initialize", command=on_init).pack(pady=30)