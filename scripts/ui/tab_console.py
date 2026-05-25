"""
    TomeWeaver: Developer Console Tab
    ---------------------------------
    Provides a real-time, scrolling view of the engine's internal states,
    API errors, and LLM JSON generation. Includes a real-time ANSI-to-GUI 
    color parser so terminal logs render beautifully.
"""
import sys
import re
import customtkinter as ctk


class ConsoleRedirector:
    """
    Hijacks Python's standard output (sys.stdout) and routes it to 
    a Tkinter text widget. Parses standard ANSI escape codes (colorama) 
    and applies native UI color tags on the fly.
    """
    def __init__(self, text_widget, status_callback=None):
        """Capture stdout and render ANSI-colored lines into a text widget.

        Args:
            text_widget: Tk ``Text`` widget receiving redirected output.
            status_callback: Optional ``(message)`` hook for the status bar.
        """
        self.text_widget = text_widget
        self.original_stdout = sys.stdout
        self.status_callback = status_callback
        
        # Regex to find ANSI escape sequences (e.g., \x1b[31m or \033[31;1m)
        self.ansi_regex = re.compile(r'\x1b\[([0-9;]*)m')
        
        # Map ANSI color codes to the Tkinter tags we registered in the UI
        self.tag_map = {
            '31': 'ansi_red',
            '32': 'ansi_green',
            '33': 'ansi_yellow',
            '34': 'ansi_blue',
            '35': 'ansi_magenta',
            '36': 'ansi_cyan',
            '37': 'ansi_white',
            '2':  'ansi_dim',
        }
        # Stateful tracking for multi-line colored strings
        self.active_tags = set()

    def write(self, string):
        # 1. Update the UI Status Bar (Requires clean, uncolored text)
        if self.status_callback:
            clean_str = self.ansi_regex.sub('', string).replace('\r', '').replace('\n', '').strip()
            if clean_str and len(clean_str) < 100:
                if clean_str.endswith("...") or "Failed" in clean_str or "Backing off" in clean_str:
                    self.status_callback(clean_str)

        # 2. Parse and inject colored text
        # re.split keeps the captured groups, so parts alternates: [text, ansi_code, text, ansi_code...]
        parts = self.ansi_regex.split(string)
        
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # Even indices are the actual text payload
                if part:
                    tags = tuple(self.active_tags) if self.active_tags else ()
                    self.text_widget.insert("end", part, tags)
            else:
                # Odd indices are the ANSI codes (e.g., '31', '0', '31;2')
                codes = part.split(';')
                for code in codes:
                    if code == '0' or code == '':
                        self.active_tags.clear()
                    elif code in self.tag_map:
                        # If a new main color is applied, clear previous colors to prevent conflicts
                        if code in ['31', '32', '33', '34', '35', '36', '37']:
                            self.active_tags = {t for t in self.active_tags if t == 'ansi_dim'}
                        self.active_tags.add(self.tag_map[code])

        self.text_widget.see("end")
        self.original_stdout.write(string) 

    def flush(self):
        self.original_stdout.flush()


class ConsoleTab(ctk.CTkFrame):
    """
    Developer Console Tab
    """
    def __init__(self, parent, engine, status_callback=None):
        """Build the developer console tab and attach :class:`ConsoleRedirector`.

        Args:
            parent: Workspace tab container.
            engine: Active engine (for log context paths).
            status_callback: Optional status bar updater.
        """
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        
        # Default text color changed to off-white so colored tags pop correctly
        self.textbox = ctk.CTkTextbox(self, font=("Consolas", 13), fg_color="#0F0F0F", text_color="#E0E0E0")
        self.textbox.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- REGISTER NATIVE UI COLOR TAGS ---
        # Bypasses CustomTkinter to use the underlying tk.Text tagging engine
        self.textbox.tag_config("ansi_red", foreground="#F44336")
        self.textbox.tag_config("ansi_green", foreground="#4CAF50")
        self.textbox.tag_config("ansi_yellow", foreground="#FFEB3B")
        self.textbox.tag_config("ansi_blue", foreground="#2196F3")
        self.textbox.tag_config("ansi_magenta", foreground="#9C27B0")
        self.textbox.tag_config("ansi_cyan", foreground="#00BCD4")
        self.textbox.tag_config("ansi_white", foreground="#FFFFFF")
        self.textbox.tag_config("ansi_dim", foreground="#888888")
        
        # CRITICAL FIX for --noconsole mode:
        # In a compiled EXE with no terminal, sys.stdout and sys.stderr are None.
        # We must manually assign our redirector to these slots so that print() 
        # calls have a destination (our UI textbox) instead of vanishing or crashing.
        self.redirector = ConsoleRedirector(self.textbox, status_callback)
        
        sys.stdout = self.redirector
        sys.stderr = self.redirector # Also catch Python tracebacks and errors!
        
        print("TomeWeaver API Console initialized. Awaiting engine events...\n")

    def restore_stdout(self):
        """CRITICAL: Must be called before closing the workspace to prevent crashes."""
        sys.stdout = self.redirector.original_stdout