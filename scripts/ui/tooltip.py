"""
TomeWeaver: UI Tooltip Utility
------------------------------
Provides a reusable, classic high-contrast hover-tooltip.
"""
import tkinter as tk

class Tooltip:
    def __init__(self, widget, text, delay=500):
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
        self._id = self.widget.after(self.delay, self.show_tooltip)

    def show_tooltip(self, event=None):
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
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None