"""
    TomeWeaver: Story Timeline UI
    -----------------------------
    The core gameplay interface. Displays the adventure in a Single-Page 
    Card architecture, guaranteeing 60fps performance and zero resizing bugs.
    Features a Unified Textbox, Director's Control Panel, and Time-Travel Timeline.
"""
import threading
import re
import difflib
import customtkinter as ctk
from tkinter import messagebox
from ui.tooltip import Tooltip

# Timeline navigation glyphs (media-control style; tooltips carry the full labels)
_NAV_ICON_FIRST = "⏮"
_NAV_ICON_PREV_CHAPTER = "⏪"
_NAV_ICON_PREV_TURN = "⏴"
_NAV_ICON_NEXT_TURN = "⏵"
_NAV_ICON_NEXT_CHAPTER = "⏩"
_NAV_ICON_LAST = "⏭"
_NAV_BTN_FONT = ("Segoe UI Symbol", 16)
_NAV_TURN_BTN_FONT = ("Segoe UI Symbol", 15)
_NAV_BTN_STYLE = {
    "fg_color": "#4A4A4A",
    "hover_color": "#333333",
    "font": _NAV_BTN_FONT,
    "height": 28,
}
_NAV_TURN_BTN_STYLE = {
    **_NAV_BTN_STYLE,
    "font": _NAV_TURN_BTN_FONT,
}


def get_darker_shade(hex_color, factor=0.4):
    """Generates a deep-background pill color from a bright hex code."""
    try:
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6: return "#1A1A1B" 
        rgb = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
        dark = [max(0, int(c * factor)) for c in rgb]
        return f"#{dark[0]:02x}{dark[1]:02x}{dark[2]:02x}"
    except Exception:
        return "#1A1A1B"


class CTkFlowFrame(ctk.CTkFrame):
    """A custom frame that uses native packing to simulate a horizontal flow layout."""
    def __init__(self, master, **kwargs):
        """Create a horizontal flow layout container for choice chips.

        Args:
            master: Parent CTk widget.
            **kwargs: Forwarded to :class:`CTkFrame`.
        """
        super().__init__(master, **kwargs)
        self.rows = []

    def flow(self, pill_widgets):
        """Lay out choice pill widgets in wrapped horizontal rows.

        Args:
            pill_widgets: Iterable of CTk buttons to pack into flow rows.
        """
        for row in self.rows: row.destroy()
        self.rows.clear()
        
        if not pill_widgets: return
        
        self.update_idletasks()
        max_width = self.winfo_width()
        if max_width <= 10: max_width = 800
        
        current_row = ctk.CTkFrame(self, fg_color="transparent")
        current_row.pack(fill="x", anchor="w", pady=(0, 5))
        self.rows.append(current_row)
        
        current_width = 0
        pad_x = 8
        
        for pill in pill_widgets:
            pill.update_idletasks()
            w = pill.winfo_reqwidth()
            
            if current_width + w > max_width and current_width > 0:
                current_row = ctk.CTkFrame(self, fg_color="transparent")
                current_row.pack(fill="x", anchor="w", pady=(0, 5))
                self.rows.append(current_row)
                current_width = 0
                
            pill.master = current_row
            pill.pack(side="left", padx=(0, pad_x))
            current_width += w + pad_x


def clean_prose(text):
    """Aggressively formats text for professional e-reader line spacing."""
    if not text: return ""
    # 1. Convert all literal newlines to spaces to completely flatten the AI's artificial wrapping
    text = text.replace("\\n", "\n").replace("\r", "")
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # 2. Convert 3+ newlines to exactly 2 (standard paragraph break)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 3. Clean up double spaces
    return re.sub(r' {2,}', ' ', text).strip()


class StoryTab(ctk.CTkFrame):
    """
    Single-Page Story UI
    """
    def __init__(self, parent, engine, workspace):
        """Build the timeline, prose viewer, and player action controls.

        Args:
            parent: Workspace tab container.
            engine: Active headless engine instance.
            workspace: Parent :class:`WorkspaceFrame` for cross-tab refresh.
        """
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        self.workspace = workspace

        # --- FONT SETTINGS ---
        from config import ENGINE_CONFIG
        f_family = ENGINE_CONFIG.get("prose_font_family", "Georgia")
        f_size = ENGINE_CONFIG.get("prose_font_size", 15)
        
        self.prose_font = (f_family, int(f_size))
        self.bridge_font = (f_family, int(f_size), "italic")
        self.header_font = ("Arial", 12)
        self.action_font = ("Arial", 14, "bold")
        
        # --- STATE VARIABLES ---
        self.current_turn_idx = 0
        self.has_inventory = False

        # ==========================================
        # 1. THE MAIN CARD (Fills remaining space)
        # ==========================================
        self.card_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("#EBEBEB", "#22252A"), border_width=1, border_color=("#D3D3D3", "#343638"))
        
        # Internal Card Widgets
        self.hdr_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        self.lbl_chapter = ctk.CTkLabel(self.hdr_frame, text="", font=("Georgia", 22, "bold", "italic"), text_color="#00ACC1")
        self.btn_edit_card = ctk.CTkButton(self.hdr_frame, text="✎ Edit Scene", width=90, fg_color="#4A4A4A", hover_color="#333333")
        
        self.lbl_meta = ctk.CTkLabel(self.card_frame, text="", text_color="gray", font=self.header_font)
        
        # Action Frame (Holds the label and the "..." button side-by-side)
        self.action_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        self.lbl_action = ctk.CTkLabel(self.action_frame, text="", font=self.action_font, text_color="#4CAF50")
        self.btn_action_more = ctk.CTkButton(self.action_frame, text="...", width=30, height=20, font=("Arial", 14, "bold"), fg_color="#333333", hover_color="#555555")
        
        self.inv_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        
        # Unified Textbox with Professional Spacing
        self.prose_box = ctk.CTkTextbox(self.card_frame, wrap="word", font=self.prose_font, fg_color="transparent")
        self.prose_box._textbox.configure(spacing2=6, font=self.prose_font) # Adds 6px between wrapped lines
        
        # Register Native Tags safely
        self.prose_box._textbox.tag_config("bridge", font=self.bridge_font, foreground="#90CAF9") 
        self.prose_box._textbox.tag_config("story", font=self.prose_font)
        self.prose_box._textbox.tag_config("lore_dump", font=("Arial", 12, "italic"), foreground="gray")
        
        self.tools_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        self.bridge_tools = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
        self.story_tools = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
        self.choices_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")

        # ==========================================
        # 2. THE TIMELINE BAR (Bottom, Fixed)
        # ==========================================
        self.timeline_frame = ctk.CTkFrame(self, fg_color="transparent")
        
        # Consistent padx=2 between ALL buttons in a group, and padx=10 framing the slider
        
        self.btn_first = ctk.CTkButton(
            self.timeline_frame,
            text=_NAV_ICON_FIRST,
            width=36,
            command=lambda: self._navigate_timeline("first"),
            **_NAV_BTN_STYLE,
        )
        self.btn_first.pack(side="left", padx=2, pady=5)
        Tooltip(self.btn_first, "Jump to the First Turn of the Story")
        
        self.btn_prev_chap = ctk.CTkButton(
            self.timeline_frame,
            text=_NAV_ICON_PREV_CHAPTER,
            width=36,
            command=lambda: self._navigate_timeline("prev_chapter"),
            **_NAV_BTN_STYLE,
        )
        self.btn_prev_chap.pack(side="left", padx=2, pady=5)
        Tooltip(self.btn_prev_chap, "Jump to Previous Chapter")
        
        self.btn_prev = ctk.CTkButton(
            self.timeline_frame,
            text=_NAV_ICON_PREV_TURN,
            width=36,
            command=lambda: self._navigate_timeline("prev"),
            **_NAV_TURN_BTN_STYLE,
        )
        self.btn_prev.pack(side="left", padx=(2, 10), pady=5)
        Tooltip(self.btn_prev, "Go to Previous Turn")
        
        self.slider = ctk.CTkSlider(self.timeline_frame, command=self._on_slider_move)
        self.slider.pack(side="left", fill="x", expand=True, padx=10, pady=5)
               
        self.btn_next = ctk.CTkButton(
            self.timeline_frame,
            text=_NAV_ICON_NEXT_TURN,
            width=36,
            command=lambda: self._navigate_timeline("next"),
            **_NAV_TURN_BTN_STYLE,
        )
        self.btn_next.pack(side="left", padx=(10, 2), pady=5)
        Tooltip(self.btn_next, "Go to the Next Turn")
        
        self.btn_next_chap = ctk.CTkButton(
            self.timeline_frame,
            text=_NAV_ICON_NEXT_CHAPTER,
            width=36,
            command=lambda: self._navigate_timeline("next_chapter"),
            **_NAV_BTN_STYLE,
        )
        self.btn_next_chap.pack(side="left", padx=2, pady=5)
        Tooltip(self.btn_next_chap, "Jump to Next Chapter")
        
        self.btn_last = ctk.CTkButton(
            self.timeline_frame,
            text=_NAV_ICON_LAST,
            width=36,
            command=lambda: self._navigate_timeline("last"),
            **_NAV_BTN_STYLE,
        )
        self.btn_last.pack(side="left", padx=2, pady=5)
        Tooltip(self.btn_last, "Jump to the Last Turn of the Story")
        
        # ==========================================
        # 3. THE INPUT BAR (Bottom, Fixed)
        # ==========================================
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")

        self.cmd_dropdown = ctk.CTkOptionMenu(
            self.input_frame, 
            values=["Standard Action", "Expand Notes", "Force Setting", "Force Time", "Force POV", "Force Chapter"],
            width=140
        )
        if not self.engine.is_campaign:
            self.cmd_dropdown.pack(side="left", padx=(0, 10))

        self.text_input = ctk.CTkEntry(self.input_frame, placeholder_text="Type a custom action or dialogue...", font=("Arial", 14))
        self.text_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.text_input.bind("<Return>", lambda e: self.on_submit())

        self.btn_submit = ctk.CTkButton(self.input_frame, text="Submit", command=self.on_submit, width=100)
        self.btn_submit.pack(side="right")

        self.status_var = ctk.StringVar(value="Ready.")
        ctk.CTkLabel(self, textvariable=self.status_var, font=("Arial", 12, "italic"), text_color="gray").pack(side="bottom", anchor="w", padx=20, pady=(0, 5))

        # --- STARTUP SCREEN ---
        self.startup_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_start_adv = ctk.CTkButton(
            self.startup_frame, 
            text="✨ Start Adventure (Generate Opening Scene) ✨", 
            font=("Arial", 18, "bold"), height=60, 
            fg_color="#2E7D32", hover_color="#1B5E20",
            command=self._trigger_startup
        )
        self.btn_start_adv.pack(expand=True)

        # Initial Boot: Try to load the bookmark
        self._active_theme = None
        self.refresh_timeline(go_to_last=True, use_bookmark=True)

    def apply_theme(self, theme):
        """Apply atmospheric skin to the story card and luminance-flipped text."""
        from ui.theme_utils import apply_card_style, apply_card_text_colors, apply_story_tab_chrome

        self._active_theme = theme
        apply_story_tab_chrome(self, theme)
        apply_card_style(self.card_frame, theme)
        apply_card_text_colors(self, theme)


    # ---------------------------------------------------------
    # TIMELINE & NAVIGATION LOGIC
    # ---------------------------------------------------------

    def refresh_timeline(self, go_to_last=False, use_bookmark=False):
        """Syncs the slider boundaries to the history array and perfectly resets layout order."""
        history_len = len(self.engine.history)
        
        # 1. Strip everything safely
        self.startup_frame.pack_forget()
        self.card_frame.pack_forget()
        self.timeline_frame.pack_forget()
        self.input_frame.pack_forget()
        
        if history_len == 0:
            self.startup_frame.pack(fill="both", expand=True, pady=(100, 0))
            self._unlock_ui("Waiting for Director to start the adventure...")
            return
            
        # 2. Strict Layout Stacking (Guarantees layout won't crush)
        self.card_frame.pack(fill="both", expand=True, padx=20, pady=(15, 10))
        self.timeline_frame.pack(fill="x", padx=20, pady=10)
        self.input_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        if go_to_last:
            if use_bookmark:
                # ONLY use the bookmark during the initial workspace load
                from config import INSTANCE_CONFIG
                story_path = self.workspace.folder_name
                bookmark = INSTANCE_CONFIG.get("story_bookmarks", {}).get(story_path)
                
                if bookmark is not None and 0 <= int(bookmark) < history_len:
                    self.current_turn_idx = int(bookmark)
                else:
                    self.current_turn_idx = history_len - 1
            else:
                # Regular gameplay action: Always force to the end
                self.current_turn_idx = history_len - 1
            
        if history_len > 1:
            self.slider.configure(state="normal", from_=0, to=history_len - 1, number_of_steps=history_len - 1)
            self.slider.set(self.current_turn_idx)
            
            self.btn_first.configure(state="normal" if self.current_turn_idx > 0 else "disabled")
            self.btn_prev.configure(state="normal" if self.current_turn_idx > 0 else "disabled")
            self.btn_next.configure(state="normal" if self.current_turn_idx < history_len - 1 else "disabled")
            self.btn_last.configure(state="normal" if self.current_turn_idx < history_len - 1 else "disabled")
            
            # --- DYNAMIC CHAPTER BOUNDARY CHECKS ---
            curr_turn_val = self.engine.history[self.current_turn_idx].get("turn", 0)
            
            has_prev_chap = any(c.get("start_turn") is not None and c.get("start_turn") < curr_turn_val for c in self.engine.chapters)
            has_next_chap = any(c.get("start_turn") is not None and c.get("start_turn") > curr_turn_val for c in self.engine.chapters)
            
            # Prologue logic: Turn 0 acts as the ultimate previous chapter boundary
            if not has_prev_chap and curr_turn_val > 0: has_prev_chap = True
            
            self.btn_prev_chap.configure(state="normal" if has_prev_chap else "disabled")
            self.btn_next_chap.configure(state="normal" if has_next_chap else "disabled")
            
        else:
            self.slider.configure(from_=0, to=1, number_of_steps=1)
            self.slider.set(0)
            self.slider.configure(state="disabled")
            for btn in [self.btn_first, self.btn_prev, self.btn_prev_chap, self.btn_next_chap, self.btn_next, self.btn_last]:
                btn.configure(state="disabled")
                
        self._render_turn()
        self._update_bookmark()

    def _update_bookmark(self):
        """Silently records the current turn index to the global instance config."""
        from config import INSTANCE_CONFIG
        story_path = self.workspace.folder_name
        INSTANCE_CONFIG.setdefault("story_bookmarks", {})[story_path] = self.current_turn_idx
        # We don't save to disk on every slider move to prevent lag; 
        # the App will commit to disk when the workspace or app closes.

    def _on_slider_move(self, value):
        idx = int(value)
        if idx != self.current_turn_idx:
            self.current_turn_idx = idx
            self._update_bookmark() # Record the move
            self._render_turn()

    def _navigate_timeline(self, direction):
        
        if direction == "first": 
            self.current_turn_idx = 0
        elif direction == "prev" and self.current_turn_idx > 0: 
            self.current_turn_idx -= 1
        elif direction == "next" and self.current_turn_idx < len(self.engine.history) - 1: 
            self.current_turn_idx += 1
        elif direction == "last": 
            self.current_turn_idx = len(self.engine.history) - 1
        elif direction == "prev_chapter":
            curr_turn_val = self.engine.history[self.current_turn_idx].get("turn", 0)
            
            # Find the closest chapter start_turn that is STRICTLY LESS than the current turn
            target_idx = 0 # Default to the very first turn (Prologue)
            for c in reversed(self.engine.chapters):
                s_turn = c.get("start_turn")
                if s_turn is not None and s_turn < curr_turn_val:
                    # Found it! Now map the turn value back to an array index
                    for i, t in enumerate(self.engine.history):
                        if t.get("turn") == s_turn:
                            target_idx = i
                            break
                    break
            self.current_turn_idx = target_idx
            
        elif direction == "next_chapter":
            curr_turn_val = self.engine.history[self.current_turn_idx].get("turn", 0)
            
            # Find the closest chapter start_turn that is STRICTLY GREATER than the current turn
            target_idx = len(self.engine.history) - 1 # Default to the very last turn
            for c in self.engine.chapters:
                s_turn = c.get("start_turn")
                if s_turn is not None and s_turn > curr_turn_val:
                    for i, t in enumerate(self.engine.history):
                        if t.get("turn") == s_turn:
                            target_idx = i
                            break
                    break
            self.current_turn_idx = target_idx

        self.refresh_timeline(go_to_last=False)
        self._update_bookmark()


    # ---------------------------------------------------------
    # RENDER ACTIVE TURN (STRICT BOTTOM-UP PACKING)
    # ---------------------------------------------------------

    def _render_turn(self):
        """Draws all elements using a strict Bottom-Up packing order to guarantee the layout never breaks."""
        
        # 1. PURGE THE CARD STACK
        self.hdr_frame.pack_forget()
        self.lbl_chapter.pack_forget()
        self.btn_edit_card.pack_forget()
        self.lbl_meta.pack_forget()
        self.action_frame.pack_forget()
        self.inv_frame.pack_forget()
        self.prose_box.pack_forget()
        self.tools_frame.pack_forget()
        self.choices_frame.pack_forget()  # CRITICAL: Fixes the vertical gap bug

        idx = self.current_turn_idx
        turn = self.engine.history[idx]
        history_len = len(self.engine.history)
        
        # CRITICAL FIX: Use the engine's resolved property so Sandbox users always get Director Tools!
        cheats_allowed = getattr(self.engine, "allow_fix_command", True)
        
        try: actual_turn = int(turn.get("turn", 0))
        except: actual_turn = 0
        
        # --- DATA PREPARATION ---
        active_chap = self.engine.chapters[0]
        for c in reversed(self.engine.chapters):
            s_turn = c.get("start_turn")
            if s_turn is not None and s_turn <= actual_turn:
                active_chap = c
                break
                
        is_epilogue = str(turn.get("is_game_over", False)).lower() == "true" and str(turn.get("objective_achieved", False)).lower() == "true"
        
        if actual_turn == 0: chap_title = "~ Prologue ~"
        elif is_epilogue: chap_title = "~ Epilogue ~"
        else:
            c_num = active_chap.get('chapter_number', 1)
            c_title = active_chap.get('title', "").strip()
            
            # The standard prefix we automatically manage
            prefix = f"Chapter {c_num}"
            
            # Smart Detection: Skip auto-prefixing if the user already did it.
            # Handles: "Chapter 1", "Chapter 1 - Title", "CHAPTER 1: Title"
            if not c_title or c_title.lower() == prefix.lower():
                chap_display = prefix
            elif c_title.lower().startswith(prefix.lower()):
                # User manually wrote the chapter number, respect their formatting/delimiters
                chap_display = c_title
            else:
                # Standard case: Prepend our managed index
                chap_display = f"{prefix}: {c_title}"
            
            chap_title = f"~ {chap_display} ~"
            
        self.lbl_chapter.configure(text=chap_title)
        
        if self._active_theme:
            from ui.theme_utils import apply_card_text_colors
            apply_card_text_colors(self, self._active_theme)
        
        loc_raw = turn.get("location", "Unknown").strip()
        pov_raw = turn.get("pov_character", "Unknown").strip()
        
        loc_hdr = loc_raw if len(loc_raw) <= 100 else "Current Location"
        pov_hdr = pov_raw if len(pov_raw) <= 100 else "Main Character"
        
        meta_text = f"[Turn {actual_turn}]"
        
        # Inject the Micro-Objective Tracker for Campaign Mode
        if self.engine.is_campaign and actual_turn > 0 and not is_epilogue:
            obj_total = len(active_chap.get("objectives", []))
            if obj_total > 0:
                obj_current = 1
                for pt in self.engine.history:
                    pt_num = pt.get("turn", 0)
                    c_start = active_chap.get("start_turn")
                    # Count how many objectives were achieved *before* this specific turn
                    if c_start is not None and c_start <= pt_num < actual_turn:
                        if str(pt.get("objective_achieved", False)).lower() == "true":
                            obj_current += 1
                            
                # Cap it mathematically so it doesn't overflow if the AI hallucinates early victories
                if obj_current > obj_total: obj_current = obj_total
                meta_text += f" • [🎯 {obj_current}/{obj_total}]"
                
        meta_text += f" • [Loc: {loc_hdr}] • [POV: {pov_hdr}]"
        
        self.lbl_meta.configure(text=meta_text)
        
        has_action = False
        if idx > 0 and self.engine.history[idx-1].get("player_choice"):
            raw_action = self.engine.history[idx-1].get("player_choice", "").strip()
            
            # --- SANDBOX IMMERSION FILTER ---
            # Strictly hide transition headers on chapter boundaries (Start and End turns)
            hide_header = False
            if not self.engine.is_campaign:
                # Get boundaries as integers for absolute comparison
                try:
                    c_start = int(active_chap.get("start_turn", -1))
                    c_end = active_chap.get("end_turn")
                    c_end = int(c_end) if c_end is not None else -1
                    
                    current = int(actual_turn)
                    
                    if current == c_start or current == c_end:
                        hide_header = True
                except (ValueError, TypeError):
                    pass

            if not hide_header:
                # Flatten to single line for the header display
                flat_action = raw_action.replace("\n", " ").replace("\r", " ")
                
                # 1. Pack button to the far RIGHT first so it stays fixed
                self.btn_action_more.pack(side="right", padx=(10, 0))
                self.btn_action_more.configure(command=lambda a=raw_action: self._show_full_action(a))
                
                # 2. Pack label to the LEFT and allow it to expand into the remaining middle space
                self.lbl_action.pack(side="left", fill="x", expand=True)
                self.lbl_action.configure(text=f"❯ {flat_action}", anchor="w")
                    
                has_action = True

        self._render_inventory(turn)

        # Build Textbox Content
        self.prose_box.configure(state="normal")
        self.prose_box.delete("1.0", "end")
        
        if len(loc_raw) > 100 or len(pov_raw) > 100:
            lore_dump = ""
            if len(loc_raw) > 100: lore_dump += f"[Location]: {loc_raw}\n\n"
            if len(pov_raw) > 100: lore_dump += f"[POV]: {pov_raw}\n\n"
            self.prose_box.insert("end", f"{lore_dump.strip()}\n\n***\n\n", "lore_dump")

        bridge = turn.get("narrative_bridge")
        is_valid_bridge = bridge and bridge not in ["[OK]", "[FAILED]", ""]
        if idx > 0 and is_valid_bridge:
            clean_br = clean_prose(bridge)
            self.prose_box.insert("end", f"{clean_br}\n\n", "bridge")

        story = clean_prose(turn.get("story_text", ""))
        self.prose_box.insert("end", story, "story")
        self.prose_box.configure(state="disabled")

        # Build Director's Control Panel
        for w in self.bridge_tools.winfo_children(): w.destroy()
        for w in self.story_tools.winfo_children(): w.destroy()
        self.bridge_tools.pack_forget()
        self.story_tools.pack_forget()
        
        is_game_over = str(turn.get("is_game_over", False)).lower() == "true"
        show_controls = not is_game_over and not self.engine.is_test_mode
        
        if show_controls:
            # --- THE NARRATIVE SURGERY MENU ---
            # Purge the tools_frame properly to fix the duplication bug
            for w in self.tools_frame.winfo_children(): w.destroy()
            
            # Recreate the toolbars
            self.bridge_tools = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
            self.story_tools = ctk.CTkFrame(self.tools_frame, fg_color="transparent")
            
            if idx > 0:
                self.bridge_tools.pack(fill="x", pady=(5, 0))
                ctk.CTkLabel(self.bridge_tools, text="Bridge:", font=("Arial", 11, "bold"), text_color="#90CAF9", width=40).pack(side="left")

                if is_valid_bridge:
                    btn_gen = ctk.CTkButton(self.bridge_tools, text="⟳ Reroll", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100", command=lambda: self._generate_bridge(idx))
                    btn_gen.pack(side="left", padx=2)
                    
                    btn_exp = ctk.CTkButton(self.bridge_tools, text="✨ Expand", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F", command=lambda: self._trigger_bridge_edit(idx, "expand"))
                    btn_exp.pack(side="left", padx=2)
                    
                    btn_cond = ctk.CTkButton(self.bridge_tools, text="✨ Condense", width=60, height=24, font=("Arial", 11), fg_color="#3F51B5", hover_color="#303F9F", command=lambda: self._trigger_bridge_edit(idx, "condense"))
                    btn_cond.pack(side="left", padx=2)
                    
                    btn_pol = ctk.CTkButton(self.bridge_tools, text="✨ Polish", width=60, height=24, font=("Arial", 11), fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: self._trigger_bridge_edit(idx, "polish"))
                    btn_pol.pack(side="left", padx=2)
                    
                    btn_edit_br = ctk.CTkButton(self.bridge_tools, text="✎ Edit", width=50, height=24, font=("Arial", 11), fg_color="#4A4A4A", hover_color="#333333", command=lambda idx=idx: self._open_edit_dialog(idx))
                    btn_edit_br.pack(side="left", padx=2)
                    
                    btn_del = ctk.CTkButton(self.bridge_tools, text="X", width=28, height=24, font=("Arial", 11), fg_color="#B71C1C", hover_color="#7F0000", command=lambda: self._delete_bridge(idx))
                    btn_del.pack(side="left", padx=2)
                else:
                    btn_gen = ctk.CTkButton(self.bridge_tools, text="✨ Generate", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#E65100", command=lambda: self._generate_bridge(idx))
                    btn_gen.pack(side="left", padx=2)
                    
                # --- TIMELINE SURGERY (Right-Aligned on the Bridge Row) ---
                # Buttons pack right-to-left: Delete -> Undo -> Insert -> Bridge2Turn -> Turn2Bridge
                btn_del_t = ctk.CTkButton(self.bridge_tools, text="X Delete Turn", width=80, height=24, font=("Arial", 11), fg_color="#B71C1C", hover_color="#7F0000", command=lambda: self._trigger_surgery("delete", idx))
                btn_del_t.pack(side="right", padx=2)
                Tooltip(btn_del_t, "Permanently deletes this card and left-shifts all future turns.")
                
                if cheats_allowed and idx == history_len - 1 and history_len > 1:
                    btn_undo = ctk.CTkButton(self.bridge_tools, text="↶ Undo Turn", width=90, height=24, fg_color="#D32F2F", hover_color="#9A0007", command=self.on_undo)
                    btn_undo.pack(side="right", padx=2)
                    Tooltip(btn_undo, "Revert the game state to the previous turn.")
                
                btn_ins = ctk.CTkButton(self.bridge_tools, text="+ Insert Turn", width=80, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100", command=lambda: self._trigger_surgery("insert", idx))
                btn_ins.pack(side="right", padx=2)
                Tooltip(btn_ins, "Right-shifts all future turns and inserts a blank card here for you to type in.")
                
                if is_valid_bridge:
                    btn_b2t = ctk.CTkButton(self.bridge_tools, text="↔ Bridge to Turn", width=100, height=24, font=("Arial", 11), fg_color="#7B1FA2", hover_color="#4A148C", command=lambda: self._trigger_surgery("bridge_to_turn", idx))
                    btn_b2t.pack(side="right", padx=2)
                    Tooltip(btn_b2t, "Extracts this bridge into its own dedicated scene card.")

                if idx < history_len - 1:
                    btn_t2b = ctk.CTkButton(self.bridge_tools, text="↔ Turn to Bridge", width=100, height=24, font=("Arial", 11), fg_color="#7B1FA2", hover_color="#4A148C", command=lambda: self._trigger_surgery("turn_to_bridge", idx))
                    btn_t2b.pack(side="right", padx=2)
                    Tooltip(btn_t2b, "Collapses this scene forward into the next turn's narrative bridge.")

            self.story_tools.pack(fill="x", pady=(5, 5))
            ctk.CTkLabel(self.story_tools, text="Story:", font=("Arial", 11, "bold"), text_color="white", width=40).pack(side="left")
            
            if idx == history_len - 1:
                btn_redo = ctk.CTkButton(self.story_tools, text="⟳ Redo Turn", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100", command=self._trigger_redo)
                btn_redo.pack(side="left", padx=2)
                
            btn_rc = ctk.CTkButton(self.story_tools, text="⟳ Choices", width=60, height=24, font=("Arial", 11), fg_color="#0288D1", hover_color="#01579B", command=lambda: self._trigger_redo_choices(idx))
            btn_rc.pack(side="left", padx=2)
            
            btn_exp = ctk.CTkButton(self.story_tools, text="✨ Expand", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F", command=lambda: self._trigger_expansion(idx))
            btn_exp.pack(side="left", padx=2)

            btn_cond = ctk.CTkButton(self.story_tools, text="✨ Condense", width=60, height=24, font=("Arial", 11), fg_color="#3F51B5", hover_color="#303F9F", command=lambda: self._trigger_condense(idx))
            btn_cond.pack(side="left", padx=2)
            
            btn_pol = ctk.CTkButton(self.story_tools, text="✨ Polish", width=60, height=24, font=("Arial", 11), fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: self._trigger_polish(idx))
            btn_pol.pack(side="left", padx=2)
            
            if cheats_allowed:
                btn_fix = ctk.CTkButton(self.story_tools, text="✨ Fix...", width=60, height=24, font=("Arial", 11), fg_color="#009688", hover_color="#00796B", command=lambda: self._trigger_fix(idx))
                btn_fix.pack(side="left", padx=2)
                
            # --- STORY CONTENT TOOLS (Right-Aligned on Story Row) ---
            if cheats_allowed:
                btn_edit_card = ctk.CTkButton(self.story_tools, text="✎ Edit Scene", width=90, height=24, fg_color="#4A4A4A", hover_color="#333333", command=lambda idx=idx: self._open_edit_dialog(idx))
                btn_edit_card.pack(side="right", padx=2)
                
                # The Chapter Editor is distinct from the Scene Editor
                btn_edit_chap = ctk.CTkButton(self.story_tools, text="✎ Edit Chapter", width=95, height=24, fg_color="#4A4A4A", hover_color="#333333", command=lambda idx=idx: self._open_chapter_editor(idx))
                btn_edit_chap.pack(side="right", padx=2)
                
                
            if actual_turn > 1:
                is_start_of_chapter = active_chap.get("start_turn") == actual_turn
                if is_start_of_chapter:
                    btn_merge = ctk.CTkButton(self.story_tools, text="← Merge Chapter", width=100, height=24, font=("Arial", 11), fg_color="#4CAF50", hover_color="#388E3C", command=lambda: self._trigger_surgery("merge", idx))
                    btn_merge.pack(side="right", padx=2)
                else:
                    btn_split = ctk.CTkButton(self.story_tools, text="✂ Split Chapter", width=100, height=24, font=("Arial", 11), fg_color="#00BCD4", hover_color="#0097A7", command=lambda: self._trigger_surgery("split", idx))
                    btn_split.pack(side="right", padx=2)

        # Build Choices Area
        for w in self.choices_frame.winfo_children(): w.destroy()
        
        if idx == history_len - 1 and not is_game_over and turn.get("player_choice") is not None:
            c_text = turn.get("player_choice")
            btn_retry = ctk.CTkButton(self.choices_frame, text=f"⟳ Retry Action: {c_text}", fg_color="#F57C00", hover_color="#E65100", command=lambda: self._execute_action(c_text))
            btn_retry.pack(side="left", padx=5)
            
            def cancel_pending():
                self.engine.history[-1]["player_choice"] = None
                self.engine.save_state()
                self.refresh_timeline(go_to_last=True)
                
            btn_cancel = ctk.CTkButton(self.choices_frame, text="X Cancel Action", fg_color="#D32F2F", hover_color="#9A0007", command=cancel_pending)
            btn_cancel.pack(side="left", padx=5)
            
            self.btn_submit.configure(state="disabled")
            self.text_input.configure(state="disabled")
            
        elif idx == history_len - 1:
            for c in turn.get("choices", []):
                if not cheats_allowed and "Cheat Death" in c: continue
                color = "#1F6AA5"; hover = "#144870"
                if "Restart Game" in c: color = "#D32F2F"; hover = "#9A0007"
                elif "Quit" in c: color = "#4A4A4A"; hover = "#333333"
                elif "Export" in c: color = "#388E3C"; hover = "#1B5E20"
                elif "Undo (Cheat Death" in c: color = "#D32F2F"; hover = "#9A0007"
                elif "Start Chapter:" in c or "Conclude the Story" in c or "Proceed to the next" in c: color = "#7B1FA2"; hover = "#4A148C"
                
                btn = ctk.CTkButton(self.choices_frame, text=c, fg_color=color, hover_color=hover, anchor="w", command=lambda action=c: self._execute_action(action))
                btn.pack(fill="x", pady=2, padx=5)
                
        if idx == history_len - 1 and not is_game_over and turn.get("player_choice") is None:
            self.text_input.configure(state="normal")
            self.text_input.delete(0, 'end') # AGGRESSIVE CLEAR: Wipe any ghostly placeholder text
            self.btn_submit.configure(state="normal")
            self.cmd_dropdown.configure(state="normal")
        else:
            self.text_input.configure(state="disabled")
            self.btn_submit.configure(state="disabled")
            self.cmd_dropdown.configure(state="disabled")

        # =================================================================
        # 99. STRICT BOTTOM-UP PACKING
        # =================================================================
        has_choices = len(self.choices_frame.winfo_children()) > 0
        if has_choices:
            self.choices_frame.pack(side="bottom", fill="x", padx=20, pady=(5, 15))
            
        if show_controls:
            self.tools_frame.pack(side="bottom", fill="x", padx=20, pady=(5, 10))
            
        self.hdr_frame.pack(side="top", fill="x", padx=20, pady=(15, 5))
        self.lbl_chapter.pack(side="top", anchor="center")
        
        self.lbl_meta.pack(side="top", fill="x", padx=20, pady=(0, 5))
        
        if has_action:
            self.action_frame.pack(side="top", fill="x", padx=20, pady=(0, 10))
            
        if self.has_inventory:
            self.inv_frame.pack(side="top", fill="x", padx=20, pady=(0, 10))
            
        self.prose_box.pack(side="top", fill="both", expand=True, padx=20, pady=5)

        self._unlock_ui("Ready.")

    def _render_inventory(self, turn):
        """Builds the inventory pills safely using CTkFlowFrame."""
        for w in self.inv_frame.winfo_children(): w.destroy()
        
        schema = self.engine.setup_data.get("inventory_dictionary", {})
        is_game_over = str(turn.get("is_game_over", False)).lower() == "true"
        
        if not self.engine.track_inventory or not schema or is_game_over:
            self.has_inventory = False
            return
            
        self.has_inventory = True
        inv_str = turn.get("inventory_and_state", "").replace("[Status]", "").strip()
        current_state = {}
        for k, v in re.findall(r'([A-Za-z0-9_]+)\s*:\s*(.*?)(?=(?:[A-Za-z0-9_]+\s*:|$))', inv_str):
            current_state[k.strip()] = v.strip(' .,;')
            
        # Dynamically size the box height based on amount of items (Increased slightly to accommodate wrap padding)
        inv_height = 55 if len(schema) <= 3 else 95
            
        inv_box = ctk.CTkTextbox(
            self.inv_frame, wrap="word", height=inv_height,
            fg_color="transparent", scrollbar_button_color=("#EBEBEB", "#22252A"), scrollbar_button_hover_color=("#EBEBEB", "#22252A")
        )
        
        # FIX: Add 10px of vertical padding specifically between wrapped lines
        inv_box._textbox.configure(spacing2=10)
        
        inv_box.pack(fill="x")
        
        schema_items = list(schema.items())
        for idx, (key, info) in enumerate(schema_items):
            val = current_state.get(key, "None")
            if not val or str(val).strip() == "": val = "None"
            
            icon = info.get("icon", "🎒")
            base_color = info.get("color", "#1F6AA5")
            dark_bg = get_darker_shade(base_color)
            is_last = (idx == len(schema_items) - 1)
            
            pill = ctk.CTkFrame(inv_box, fg_color=dark_bg, corner_radius=15, border_width=1, border_color=base_color)
            
            lbl_i = ctk.CTkLabel(pill, text=icon, font=("Segoe UI Emoji", 14), text_color=base_color)
            lbl_i.pack(side="left", padx=(8, 4), pady=2)
            
            val_str = str(val)
            display_val = val_str if len(val_str) <= 35 else val_str[:32] + "..."
            lbl_v = ctk.CTkLabel(pill, text=f"{key}: {display_val}", font=("Arial", 12, "bold"), text_color="white")
            lbl_v.pack(side="left", padx=(0, 10), pady=2)
            
            tip_text = f"{key}:\n{val_str}"
            Tooltip(pill, tip_text)
            Tooltip(lbl_i, tip_text)
            Tooltip(lbl_v, tip_text)
            
            inv_box._textbox.window_create("end", window=pill)
            if not is_last:
                inv_box.insert("end", "   ", "sep")
                
        inv_box.configure(state="disabled")

    def _show_full_action(self, full_text):
        """Spawns a clean, scrollable window to read the unabridged player action."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Player Action")
        dialog.geometry("500x350")
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())
        
        ctk.CTkLabel(dialog, text="Action Taken:", font=("Arial", 16, "bold"), text_color="#4CAF50").pack(anchor="w", padx=20, pady=(20, 5))
        
        box = ctk.CTkTextbox(dialog, wrap="word", font=("Arial", 14))
        box.insert("1.0", full_text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=20, pady=5)
        
        ctk.CTkButton(dialog, text="Close", fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(pady=15)
        
    # ---------------------------------------------------------
    # ACTION SUBMISSION & THREADING
    # ---------------------------------------------------------

    def on_submit(self):
        """Submit the player's free-text or custom action to the engine."""
        if self.text_input.cget("state") == "disabled": return
        
        raw_text = self.text_input.get().strip()
        
        # CTk Bug Fix: Filter out the literal placeholder text if Tkinter accidentally returns it
        if raw_text == "Type a custom action or dialogue...":
            raw_text = ""
            
        cmd_type = self.cmd_dropdown.get() if not self.engine.is_campaign else "Standard Action"
        
        # Force Chapter is the ONLY command allowed to be submitted entirely blank 
        # (It opens the modal where you can fill in the details)
        if not raw_text and cmd_type != "Force Chapter": 
            return
            
        self.text_input.delete(0, 'end') 
        
        # --- AUTO-RESET DROPDOWN ---
        # Instantly revert the dropdown to Standard Action so the next turn's input is safe
        if not self.engine.is_campaign:
            self.cmd_dropdown.set("Standard Action")
        
        # --- UNIVERSAL INTERCEPTOR (Dropdown + Shorthand) ---
        is_force_chap = False
        chap_title = ""
        
        if cmd_type == "Force Chapter":
            is_force_chap = True
            chap_title = raw_text
        elif raw_text.lower().startswith("chapter:"):
            is_force_chap = True
            chap_title = raw_text[8:].strip() 
            
        if is_force_chap:
            self._show_force_chapter_dialog(chap_title)
            return

        # Standard routing for other commands
        if cmd_type == "Expand Notes": final_action = f"EXPAND: {raw_text}"
        elif cmd_type == "Force Setting": final_action = f"setting: {raw_text}"
        elif cmd_type == "Force Time": final_action = f"time: {raw_text}"
        elif cmd_type == "Force POV": final_action = f"pov: {raw_text}"
        else: final_action = raw_text

        self._execute_action(final_action)
        
    def _show_force_chapter_dialog(self, initial_idea):
        """Spawns a highly-tooled modal for the Director to configure a Cold Open chapter transition."""
        try:
            dialog = ctk.CTkToplevel(self)
            dialog.title("Force New Chapter (Cold Open)")
            dialog.geometry("750x700")
            dialog.attributes("-topmost", True)
            dialog.grab_set()

            from ui.tooltip import center_window_on_parent
            center_window_on_parent(dialog, self.winfo_toplevel())

            hdr = ctk.CTkFrame(dialog, fg_color="transparent")
            hdr.pack(fill="x", padx=20, pady=(15, 5))
            ctk.CTkLabel(hdr, text="🎬 Director: Next Chapter Setup", font=("Arial", 18, "bold"), text_color="#00BCD4").pack(side="left")

            ctk.CTkLabel(dialog, text="Configure the cold open for the next chapter. The AI will completely sever continuity with the previous environment and adopt these exact parameters.", wraplength=700, text_color="gray", justify="left").pack(anchor="w", padx=20, pady=(0, 10))

            scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=20, pady=5)

            c_vars = {}

            def add_field(label_text, key, is_multiline=False, tooltip_text="", default_val=""):
                f = ctk.CTkFrame(scroll, fg_color="transparent")
                f.pack(fill="x", pady=(10, 2))
                
                lbl = ctk.CTkLabel(f, text=label_text, font=("Arial", 14, "bold"))
                lbl.pack(side="left")
                if tooltip_text: Tooltip(lbl, tooltip_text)
                
                if is_multiline:
                    box_container = ctk.CTkFrame(scroll, fg_color="transparent")
                    box_container.pack(fill="x", padx=10)
                    box = ctk.CTkTextbox(box_container, height=80, wrap="word", font=("Arial", 14))
                    box.insert("1.0", str(default_val))
                    box.pack(fill="x")
                    widget = box
                else:
                    var = ctk.StringVar(value=str(default_val))
                    entry = ctk.CTkEntry(f, textvariable=var, font=("Arial", 14))
                    entry.pack(side="left", fill="x", expand=True, padx=10)
                    widget = var
                    
                # AI Tooling
                btn_inspire = ctk.CTkButton(f, text="🪄 Inspire", width=60, height=20, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
                btn_inspire.pack(side="right", padx=2)
                Tooltip(btn_inspire, "Expand shorthand text into a rich description.")
                
                btn_reroll = ctk.CTkButton(f, text="⟳ Reroll", width=60, height=20, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
                btn_reroll.pack(side="right", padx=2)
                Tooltip(btn_reroll, "Generate a completely new, creative idea for this field.")
                
                def do_ai(w=widget, btn=btn_reroll, is_inspire=False):
                    shorthand = None
                    if is_inspire:
                        shorthand = w.get().strip() if isinstance(w, ctk.StringVar) else w.get("1.0", "end").strip()
                        if not shorthand:
                            messagebox.showwarning("Missing Input", "Type some shorthand ideas in the box first to inspire the AI!")
                            return
                            
                    orig_text = btn.cget("text")
                    btn.configure(state="disabled", text="...")
                    self.winfo_toplevel().configure(cursor="watch")
                    
                    def worker():
                        from api import TomeWeaverAPI
                        success, result = TomeWeaverAPI.generate_field_data(self.engine.setup_data, f"New Chapter {key.replace('_', ' ')}", shorthand)
                        def update_ui():
                            self.winfo_toplevel().configure(cursor="")
                            btn.configure(state="normal", text=orig_text)
                            if success:
                                if isinstance(w, ctk.StringVar): w.set(result)
                                else:
                                    w.delete("1.0", "end")
                                    w.insert("1.0", result)
                            else:
                                messagebox.showerror("Error", result)
                        self.after(0, update_ui)
                    import threading
                    threading.Thread(target=worker, daemon=True).start()
                    
                btn_reroll.configure(command=lambda: do_ai(btn=btn_reroll, is_inspire=False))
                btn_inspire.configure(command=lambda: do_ai(btn=btn_inspire, is_inspire=True))

                c_vars[key] = widget

            add_field("Chapter Title:", "title", default_val=initial_idea)
            
            row2 = ctk.CTkFrame(scroll, fg_color="transparent")
            row2.pack(fill="x", pady=10)
            
            f_pov = ctk.CTkFrame(row2, fg_color="transparent")
            f_pov.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ctk.CTkLabel(f_pov, text="POV Character:", font=("Arial", 12, "bold")).pack(anchor="w")
            curr_pov = self.engine.history[-1].get("pov_character", "") if self.engine.history else ""
            c_vars["pov"] = ctk.StringVar(value=curr_pov)
            ctk.CTkEntry(f_pov, textvariable=c_vars["pov"], font=("Arial", 14)).pack(fill="x")
            
            f_time = ctk.CTkFrame(row2, fg_color="transparent")
            f_time.pack(side="right", fill="x", expand=True)
            ctk.CTkLabel(f_time, text="Time Jump (e.g. 'Three days later'):", font=("Arial", 12, "bold")).pack(anchor="w")
            c_vars["time"] = ctk.StringVar(value="")
            ctk.CTkEntry(f_time, textvariable=c_vars["time"], font=("Arial", 14)).pack(fill="x")

            add_field("Location / Environment:", "location", is_multiline=True, tooltip_text="The exact setting the new chapter opens in.")
            add_field("Synopsis / Starting Situation:", "synopsis", is_multiline=True, tooltip_text="What is the protagonist doing exactly as the chapter begins?", default_val=initial_idea)

            from config import INSTANCE_CONFIG, ROOT_DIR, save_json_atomically

            transition_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            transition_frame.pack(fill="x", pady=(14, 4))
            ctk.CTkLabel(
                transition_frame,
                text="Chapter transition:",
                font=("Arial", 14, "bold"),
            ).pack(anchor="w")

            saved_mode = INSTANCE_CONFIG.get("force_chapter_transition_mode", "wrap_up")
            if saved_mode not in ("wrap_up", "immediate"):
                saved_mode = "wrap_up"
            transition_var = ctk.StringVar(value=saved_mode)

            rb_wrap = ctk.CTkRadioButton(
                transition_frame,
                text="Conclude current scene first",
                variable=transition_var,
                value="wrap_up",
            )
            rb_wrap.pack(anchor="w", padx=8, pady=(6, 2))
            Tooltip(
                rb_wrap,
                "The AI writes one more turn to wrap up this chapter, then offers "
                "'Start Chapter X' as the only choice. The cold open begins on the turn after that.",
            )

            rb_immediate = ctk.CTkRadioButton(
                transition_frame,
                text="Begin next chapter immediately",
                variable=transition_var,
                value="immediate",
            )
            rb_immediate.pack(anchor="w", padx=8, pady=(2, 6))
            Tooltip(
                rb_immediate,
                "This turn ends the chapter. Your action is set to 'Start Chapter X: …' and "
                "the new chapter cold-opens on the very next turn — no AI wrap-up.",
            )

            def on_submit_modal():
                chap_data = {
                    "title": c_vars["title"].get().strip(),
                    "pov": c_vars["pov"].get().strip(),
                    "time": c_vars["time"].get().strip(),
                    "location": c_vars["location"].get("1.0", "end").strip(),
                    "synopsis": c_vars["synopsis"].get("1.0", "end").strip()
                }
                immediate = transition_var.get() == "immediate"

                INSTANCE_CONFIG["force_chapter_transition_mode"] = transition_var.get()
                save_json_atomically(INSTANCE_CONFIG, ROOT_DIR / "configs" / "instance_config.json")
                
                dialog.destroy()
                self._lock_ui("Architecting transition...")
                def worker():
                    result = self.engine.trigger_manual_chapter(chap_data, immediate=immediate)
                    
                    def update_ui():
                        self.refresh_timeline(go_to_last=True)
                        if not result:
                            messagebox.showerror("Error", "Failed to generate chapter transition.")
                            return
                            
                        # CRITICAL FIX: Trigger the memory compiler check after a manual chapter transition!
                        def on_progress(current, total):
                            if current == "Seeding": msg = "Extracting Base Lore..."
                            elif current == "Condensing": msg = f"{total}..."
                            elif current == "Reconciling": msg = "Merging duplicates..."
                            elif current == "Syncing": msg = "Recalculating Timestamps..."
                            else: msg = f"Processing Chunk {current}/{total}..."
                            self.after(0, lambda: self.status_var.set(f"Background Task: {msg}"))
                            
                        def on_complete(success, msg):
                            self.after(0, lambda: self.status_var.set("Ready."))

                        self.engine._trigger_memory_compilation(progress_callback=on_progress, completion_callback=on_complete)

                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()

            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(fill="x", padx=20, pady=15)
            ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left")
            
            btn_submit = ctk.CTkButton(btn_frame, text="Submit", font=("Arial", 14, "bold"), fg_color="#00BCD4", hover_color="#0097A7", command=on_submit_modal)
            btn_submit.pack(side="right")
            Tooltip(btn_submit, "Apply the chapter setup using the selected transition mode above.")
            
        except Exception as e:
            # If the modal crashed while trying to render, show us the exact error!
            from tkinter import messagebox
            messagebox.showerror("UI Crash", f"Failed to open Director Modal:\n\n{str(e)}")
        
        
    def _execute_action(self, action_string):
        pc_exact = str(action_string).strip()
        
        if pc_exact in ["Export Story", "Export Tragic Ending"]:
            self.workspace._export_dialog() 
            return
        if pc_exact == "Quit":
            self.workspace.close_workspace()
            return
            
        self._lock_ui(f"Submitting: '{action_string[:20]}...'")
        def worker():
            result = self.engine.submit_action(action_string)
            def update_ui():
                if not result and pc_exact != "Restart Game" and not pc_exact.startswith("Undo"):
                    messagebox.showerror("Generation Error", "The AI failed to generate the next turn.")
                    self.refresh_timeline(go_to_last=True)
                    return

                # 1. INSTANT UI UNLOCK: Redraw the UI immediately so the user can read the story!
                self.refresh_timeline(go_to_last=True)

                # 2. BACKGROUND RAG: Run memory compilation silently while the user reads.
                def on_progress(current, total):
                    if current == "Seeding": msg = "Extracting Base Lore..."
                    elif current == "Condensing": msg = f"{total}..."
                    elif current == "Reconciling": msg = "Merging duplicates..."
                    elif current == "Syncing": msg = "Recalculating Timestamps..."
                    else: msg = f"Processing Chunk {current}/{total}..."
                    # Just update the status bar gently, do NOT lock the UI
                    self.after(0, lambda: self.status_var.set(f"Background Task: {msg}"))
                    
                def on_complete(success, msg):
                    self.after(0, lambda: self.status_var.set("Ready."))

                self.engine._trigger_memory_compilation(progress_callback=on_progress, completion_callback=on_complete)
                    
            self.after(0, update_ui)
        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------
    # NON-DESTRUCTIVE EDITORS
    # ---------------------------------------------------------

    def _delete_bridge(self, turn_idx):
        if messagebox.askyesno("Delete Bridge", "Are you sure you want to delete this transition?"):
            if "narrative_bridge" in self.engine.history[turn_idx]:
                del self.engine.history[turn_idx]["narrative_bridge"]
                self.engine._resync_all_visibility()
                self.engine.save_state()
                self._render_turn()

    def _generate_bridge(self, turn_idx):
        self._lock_ui("Regenerating transition...")
        def worker():
            b_text = self.engine.request_bridge_generation(turn_idx)
            def update_ui():
                if b_text and b_text not in ["[OK]", "[FAILED]"]:
                    self.engine.history[turn_idx]["narrative_bridge"] = b_text
                    self.engine.save_state()
                self._unlock_ui("Ready.")
                self._render_turn() 
            self.after(0, update_ui)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_bridge_edit(self, turn_idx, edit_type):
        current_bridge = self.engine.history[turn_idx].get("narrative_bridge", "").strip()
        if not current_bridge: return
            
        self._lock_ui(f"Applying {edit_type} to bridge...")
        self.engine.backup_turn = self.engine.history[turn_idx].copy()
        self.engine.backup_turn["story_text"] = current_bridge 
        self.engine.backup_turn_idx = turn_idx
        
        def worker():
            from api import TomeWeaverAPI
            # Pass the Engine so the API can construct the full Narrative Sandwich + RAG Lore
            success, result = TomeWeaverAPI.edit_narrative_bridge(self.engine, turn_idx, current_bridge, edit_type)
            
            def update_ui():
                if success and result:
                    clean_result = result.replace('"', '').replace('*', '').strip()
                    draft = self.engine.backup_turn.copy()
                    draft["story_text"] = clean_result
                    self._show_draft_diff(draft, f"{edit_type} (Bridge)")
                else:
                    messagebox.showerror("Error", f"Failed to {edit_type} bridge.\n{result}")
                    self.engine.cancel_draft()
                    self._unlock_ui("Ready.")
            self.after(0, update_ui)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_surgery(self, action, turn_idx):
        if action == "delete":
            warn = f"Are you sure you want to permanently delete Turn {self.engine.history[turn_idx].get('turn')}?\n\nThis will shift all future turns backwards."
            if messagebox.askyesno("Delete Turn", warn, icon="warning"):
                self._lock_ui("Deleting turn...")
                def worker():
                    self.engine.delete_turn(turn_idx)
                    
                    # If we deleted the very last turn, we must retreat the UI cursor safely
                    new_len = len(self.engine.history)
                    if self.current_turn_idx >= new_len:
                        self.current_turn_idx = new_len - 1
                        
                    self.after(0, lambda: self.refresh_timeline(go_to_last=False))
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
        elif action == "insert":
            # Spawn a small decision dialog to determine the anchor point
            dialog = ctk.CTkToplevel(self)
            dialog.title("Insert Blank Turn")
            dialog.geometry("350x150")
            dialog.attributes("-topmost", True)
            dialog.grab_set() # Force focus
            
            from ui.tooltip import center_window_on_parent
            center_window_on_parent(dialog, self.winfo_toplevel())

            t_num = self.engine.history[turn_idx].get('turn', '?')
            ctk.CTkLabel(dialog, text=f"Where should the blank card be inserted relative to Turn {t_num}?", wraplength=300).pack(pady=15)

            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(pady=10)

            def execute_insertion(final_idx):
                dialog.destroy()
                self._lock_ui("Inserting blank turn...")
                def worker():
                    self.engine.insert_blank_turn(final_idx)
                    # Automatically advance the UI to the newly created blank card
                    self.current_turn_idx = final_idx
                    self.after(0, lambda: self.refresh_timeline(go_to_last=False))
                import threading
                threading.Thread(target=worker, daemon=True).start()

            # "Before" uses the current index (everything right-shifts)
            ctk.CTkButton(btn_frame, text="Insert Before", width=120, fg_color="#1F6AA5", command=lambda: execute_insertion(turn_idx)).pack(side="left", padx=10)
            
            # "After" uses index + 1 (everything after the current card right-shifts)
            ctk.CTkButton(btn_frame, text="Insert After", width=120, fg_color="#2E7D32", hover_color="#1B5E20", command=lambda: execute_insertion(turn_idx + 1)).pack(side="left", padx=10)
            
        elif action == "turn_to_bridge":
            self._lock_ui("Collapsing turn into bridge...")
            def worker():
                self.engine.convert_turn_to_bridge(turn_idx)
                
                # Because the turn deleted itself, the NEXT turn instantly shifted left
                # and occupies this exact index. The cursor stays exactly where it is!
                self.after(0, lambda: self.refresh_timeline(go_to_last=False))
            import threading
            threading.Thread(target=worker, daemon=True).start()
            
        elif action == "bridge_to_turn":
            self._lock_ui("Expanding bridge into turn...")
            def worker():
                self.engine.convert_bridge_to_turn(turn_idx)
                self.after(0, lambda: self.refresh_timeline(go_to_last=False))
            import threading
            threading.Thread(target=worker, daemon=True).start()
            
        elif action == "split":
            self._lock_ui("Splitting chapter boundaries...")
            def worker():
                self.engine.split_chapter(turn_idx)
                self.after(0, lambda: self.refresh_timeline(go_to_last=False))
            import threading
            threading.Thread(target=worker, daemon=True).start()
            
        elif action == "merge":
            c_num = next((c.get("chapter_number") for c in self.engine.chapters if c.get("start_turn") == self.engine.history[turn_idx].get("turn")), None)
            if c_num:
                self._lock_ui("Merging chapter boundaries...")
                def worker():
                    self.engine.merge_chapter_up(c_num)
                    self.after(0, lambda: self.refresh_timeline(go_to_last=False))
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
        self._update_bookmark()
            
    def on_undo(self):
        """Revert the last committed player choice on a background worker thread."""
        self._lock_ui("Undoing last choice...")
        def worker():
            self.engine.undo()
            self.after(0, lambda: self.refresh_timeline(go_to_last=True))
        threading.Thread(target=worker, daemon=True).start()
        self._update_bookmark()

    def _trigger_redo(self):
        self._lock_ui("Generating alternative version...")
        def worker():
            self.engine.redo_turn()
            self.after(0, lambda: self.refresh_timeline(go_to_last=True))
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_redo_choices(self, turn_idx):
        self._lock_ui("Generating new choices...")
        def worker():
            self.engine.redo_choices(turn_idx)
            self.after(0, self._render_turn)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_polish(self, turn_idx):
        self._lock_ui("Generating polished prose...")
        def worker():
            draft = self.engine.request_polish(turn_idx)
            self.after(0, lambda: self._show_draft_diff(draft, "polish"))
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_expansion(self, turn_idx):
        self._lock_ui("Expanding turn prose...")
        def worker():
            draft = self.engine.request_expansion(turn_idx)
            self.after(0, lambda: self._show_draft_diff(draft, "expansion"))
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_condense(self, turn_idx):
        self._lock_ui("Condensing turn prose...")
        def worker():
            draft = self.engine.request_condense(turn_idx)
            self.after(0, lambda: self._show_draft_diff(draft, "condense"))
        threading.Thread(target=worker, daemon=True).start()
        
    def _trigger_fix(self, turn_idx):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Director Fix")
        dialog.geometry("750x620") 
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())
        
        lbl_src = ctk.CTkLabel(dialog, text="1. Target Text (Optional - Highlight text in the story to auto-fill):", font=("Arial", 12, "bold"), text_color="#00BCD4")
        lbl_src.pack(anchor="w", padx=20, pady=(20, 2))
        source_box = ctk.CTkTextbox(dialog, height=80, font=("Arial", 14), wrap="word")
        source_box.pack(fill="x", padx=20)
        
        lbl_tgt = ctk.CTkLabel(dialog, text="2. Literal Replacement (Optional):", font=("Arial", 12, "bold"), text_color="#4CAF50")
        lbl_tgt.pack(anchor="w", padx=20, pady=(15, 2))
        target_box = ctk.CTkTextbox(dialog, height=80, font=("Arial", 14), wrap="word")
        target_box.pack(fill="x", padx=20)
        
        lbl_inst = ctk.CTkLabel(dialog, text="3. AI Editor Instruction (Optional):", font=("Arial", 12, "bold"), text_color="#FF9800")
        lbl_inst.pack(anchor="w", padx=20, pady=(15, 2))
        inst_box = ctk.CTkTextbox(dialog, height=80, font=("Arial", 14), wrap="word")
        inst_box.pack(fill="x", padx=20)
        
        bot_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        bot_frame.pack(fill="x", padx=20, pady=(15, 0))
        
        ctk.CTkLabel(bot_frame, text="AI Freedom:", font=("Arial", 12, "bold"), text_color="gray").pack(side="left")
        saved_freedom = self.engine.setup_data.get("fix_freedom", "Balanced (0.4)")
        freedom_var = ctk.StringVar(value=saved_freedom)
        
        freedom_menu = ctk.CTkOptionMenu(
            bot_frame, variable=freedom_var, 
            values=["Very Conservative (0.1)", "Conservative (0.2)", "Balanced (0.4)", "Creative (0.7)", "Very Creative (0.9)"],
            width=180
        )
        freedom_menu.pack(side="left", padx=10)
        
        try:
            if self.prose_box.tag_ranges("sel"):
                selected = self.prose_box.get("sel.first", "sel.last").replace('\n', ' ').strip()
                if selected: source_box.insert("1.0", selected)
        except Exception: pass
            
        inst_box.focus()
        
        def on_submit(*args):
            src = source_box.get("1.0", "end").strip()
            tgt = target_box.get("1.0", "end").strip()
            inst = inst_box.get("1.0", "end").strip()
            
            if not tgt and not inst: return 
            
            if src and tgt and inst:
                instruction = f"Find the text '{src}' and replace it literally with '{tgt}'. Then, apply this editorial instruction to the surrounding scene: {inst}"
                display_title = f"{tgt} (+ {inst})"
            elif src and tgt:
                instruction = f"Find the exact text '{src}' and swap it literally with '{tgt}'. Do not add narrative commentary about the change."
                display_title = tgt
            elif src and inst:
                instruction = f"Locate the text '{src}' and rewrite it according to this instruction: {inst}"
                display_title = inst
            elif tgt and not src and not inst:
                instruction = f"Insert or apply this exact text to the scene: '{tgt}'"
                display_title = tgt
            else:
                instruction = f"Apply this editorial instruction to the scene: {inst}"
                display_title = inst
                
            freedom_str = freedom_var.get()
            match = re.search(r'\(([\d\.]+)\)', freedom_str)
            target_temp = float(match.group(1)) if match else 0.4
            
            self.engine.setup_data["fix_freedom"] = freedom_str
            from config import save_json_atomically
            save_json_atomically(self.engine.setup_data, self.engine.adv_dir / "setup.json")
                
            dialog.destroy()
            
            self._lock_ui(f"Applying fix: {display_title[:15]}...")
            def worker():
                draft = self.engine.request_fix(instruction, turn_idx, temp_override=target_temp)
                self.after(0, lambda: self._show_draft_diff(draft, "fix", display_title))
            threading.Thread(target=worker, daemon=True).start()
            
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4A4A4A", hover_color="#333333", command=dialog.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Apply Fix", width=120, font=("Arial", 14, "bold"), fg_color="#009688", hover_color="#00796B", command=on_submit).pack(side="right", padx=10)

    # ---------------------------------------------------------
    # DIFF UI & MANUAL EDIT
    # ---------------------------------------------------------

    def _show_draft_diff(self, draft_turn, action_type, instruction=None):
        if not draft_turn:
            self._unlock_ui("Ready.")
            messagebox.showerror("Error", "The engine failed to generate a draft. Check the Developer Console.")
            self.engine.cancel_draft()
            self._render_turn()
            return
            
        dialog = ctk.CTkToplevel(self)
        title_str = f"Review Draft ({action_type.capitalize()})"
        if instruction: title_str += f": '{instruction}'"
        dialog.title(title_str)
        dialog.geometry("1000x700")
        dialog.attributes("-topmost", True)
        dialog.grab_set()
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        orig_text = self.engine.backup_turn.get("story_text", "").replace("\\n", "\n").strip()
        new_text = draft_turn.get("story_text", "").replace("\\n", "\n").strip()
        is_identical = (orig_text == new_text)

        if is_identical:
            warn_frame = ctk.CTkFrame(dialog, fg_color="#FBC02D", corner_radius=8)
            warn_frame.pack(fill="x", padx=20, pady=(20, 0))
            ctk.CTkLabel(warn_frame, text="⚠️ NO CHANGES DETECTED: The AI returned the exact same text! Hit 'Reroll' to try again. ⚠️", font=("Arial", 16, "bold"), text_color="black").pack(pady=10)

        grid = ctk.CTkFrame(dialog, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20, pady=20)
        grid.columnconfigure(0, weight=1, uniform="group1")
        grid.columnconfigure(1, weight=1, uniform="group1")
        grid.rowconfigure(1, weight=1)

        ctk.CTkLabel(grid, text="Original Text", font=("Arial", 16, "bold"), text_color="#F44336").grid(row=0, column=0, pady=(0, 10))
        new_hdr_color = "#FBC02D" if is_identical else "#4CAF50"
        new_hdr_text = "Proposed Revision (IDENTICAL)" if is_identical else "Proposed Revision"
        ctk.CTkLabel(grid, text=new_hdr_text, font=("Arial", 16, "bold"), text_color=new_hdr_color).grid(row=0, column=1, pady=(0, 10))

        orig_box = ctk.CTkTextbox(grid, wrap="word", font=self.prose_font)
        orig_box.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        
        new_box = ctk.CTkTextbox(grid, wrap="word", font=self.prose_font)
        new_box.grid(row=1, column=1, sticky="nsew", padx=(10, 0))

        orig_box.tag_config("delete", background="#5C1B1B") 
        orig_box.tag_config("replace", background="#7A4B00") 
        new_box.tag_config("insert", background="#1B4B1B") 
        new_box.tag_config("replace", background="#7A4B00") 

        orig_tokens = re.split(r'(\s+)', orig_text)
        new_tokens = re.split(r'(\s+)', new_text)

        matcher = difflib.SequenceMatcher(None, orig_tokens, new_tokens)
        
        for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
            orig_slice = "".join(orig_tokens[i1:i2])
            new_slice = "".join(new_tokens[j1:j2])
            
            if opcode == 'equal':
                orig_box.insert("end", orig_slice)
                new_box.insert("end", new_slice)
            elif opcode == 'replace':
                orig_box.insert("end", orig_slice, "replace")
                new_box.insert("end", new_slice, "replace")
            elif opcode == 'delete':
                orig_box.insert("end", orig_slice, "delete")
            elif opcode == 'insert':
                new_box.insert("end", new_slice, "insert")

        orig_box.configure(state="disabled")
        new_box.configure(state="disabled")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        def on_accept():
            if "(Bridge)" in action_type:
                idx = self.engine.backup_turn_idx
                self.engine.history[idx]["narrative_bridge"] = draft_turn["story_text"]
                self.engine._resync_all_visibility()
                self.engine.save_state()
                self.engine.cancel_draft()
            else:
                self.engine.commit_draft(draft_turn)
                
            dialog.destroy()
            self._render_turn()

        def on_cancel():
            self.engine.cancel_draft()
            dialog.destroy()
            self._render_turn()

        def on_retry():
            dialog.destroy()
            if action_type == "expansion": self._trigger_expansion(self.current_turn_idx)
            elif action_type == "condense": self._trigger_condense(self.current_turn_idx)
            else:
                self._lock_ui(f"Rerolling {action_type} draft...")
                def worker():
                    new_draft = self.engine.request_reroll_draft()
                    self.after(0, lambda: self._show_draft_diff(new_draft, action_type, instruction))
                threading.Thread(target=worker, daemon=True).start()
                
        ctk.CTkButton(btn_frame, text="Cancel (Discard)", fg_color="#D32F2F", hover_color="#9A0007", width=120, command=on_cancel).pack(side="left")
        
        center_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
        center_frame.pack(side="left", expand=True)
        ctk.CTkButton(center_frame, text="⟳ Reroll Draft", fg_color="#FF9800", hover_color="#F57C00", width=120, command=on_retry).pack()
        
        ctk.CTkButton(btn_frame, text="Accept Revision", fg_color="#388E3C", hover_color="#1B5E20", width=120, command=on_accept).pack(side="right") 
        
    def _open_edit_dialog(self, turn_idx):
        if turn_idx < 0 or turn_idx >= len(self.engine.history): return
        turn = self.engine.history[turn_idx]
        
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Narrative Editor: Turn {turn.get('turn', '?')}")
        dialog.geometry("900x850")
        dialog.attributes("-topmost", True)
        dialog.grab_set() 
        
        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        meta_grid = ctk.CTkFrame(scroll, fg_color="transparent")
        meta_grid.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(meta_grid, text="Location:", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w")
        loc_var = ctk.StringVar(value=turn.get("location", ""))
        
        # Wrap the entry and button in a sub-frame so they sit nicely in the grid cell
        loc_frame = ctk.CTkFrame(meta_grid, fg_color="transparent")
        loc_frame.grid(row=1, column=0, padx=(0, 20), sticky="w")
        
        ctk.CTkEntry(loc_frame, textvariable=loc_var, width=320, font=("Arial", 13)).pack(side="left")
        
        def infer_loc_async():
            # Grab the current, LIVE text from the prose box (and bridge if it exists)
            current_prose = story_box.get("1.0", "end").strip()
            if bridge_box is not None:
                br = bridge_box.get("1.0", "end").strip()
                if br: current_prose = f"{br}\n\n{current_prose}"
                
            if not current_prose: return
                
            # Determine if we should pass a geographic anchor
            prev_loc = None
            if turn_idx > 0:
                # Is this the start of a chapter?
                is_start = False
                for c in self.engine.chapters:
                    if c.get("start_turn") == turn.get("turn"):
                        is_start = True
                        break
                # If it is NOT a hard chapter cut, pass the previous turn's location
                if not is_start:
                    prev_loc = self.engine.history[turn_idx - 1].get("location", "")
                
            btn_loc_infer.configure(state="disabled", text="...")
            self.winfo_toplevel().configure(cursor="watch")
            
            def worker():
                from api import TomeWeaverAPI
                succ, res = TomeWeaverAPI.infer_location(current_prose, prev_loc)
                def update_ui():
                    self.winfo_toplevel().configure(cursor="")
                    btn_loc_infer.configure(state="normal", text="⟳")
                    if succ and res:
                        loc_var.set(res)
                self.after(0, update_ui)
            import threading
            threading.Thread(target=worker, daemon=True).start()

        btn_loc_infer = ctk.CTkButton(loc_frame, text="⟳", width=25, height=24, fg_color="#F57C00", hover_color="#E65100", command=infer_loc_async)
        btn_loc_infer.pack(side="left", padx=(5, 0))
        Tooltip(btn_loc_infer, "Read the story prose and automatically determine the location.")
        
        ctk.CTkLabel(meta_grid, text="POV:", font=("Arial", 12, "bold")).grid(row=0, column=1, sticky="w")
        pov_var = ctk.StringVar(value=turn.get("pov_character", ""))
        ctk.CTkEntry(meta_grid, textvariable=pov_var, width=250, font=("Arial", 13)).grid(row=1, column=1, sticky="w")

        if turn_idx > 0:
            br_hdr = ctk.CTkFrame(scroll, fg_color="transparent")
            br_hdr.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(br_hdr, text="Narrative Bridge (Transition):", font=("Arial", 12, "bold")).pack(side="left")
            
            # --- RESTORED BRIDGE TOOLS ---
            btn_clear_br = ctk.CTkButton(br_hdr, text="X Clear", width=60, height=24, fg_color="#B71C1C", hover_color="#7F0000")
            btn_clear_br.pack(side="right", padx=2)
            Tooltip(btn_clear_br, "Wipe the textbox below.")

            btn_pol_br = ctk.CTkButton(br_hdr, text="✨ Polish", width=70, height=24, fg_color="#9C27B0", hover_color="#7B1FA2")
            btn_pol_br.pack(side="right", padx=2)
            Tooltip(btn_pol_br, "AI Copy-Edit: Fix grammar/flow of this bridge.")
            
            btn_cond_br = ctk.CTkButton(br_hdr, text="✨ Condense", width=70, height=24, fg_color="#3F51B5", hover_color="#303F9F")
            btn_cond_br.pack(side="right", padx=2)
            Tooltip(btn_cond_br, "AI Edit: Make this bridge shorter and punchier.")
                        
            btn_exp_br = ctk.CTkButton(br_hdr, text="✨ Expand", width=70, height=24, fg_color="#00ACC1", hover_color="#00838F")
            btn_exp_br.pack(side="right", padx=2)
            Tooltip(btn_exp_br, "AI Expansion: Make this bridge slightly longer and more descriptive.")
            
            btn_gen_br = ctk.CTkButton(br_hdr, text="⟳ Reroll", width=70, height=24, fg_color="#F57C00", hover_color="#E65100")
            btn_gen_br.pack(side="right", padx=2)
            Tooltip(btn_gen_br, "Ask AI to generate a brand new bridge connecting the previous action to this prose.")
            
            bridge_box = ctk.CTkTextbox(scroll, height=100, wrap="word", font=self.bridge_font)
            bridge_box._textbox.configure(spacing2=6, font=self.bridge_font)
            bridge_box.insert("1.0", clean_prose(turn.get("narrative_bridge", "")))
            bridge_box.pack(fill="x", pady=(0, 20))
            
            from ui.tooltip import apply_global_text_bindings
            try: apply_global_text_bindings(bridge_box._textbox)
            except: pass
            
            btn_clear_br.configure(command=lambda: bridge_box.delete("1.0", "end"))
            
            def generate_bridge_async():
                btn_gen_br.configure(state="disabled", text="Generating...")
                self.winfo_toplevel().configure(cursor="watch")
                
                # Capture the live, unsaved story text to give the AI accurate context
                current_story = story_box.get("1.0", "end").strip()
                
                def worker():
                    # Temporarily spoof the history so the engine uses our live text
                    actual_story = self.engine.history[turn_idx].get("story_text", "")
                    self.engine.history[turn_idx]["story_text"] = current_story
                    
                    try:
                        b_text = self.engine.request_bridge_generation(turn_idx)
                    finally:
                        self.engine.history[turn_idx]["story_text"] = actual_story
                        
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn_gen_br.configure(state="normal", text="⟳ Reroll")
                        if b_text and b_text not in ["[OK]", "[FAILED]"]:
                            bridge_box.delete("1.0", "end")
                            bridge_box.insert("1.0", clean_prose(b_text))
                        elif b_text == "[OK]":
                            from tkinter import messagebox
                            messagebox.showinfo("Bridge", "The AI determined the transition is already seamless [OK].")
                        else:
                            from tkinter import messagebox
                            messagebox.showerror("Error", "Failed to generate bridge.")
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            def edit_bridge_async(edit_type, btn_ref):
                current_bridge = bridge_box.get("1.0", "end").strip()
                if not current_bridge: return
                
                current_story = story_box.get("1.0", "end").strip()
                
                orig_text = btn_ref.cget("text")
                btn_ref.configure(state="disabled", text="Working...")
                self.winfo_toplevel().configure(cursor="watch")
                
                def worker():
                    # Temporarily spoof the history so the engine uses our live text
                    actual_story = self.engine.history[turn_idx].get("story_text", "")
                    self.engine.history[turn_idx]["story_text"] = current_story
                    
                    try:
                        from api import TomeWeaverAPI
                        success, result = TomeWeaverAPI.edit_narrative_bridge(self.engine, turn_idx, current_bridge, edit_type)
                    finally:
                        self.engine.history[turn_idx]["story_text"] = actual_story
                    
                    def update_ui():
                        self.winfo_toplevel().configure(cursor="")
                        btn_ref.configure(state="normal", text=orig_text)
                        if success and result:
                            clean_res = result.strip('"\'')
                            bridge_box.delete("1.0", "end")
                            bridge_box.insert("1.0", clean_prose(clean_res))
                        else:
                            from tkinter import messagebox
                            messagebox.showerror("Error", f"Failed to {edit_type} bridge.\n{result}")
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            btn_gen_br.configure(command=generate_bridge_async)
            btn_pol_br.configure(command=lambda: edit_bridge_async("polish", btn_pol_br))
            btn_cond_br.configure(command=lambda: edit_bridge_async("condense", btn_cond_br))
            btn_exp_br.configure(command=lambda: edit_bridge_async("expand", btn_exp_br))
        else:
            bridge_box = None

        header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(header_frame, text="Story Prose:", font=("Arial", 16, "bold")).pack(side="left")

        # --- IN-PLACE STORY TOOLS (Non-Destructive) ---
        def edit_story_async(edit_type, btn_ref):
            current_text = story_box.get("1.0", "end").strip()
            if not current_text: return
            
            orig_text = btn_ref.cget("text")
            btn_ref.configure(state="disabled", text="Working...")
            self.winfo_toplevel().configure(cursor="watch")
            
            def worker():
                # 1. Temporarily spoof the history so the engine uses our live text from the textbox
                actual_history_text = self.engine.history[turn_idx].get("story_text", "")
                self.engine.history[turn_idx]["story_text"] = current_text
                
                draft = None
                try:
                    # 2. Call the standard engine generators
                    if edit_type == "polish": draft = self.engine.request_polish(turn_idx)
                    elif edit_type == "condense": draft = self.engine.request_condense(turn_idx)
                    elif edit_type == "expand": draft = self.engine.request_expansion(turn_idx)
                finally:
                    # 3. Restore the true history instantly, regardless of success or failure
                    self.engine.history[turn_idx]["story_text"] = actual_history_text
                    
                    # Discard the draft from the engine state so the Visual Diff window never pops up
                    self.engine.cancel_draft()
                
                def update_ui():
                    btn_ref.configure(state="normal", text=orig_text)
                    self.winfo_toplevel().configure(cursor="")
                    
                    if draft and draft.get("story_text"):
                        story_box.delete("1.0", "end")
                        story_box.insert("1.0", clean_prose(draft.get("story_text", "")))
                    else:
                        from tkinter import messagebox
                        messagebox.showerror("Error", f"Failed to {edit_type} story. Check console.")
                self.after(0, update_ui)
                
            import threading
            threading.Thread(target=worker, daemon=True).start()

        btn_p = ctk.CTkButton(header_frame, text="✨ Polish", width=70, height=24, fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: edit_story_async("polish", btn_p))
        btn_p.pack(side="right", padx=2)
        Tooltip(btn_p, "AI Copy-Edit: Fix grammar/flow of the text in the box below.")

        btn_c = ctk.CTkButton(header_frame, text="✨ Condense", width=70, height=24, fg_color="#3F51B5", hover_color="#303F9F", command=lambda: edit_story_async("condense", btn_c))
        btn_c.pack(side="right", padx=2)
        Tooltip(btn_c, "AI Edit: Make this prose shorter and punchier.")
        
        btn_e = ctk.CTkButton(header_frame, text="✨ Expand", width=70, height=24, fg_color="#00ACC1", hover_color="#00838F", command=lambda: edit_story_async("expand", btn_e))
        btn_e.pack(side="right", padx=2)
        Tooltip(btn_e, "AI Expansion: Add sensory depth to the text below.")

        story_box = ctk.CTkTextbox(scroll, height=350, wrap="word", font=self.prose_font)
        story_box._textbox.configure(spacing2=6, font=self.prose_font)
        story_box.insert("1.0", clean_prose(turn.get("story_text", "")))
        story_box.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(scroll, text="Action Choices:", font=("Arial", 16, "bold")).pack(anchor="w", pady=(10, 5))
        
        choice_rows = []
        choices_container = ctk.CTkFrame(scroll, fg_color="transparent")
        choices_container.pack(fill="x")

        def render_choice_list():
            for w in choices_container.winfo_children(): w.destroy()
            choice_rows.clear()
            
            curr_choices = turn.get("choices", [])
            for i, c_text in enumerate(curr_choices):
                row = ctk.CTkFrame(choices_container, fg_color="transparent")
                row.pack(fill="x", pady=2)
                
                var = ctk.StringVar(value=c_text)
                ctk.CTkLabel(row, text=f"{i+1}.").pack(side="left", padx=5)
                entry = ctk.CTkEntry(row, textvariable=var, font=("Arial", 13))
                entry.pack(side="left", fill="x", expand=True)
                
                if not self.engine.is_campaign:
                    # --- RESTORED INDIVIDUAL REROLL BUTTON ---
                    btn_reroll = ctk.CTkButton(row, text="⟳", width=25, fg_color="#F57C00", hover_color="#E65100")
                    btn_reroll.pack(side="left", padx=2)
                    Tooltip(btn_reroll, "Generate a new action to replace this one.")
                    
                    def do_reroll(target_var=var, target_btn=btn_reroll):
                        target_btn.configure(state="disabled", text="...")
                        current_story = story_box.get("1.0", "end").strip()
                        existing_choices = [v.get().strip() for v in choice_rows if v.get().strip() and v.get().strip() != "New action..."]
                        def worker():
                            from llm import generate_single_choice
                            new_choice = generate_single_choice(current_story, existing_choices)
                            def update_ui():
                                if new_choice: target_var.set(new_choice)
                                else:
                                    from tkinter import messagebox
                                    messagebox.showerror("Error", "Failed to generate a new choice. Check developer console.")
                                target_btn.configure(state="normal", text="⟳")
                            self.after(0, update_ui)
                        import threading
                        threading.Thread(target=worker, daemon=True).start()
                        
                    btn_reroll.configure(command=do_reroll)
                    
                    btn_del = ctk.CTkButton(row, text="X", width=25, fg_color="#B71C1C", hover_color="#7F0000", 
                                            command=lambda idx=i: [turn["choices"].pop(idx), render_choice_list()])
                    btn_del.pack(side="left", padx=2)
                
                choice_rows.append(var)

            if not self.engine.is_campaign:
                btn_row = ctk.CTkFrame(choices_container, fg_color="transparent")
                btn_row.pack(fill="x", pady=(10, 0))
                btn_add = ctk.CTkButton(btn_row, text="+ Add Choice", width=100, fg_color="#4A4A4A", hover_color="#333333",
                                        command=lambda: [turn["choices"].append("New action..."), render_choice_list()])
                btn_add.pack(side="left", padx=(0, 10))
                
                # --- RESTORED REROLL ALL CHOICES BUTTON ---
                btn_reroll_ch = ctk.CTkButton(btn_row, text="⟳ Reroll Choices", width=120, fg_color="#0288D1", hover_color="#01579B",
                                        command=lambda: [dialog.destroy(), self._trigger_redo_choices(turn_idx)])
                btn_reroll_ch.pack(side="left")
                Tooltip(btn_reroll_ch, "Ask AI to generate a fresh set of choices for this exact card.")

        render_choice_list()

        pc_var = None
        if turn.get("player_choice") is not None:
            ctk.CTkLabel(scroll, text="Player Action Taken:", font=("Arial", 14, "bold")).pack(anchor="w", pady=(20, 0))
            pc_var = ctk.StringVar(value=turn.get("player_choice", ""))
            ctk.CTkEntry(scroll, textvariable=pc_var, font=("Arial", 14), text_color="#4CAF50").pack(fill="x", pady=(0, 15))

        def on_save(close_dialog):
            try:
                # 1. Apply UI data directly to the RAM dictionary
                self.engine.history[turn_idx]["location"] = loc_var.get().strip()
                self.engine.history[turn_idx]["pov_character"] = pov_var.get().strip()
                
                import re
                raw_story = story_box.get("1.0", "end").strip()
                
                # Un-escape double quotes (Artifact of pasting raw JSON or external text)
                raw_story = raw_story.replace('\\"', '"')
                
                # Intelligent Spacing: Converts single newlines into proper double-newline paragraphs.
                if '\n' in raw_story and '\n\n' not in raw_story:
                    raw_story = raw_story.replace('\n', '\n\n')
                # Clean up any chaotic spacing
                raw_story = re.sub(r'\n{3,}', '\n\n', raw_story)
                
                self.engine.history[turn_idx]["story_text"] = raw_story
                
                if "choices" in turn: 
                    self.engine.history[turn_idx]["choices"] = [v.get().strip() for v in choice_rows if v.get().strip()]
                
                if pc_var: 
                    self.engine.history[turn_idx]["player_choice"] = pc_var.get().strip()
                    
                if bridge_box is not None:
                    raw_bridge = bridge_box.get("1.0", "end").strip()
                    
                    raw_bridge = raw_bridge.replace('\\"', '"')
                    
                    if '\n' in raw_bridge and '\n\n' not in raw_bridge:
                        raw_bridge = raw_bridge.replace('\n', '\n\n')
                    raw_bridge = re.sub(r'\n{3,}', '\n\n', raw_bridge)
                    
                    if raw_bridge: self.engine.history[turn_idx]["narrative_bridge"] = raw_bridge
                    elif "narrative_bridge" in self.engine.history[turn_idx]: del self.engine.history[turn_idx]["narrative_bridge"]
                
                # 2. Sync RAG visibility and commit physically to disk
                self.engine._resync_all_visibility()
                self.engine.save_state()
                
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save turn data: {e}")
                return
            
            # 3. Handle UI state
            if close_dialog:
                dialog.destroy()
                # Use after() to ensure the dialog is fully destroyed before the main window attempts to redraw
                self.after(50, lambda: self.refresh_timeline(go_to_last=False))
            else:
                # Keep open and refresh the underlying timeline silently
                self.refresh_timeline(go_to_last=False)
                orig_title = dialog.title()
                if "(Saved!)" not in orig_title:
                    dialog.title(f"{orig_title} - (Saved!)")
                    def reset_title():
                        try: dialog.title(orig_title)
                        except: pass
                    dialog.after(2000, reset_title)

        def on_seed_save():
            seed_file = self.engine.adv_dir / "start_turn.json"
            import json
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(turn, f, indent=4)
            messagebox.showinfo("Seed Created", "This turn has been saved as the official Story Seed!\nAny new game will begin exactly here.")

        # --- THE BUTTON FOOTER ---
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", pady=20, padx=20)
        
        # Left Side
        if turn.get("turn", 0) <= 1:
            ctk.CTkButton(btn_row, text="💾 Set as Story Seed", font=("Arial", 12, "bold"), height=36,
                                  fg_color="#1F6AA5", hover_color="#144870", command=on_seed_save).pack(side="left", padx=10)
                                  
        # Right Side (The 3-Button Editor Controls)
        right_group = ctk.CTkFrame(btn_row, fg_color="transparent")
        right_group.pack(side="right")
        
        ctk.CTkButton(right_group, text="Cancel", font=("Arial", 14), height=36, width=100,
                      fg_color="#D32F2F", hover_color="#9A0007", command=dialog.destroy).pack(side="left", padx=5)
                      
        ctk.CTkButton(right_group, text="Save", font=("Arial", 14, "bold"), height=36, width=100,
                      fg_color="#388E3C", hover_color="#1B5E20", command=lambda: on_save(False)).pack(side="left", padx=5)
                      
        ctk.CTkButton(right_group, text="Save & Close", font=("Arial", 14, "bold"), height=36, width=140,
                      fg_color="#2E7D32", hover_color="#1B5E20", command=lambda: on_save(True)).pack(side="left", padx=5)
                      
    # ---------------------------------------------------------
    # UI LOCKS AND AUTOPILOT
    # ---------------------------------------------------------

    def _lock_ui(self, status_msg):
        if status_msg and status_msg != "Ready." and not status_msg.startswith("Autopilot:"):
            from colorama import Style
            print(f"{Style.DIM}[UI] {status_msg}{Style.RESET_ALL}")
            
        self.winfo_toplevel().configure(cursor="watch") 
        self.status_var.set(status_msg)
        self.btn_submit.configure(state="disabled")
        self.text_input.configure(state="disabled")
        self.cmd_dropdown.configure(state="disabled")
        self.slider.configure(state="disabled")
        
        for w in [
            self.btn_first,
            self.btn_prev,
            self.btn_prev_chap,
            self.btn_next_chap,
            self.btn_next,
            self.btn_last,
        ]:
            w.configure(state="disabled")
            
        for panel in [self.bridge_tools, self.story_tools, self.choices_frame, self.hdr_frame]:
            for w in panel.winfo_children():
                if isinstance(w, ctk.CTkButton): w.configure(state="disabled")
                elif isinstance(w, ctk.CTkFrame):
                    for sub_w in w.winfo_children():
                        if isinstance(sub_w, ctk.CTkButton): sub_w.configure(state="disabled")

    def _unlock_ui(self, status_msg):
        if status_msg and status_msg != "Ready." and not status_msg.startswith("Autopilot:"):
            from colorama import Style
            print(f"{Style.DIM}[UI] {status_msg}{Style.RESET_ALL}")
            
        self.winfo_toplevel().configure(cursor="") 
        self.status_var.set(status_msg)
        
        if len(self.engine.history) > 1:
            self.slider.configure(state="normal")
            self.btn_first.configure(state="normal" if self.current_turn_idx > 0 else "disabled")
            self.btn_prev.configure(state="normal" if self.current_turn_idx > 0 else "disabled")
            self.btn_next.configure(state="normal" if self.current_turn_idx < len(self.engine.history) - 1 else "disabled")
            self.btn_last.configure(state="normal" if self.current_turn_idx < len(self.engine.history) - 1 else "disabled")

            curr_turn_val = self.engine.history[self.current_turn_idx].get("turn", 0)
            has_prev_chap = any(
                c.get("start_turn") is not None and c.get("start_turn") < curr_turn_val
                for c in self.engine.chapters
            )
            has_next_chap = any(
                c.get("start_turn") is not None and c.get("start_turn") > curr_turn_val
                for c in self.engine.chapters
            )
            if not has_prev_chap and curr_turn_val > 0:
                has_prev_chap = True

            self.btn_prev_chap.configure(state="normal" if has_prev_chap else "disabled")
            self.btn_next_chap.configure(state="normal" if has_next_chap else "disabled")
            
        is_game_over = False
        if self.engine.history:
            is_game_over = str(self.engine.history[self.current_turn_idx].get("is_game_over", False)).lower() == "true"
            
        for panel in [self.bridge_tools, self.story_tools, self.choices_frame, self.hdr_frame]:
            for w in panel.winfo_children():
                if isinstance(w, ctk.CTkButton): w.configure(state="normal")
                elif isinstance(w, ctk.CTkFrame):
                    for sub_w in w.winfo_children():
                        if isinstance(sub_w, ctk.CTkButton): sub_w.configure(state="normal")

        if self.engine.is_test_mode and self.current_turn_idx == len(self.engine.history) - 1:
            last_turn = self.engine.history[-1]
            
            # ABSOLUTE OVERRIDE: Autopilot ONLY stops if the engine explicitly flagged Mortality or Epilogue.
            # We strictly discard any legacy objective_achieved checks here.
            is_over = str(last_turn.get("is_game_over", False)).lower() == "true"
            
            if is_over:
                self.workspace._toggle_test()
                self.status_var.set("Autopilot finished: Campaign Complete.")
                return
            
            if last_turn.get("choices"):
                auto_choice = last_turn["choices"][0]
                self.status_var.set(f"Autopilot: Selecting '{auto_choice[:20]}...' in 2s")
                def auto_step():
                    if self.engine.is_test_mode: self._execute_action(auto_choice)
                    else: self.status_var.set("Autopilot aborted.")
                self.after(2000, auto_step)

    def _trigger_startup(self):
        self.startup_frame.pack_forget()
        self._lock_ui("Generating opening scene...")
        import threading
        threading.Thread(target=self._async_init, daemon=True).start()
                
    def _async_init(self):
        try: self.engine.initialize_game()
        except Exception as e: self.after(0, lambda: messagebox.showerror("Engine Error", str(e)))
            
        def on_init_complete():
            self.refresh_timeline(go_to_last=True)
            if self.engine.history:
                last_turn = self.engine.history[-1]
                if last_turn.get("player_choice") is not None:
                    self._lock_ui("Resuming interrupted generation...")
                    def worker():
                        result = self.engine.submit_action(last_turn["player_choice"])
                        def update_ui():
                            self.refresh_timeline(go_to_last=True)
                            
                            def on_progress(current, total):
                                if current == "Seeding": msg = "Extracting Base Lore..."
                                elif current == "Condensing": msg = f"{total}..."
                                elif current == "Reconciling": msg = "Merging duplicates..."
                                elif current == "Syncing": msg = "Recalculating Timestamps..."
                                else: msg = f"Processing Chunk {current}/{total}..."
                                self.after(0, lambda: self.status_var.set(f"Background Task: {msg}"))
                                
                            def on_complete(success, msg):
                                self.after(0, lambda: self.status_var.set("Ready."))

                            self.engine._trigger_memory_compilation(progress_callback=on_progress, completion_callback=on_complete)
                        self.after(0, update_ui)
                    import threading
                    threading.Thread(target=worker, daemon=True).start()
        self.after(0, on_init_complete)
        
     
    def _open_chapter_editor(self, turn_idx):
        """Spawns a transactional modal allowing the Director to edit chapters.json metadata."""
        if not self.engine.chapters: return
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Chapter Metadata")
        dialog.geometry("750x600")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self.winfo_toplevel())
        
        # 1. Clone the chapters array into memory for transactional editing
        working_chapters = [c.copy() for c in self.engine.chapters]
        
        # CRITICAL FIX: Preserve the true original titles to prevent auto-saves from blinding the Patcher
        original_titles = {c.get("chapter_number"): c.get("title", "") for c in self.engine.chapters}
        
        # Find the active chapter index based on the current turn
        curr_turn = self.engine.history[turn_idx].get("turn", 1)
        active_c_idx = 0
        for i, c in enumerate(working_chapters):
            s = c.get("start_turn")
            if s is not None and s <= curr_turn:
                active_c_idx = i
                
        state = {"idx": active_c_idx}
        c_vars = {}

        # --- UI LAYOUT ---
        hdr = ctk.CTkFrame(dialog, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(15, 5))
        lbl_hdr = ctk.CTkLabel(hdr, text="", font=("Arial", 18, "bold"), text_color="#00BCD4")
        lbl_hdr.pack(side="left")

        ctk.CTkLabel(dialog, text="Modify the structural metadata for this chapter. This will not change the story prose, but it will update the UI labels and future AI context.", wraplength=700, text_color="gray", justify="left").pack(anchor="w", padx=20, pady=(0, 10))

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=5)

        def add_field(label_text, key, is_multiline=False):
            f = ctk.CTkFrame(scroll, fg_color="transparent")
            f.pack(fill="x", pady=(10, 2))
            ctk.CTkLabel(f, text=label_text, font=("Arial", 14, "bold")).pack(side="left")
            
            if is_multiline:
                box_container = ctk.CTkFrame(scroll, fg_color="transparent")
                box_container.pack(fill="x", padx=10)
                box = ctk.CTkTextbox(box_container, height=80, wrap="word", font=("Arial", 14))
                box.pack(fill="x")
                widget = box
            else:
                var = ctk.StringVar()
                entry = ctk.CTkEntry(f, textvariable=var, font=("Arial", 14))
                entry.pack(side="left", fill="x", expand=True, padx=10)
                widget = var
                
            c_vars[key] = widget

        add_field("Chapter Title:", "title")
        
        row2 = ctk.CTkFrame(scroll, fg_color="transparent")
        row2.pack(fill="x", pady=10)
        
        f_pov = ctk.CTkFrame(row2, fg_color="transparent")
        f_pov.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(f_pov, text="POV Character:", font=("Arial", 12, "bold")).pack(anchor="w")
        c_vars["pov"] = ctk.StringVar()
        ctk.CTkEntry(f_pov, textvariable=c_vars["pov"], font=("Arial", 14)).pack(fill="x")
        
        f_time = ctk.CTkFrame(row2, fg_color="transparent")
        f_time.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(f_time, text="Time Jump:", font=("Arial", 12, "bold")).pack(anchor="w")
        c_vars["time"] = ctk.StringVar()
        ctk.CTkEntry(f_time, textvariable=c_vars["time"], font=("Arial", 14)).pack(fill="x")

        add_field("Location / Environment:", "setting", is_multiline=True)
        
        # --- RENDER LOGIC ---
        def save_current_view():
            """Extracts text from UI and saves it to the working array in memory."""
            c = working_chapters[state["idx"]]
            for k, w in c_vars.items():
                if isinstance(w, ctk.StringVar): c[k] = w.get().strip()
                else: c[k] = w.get("1.0", "end").strip()
                
        def load_view(index):
            """Loads data from the working array into the UI."""
            c = working_chapters[index]
            c_num = c.get("chapter_number", "?")
            s_turn = c.get("start_turn", "?")
            e_turn = c.get("end_turn", "Ongoing")
            
            lbl_hdr.configure(text=f"Editing Chapter {c_num} (Turns {s_turn} - {e_turn})")
            
            for k, w in c_vars.items():
                val = str(c.get(k, ""))
                if isinstance(w, ctk.StringVar): w.set(val)
                else:
                    w.delete("1.0", "end")
                    w.insert("1.0", val)
                    
            btn_prev.configure(state="normal" if index > 0 else "disabled")
            btn_next.configure(state="normal" if index < len(working_chapters) - 1 else "disabled")

        # --- FOOTER BUTTONS ---
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=15)
        
        def on_prev():
            save_current_view()
            state["idx"] -= 1
            load_view(state["idx"])
            
        def on_next():
            save_current_view()
            state["idx"] += 1
            load_view(state["idx"])
            
        btn_prev = ctk.CTkButton(btn_frame, text="< Prev Chapter", width=120, fg_color="#4A4A4A", hover_color="#333333", command=on_prev)
        btn_prev.pack(side="left")
        
        btn_next = ctk.CTkButton(btn_frame, text="Next Chapter >", width=120, fg_color="#4A4A4A", hover_color="#333333", command=on_next)
        btn_next.pack(side="left", padx=10)
        
        def on_save():
            save_current_view() # Flush the active UI state to the array
            
            # --- THE BOUNDARY PATCHER ---
            # Compare the final submitted titles against the original preserved titles
            for new_c in working_chapters:
                c_num = new_c.get("chapter_number")
                s_turn = new_c.get("start_turn")
                new_title = new_c.get("title", "").strip()
                
                orig_title = original_titles.get(c_num, "").strip()
                
                if orig_title != new_title and s_turn and s_turn > 1:
                    
                    # Safely locate the boundary turn by its actual turn integer, rather than array index
                    target_turn_val = s_turn - 1
                    b_turn = next((t for t in self.engine.history if t.get("turn") == target_turn_val), None)
                    
                    if b_turn:
                        import re
                        
                        def patch_choice(text):
                            if not text: return text
                            # Only patch if it is actually the transition choice for THIS chapter
                            if re.search(rf"^start\s*chapter\s*{c_num}\b", text, re.IGNORECASE):
                                # Preserve narrative bridge suffix if present, e.g., "(He walked in.)"
                                suffix = ""
                                m = re.search(r"(\(.*?\))$", text)
                                if m: suffix = f" {m.group(1)}"
                                
                                # DIRECT WHOLESALE REPLACEMENT
                                return f"Start Chapter {c_num}: {new_title}{suffix}"
                            return text

                        # 1. Update the literal Player Choice
                        pc = b_turn.get("player_choice", "")
                        b_turn["player_choice"] = patch_choice(pc)
                                
                        # 2. Update the Green Button choices array
                        choices = b_turn.get("choices", [])
                        for i, choice in enumerate(choices):
                            choices[i] = patch_choice(choice)
                                    
            # Overwrite engine state and commit
            self.engine.chapters = working_chapters 
            self.engine.save_state()
            dialog.destroy()
            self.refresh_timeline(go_to_last=False)
            
        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#D32F2F", hover_color="#9A0007", command=dialog.destroy).pack(side="right")
        ctk.CTkButton(btn_frame, text="💾 Save Changes", width=140, font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=on_save).pack(side="right", padx=10)

        load_view(state["idx"])