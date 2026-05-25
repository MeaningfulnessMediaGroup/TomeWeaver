"""
TomeWeaver: UI Tooltip Utility
------------------------------
Provides a reusable, classic high-contrast hover-tooltip.
"""
import tkinter as tk

class Tooltip:
    """Classic OS-style hover tooltip bound to a single widget."""

    def __init__(self, widget, text, delay=500):
        """Attach delayed show/hide tooltip behavior to a widget.

        Args:
            widget: Tk/CTk widget to bind (``<Enter>``, ``<Leave>``, click).
            text: Tooltip body text; empty text disables display.
            delay: Milliseconds before the tooltip appears.
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self._id = None

        # Bind hover events
        self.widget.bind("<Enter>", self.schedule_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
        self.widget.bind("<ButtonPress>", self.hide_tooltip) # Hide immediately if clicked

    def schedule_tooltip(self, event=None):
        """Queue :meth:`show_tooltip` after ``self.delay`` ms."""
        self._id = self.widget.after(self.delay, self.show_tooltip)

    def show_tooltip(self, event=None):
        """Create and position the floating tooltip window."""
        if self.tooltip_window or not self.text:
            return
            
        # Calculate position (slightly below and to the right of the cursor/widget)
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Use standard tkinter Toplevel with overrideredirect for a true floating tooltip
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        self.tooltip_window.attributes("-topmost", True)

        # Classic, high-contrast Tooltip styling
        label = tk.Label(
            self.tooltip_window, 
            text=self.text, 
            justify="left",
            background="#FFFFE0",     # Classic Tooltip Light Yellow/Beige
            foreground="#000000",     # Solid Black text for maximum readability
            relief="solid",           # Crisp, solid border
            borderwidth=1,            # 1px border width
            padx=8,                   # Comfortable internal padding
            pady=4,
            font=("Segoe UI", 12)     # Standard clean OS font
        )
        label.pack()

    def hide_tooltip(self, event=None):
        """Cancel a pending show and destroy the tooltip window."""
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
            
            
def apply_global_text_bindings(root_app):
    """
    Applies modern OS text shortcuts (Ctrl+Backspace, Undo) GLOBALLY 
    to all Text and Entry widgets across the entire application.
    """
    import re

    # --- 1. GLOBAL TEXTBOX BINDINGS (Story Text, Prompts, Editor) ---
    def text_focus_in(event):
        """Silently enables the Undo stack the moment a Textbox is clicked."""
        try: event.widget.configure(undo=True, autoseparators=True, maxundo=-1)
        except Exception: pass

    def text_del_word_back(event):
        try:
            if event.widget.tag_ranges("sel"): event.widget.delete("sel.first", "sel.last")
            else: event.widget.delete("insert -1 chars wordstart", "insert")
        except Exception: pass
        return "break"

    def text_del_word_fwd(event):
        try:
            if event.widget.tag_ranges("sel"): event.widget.delete("sel.first", "sel.last")
            else: event.widget.delete("insert", "insert wordend")
        except Exception: pass
        return "break"

    root_app.bind_class("Text", "<FocusIn>", text_focus_in)
    root_app.bind_class("Text", "<Control-BackSpace>", text_del_word_back)
    root_app.bind_class("Text", "<Option-BackSpace>", text_del_word_back)
    root_app.bind_class("Text", "<Control-Delete>", text_del_word_fwd)
    root_app.bind_class("Text", "<Option-Delete>", text_del_word_fwd)

    # --- 2. GLOBAL ENTRY BINDINGS (Titles, Search Bars, Single-line Inputs) ---
    def entry_del_word_back(event):
        """Standard Tkinter Entry widgets lack the 'wordstart' index, so we math it with Regex."""
        try:
            if event.widget.select_present():
                event.widget.delete("sel.first", "sel.last")
            else:
                cursor_pos = event.widget.index("insert")
                text = event.widget.get()[:cursor_pos]
                match = re.search(r'\w*\W*$', text) # Finds the last whole word and trailing spaces
                if match and match.group(0):
                    del_len = len(match.group(0))
                    event.widget.delete(cursor_pos - del_len, "insert")
        except Exception: pass
        return "break"

    root_app.bind_class("Entry", "<Control-BackSpace>", entry_del_word_back)
    root_app.bind_class("Entry", "<Option-BackSpace>", entry_del_word_back)
    
    
def center_window_on_parent(dialog, parent):
    """Mathematically centers a popup dialog over its parent window, safely accounting for CustomTkinter UI scaling."""
    dialog.update_idletasks()
    parent.update_idletasks()
    
    # 1. Retrieve the active UI scaling factor DIRECTLY from our engine config (Bulletproof)
    from config import ENGINE_CONFIG
    try:
        scale = float(ENGINE_CONFIG.get("ui_scaling", 1.0))
    except Exception:
        scale = 1.0
   
    # 2. Convert parent physical screen pixels to logical pixels
    p_w = parent.winfo_width() / scale 
    p_h = parent.winfo_height() / scale
    p_x = parent.winfo_rootx() / scale 
    p_y = parent.winfo_rooty() / scale
    
    # 3. EXPLICIT SIZE EXTRACTION: Read the exact size requested by the developer
    # Bypasses Tkinter's delayed renderer which causes the 'squished' bug
    try:
        d_w = dialog._current_width
        d_h = dialog._current_height
    except Exception:
        d_w = 400
        d_h = 300
    
    # 4. Calculate center coordinates strictly in logical pixels
    x = p_x + (p_w / 2) - (d_w / 2) 
    y = p_y + (p_h / 2) - (d_h / 2) 
    
    # Failsafe bounds
    if x < 0: x = 0
    if y < 30: y = 30
    
    # 5. Lock in the EXACT size and the CORRECTED position
    dialog.geometry(f"{int(d_w)}x{int(d_h)}+{int(x)}+{int(y)}")