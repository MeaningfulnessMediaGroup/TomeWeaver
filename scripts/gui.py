"""
TomeWeaver: GUI Launcher
------------------------
Entry point for the Desktop Application.
"""
import sys
import os
import ctypes

# --- CRITICAL FAILSAFE FOR --noconsole MODE ---
# In PyInstaller --noconsole mode, sys.stdout and sys.stderr are None.
# Any print() call during the import/loading phase will crash the app.
# We redirect them to a dummy "Null" stream immediately to prevent crashes.
class NullStream:
    def write(self, text): pass
    def flush(self): pass

if sys.stdout is None: sys.stdout = NullStream()
if sys.stderr is None: sys.stderr = NullStream()
# ----------------------------------------------

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