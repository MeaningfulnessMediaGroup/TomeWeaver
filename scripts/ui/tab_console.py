import sys
import re
import customtkinter as ctk

class ConsoleRedirector:
    def __init__(self, text_widget, status_callback=None):
        self.text_widget = text_widget
        self.original_stdout = sys.stdout
        self.status_callback = status_callback
        # Regex to strip colorama ANSI escape codes from the raw terminal strings
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def write(self, string):
        self.text_widget.insert("end", string)
        self.text_widget.see("end")
        self.original_stdout.write(string) 
        
        # Eavesdrop on the console output to update the GUI status bar
        if self.status_callback:
            clean_str = self.ansi_escape.sub('', string).replace('\r', '').replace('\n', '').strip()
            # If it's a backend status update, it usually ends in "..." or signals a failure
            if clean_str and len(clean_str) < 100:
                if clean_str.endswith("...") or "Failed" in clean_str or "Backing off" in clean_str:
                    self.status_callback(clean_str)

    def flush(self):
        self.original_stdout.flush()

class ConsoleTab(ctk.CTkFrame):
    def __init__(self, parent, engine, status_callback=None):
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        
        self.textbox = ctk.CTkTextbox(self, font=("Consolas", 12), fg_color="#0F0F0F", text_color="#00FF00")
        self.textbox.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.redirector = ConsoleRedirector(self.textbox, status_callback)
        sys.stdout = self.redirector
        
        print("TomeWeaver API Console initialized. Awaiting engine events...\n")

    def restore_stdout(self):
        sys.stdout = self.redirector.original_stdout