"""
TomeWeaver: GUI Launcher
------------------------
Entry point for the Desktop Application. Parses command-line arguments 
from .bat shortcuts and launches the CustomTkinter UI.
"""
import sys
import os
import ctypes
from pathlib import Path
import customtkinter as ctk
from ui.app import TomeWeaverApp
from config import ENGINE_CONFIG

# Hide the black terminal console on Windows
if os.name == 'nt':
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# Ensure runtime folders exist on the user's machine
from pathlib import Path
Path("adventures").mkdir(parents=True, exist_ok=True)
Path("configs/API_configs").mkdir(parents=True, exist_ok=True)


# Set global appearance and scaling for the entire application
ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(ENGINE_CONFIG.get("ui_scaling", 1.0))
ctk.set_window_scaling(ENGINE_CONFIG.get("ui_scaling", 1.0))

if __name__ == "__main__":
    startup_story = None
    if len(sys.argv) >= 2:
        adv_dir = Path(sys.argv[1]).resolve()
        adv_dir.mkdir(parents=True, exist_ok=True)
        startup_story = adv_dir.name

    # Boot the Graphical User Interface
    app = TomeWeaverApp(startup_story)
    app.mainloop()