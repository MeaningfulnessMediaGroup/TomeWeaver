import customtkinter as ctk
from tkinter import messagebox
from pathlib import Path
from api import TomeWeaverAPI
from config import create_boilerplate_files
from ui.dashboard import DashboardFrame

class TomeWeaverApp(ctk.CTk):
    def __init__(self, startup_story=None):
        super().__init__()

        self.title("TomeWeaver")
        self.geometry("1100x750")
        self.minsize(900, 600)

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self.active_frame = None

        if startup_story:
            self.open_workspace(startup_story)
        else:
            self.open_dashboard()

    def clear_container(self):
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
        
        # --- THE BOILERPLATE SAFETY NET (Inherited from main.py) ---
        if not setup_file.exists():
            self._prompt_boilerplate_initialization(folder_name)
            return

        try:
            # Initialize the engine
            engine = TomeWeaverAPI.load_engine(folder_name)
            
            self.clear_container()
            
            # Load the actual Workspace
            from ui.workspace import WorkspaceFrame
            self.active_frame = WorkspaceFrame(self.container, self, engine)
            self.active_frame.pack(fill="both", expand=True)
            
        except Exception as e:
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