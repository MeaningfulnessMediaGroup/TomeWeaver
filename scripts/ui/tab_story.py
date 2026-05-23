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
        super().__init__(master, **kwargs)
        self.rows = []

    def flow(self, pill_widgets):
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
        
        # Center the slider vertically within its frame by adding matching top/bottom padding
        self.btn_first = ctk.CTkButton(self.timeline_frame, text="|<<", width=40, fg_color="#4A4A4A", hover_color="#333333", command=lambda: self._navigate_timeline("first"))
        self.btn_first.pack(side="left", padx=2, pady=5)
        
        self.btn_prev = ctk.CTkButton(self.timeline_frame, text="<", width=40, fg_color="#4A4A4A", hover_color="#333333", command=lambda: self._navigate_timeline("prev"))
        self.btn_prev.pack(side="left", padx=(2, 10), pady=5)
        
        self.slider = ctk.CTkSlider(self.timeline_frame, command=self._on_slider_move)
        self.slider.pack(side="left", fill="x", expand=True, padx=10, pady=5)
        
        self.btn_next = ctk.CTkButton(self.timeline_frame, text=">", width=40, fg_color="#4A4A4A", hover_color="#333333", command=lambda: self._navigate_timeline("next"))
        self.btn_next.pack(side="left", padx=(10, 2), pady=5)
        
        self.btn_last = ctk.CTkButton(self.timeline_frame, text=">>|", width=40, fg_color="#4A4A4A", hover_color="#333333", command=lambda: self._navigate_timeline("last"))
        self.btn_last.pack(side="left", padx=2, pady=5)

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

        self.refresh_timeline(go_to_last=True)


    # ---------------------------------------------------------
    # TIMELINE & NAVIGATION LOGIC
    # ---------------------------------------------------------

    def refresh_timeline(self, go_to_last=False):
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
        # Equalize the padding surrounding the timeline slider (10px top, 10px bottom)
        self.timeline_frame.pack(fill="x", padx=20, pady=10)
        self.input_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        if go_to_last:
            self.current_turn_idx = history_len - 1
            
        if history_len > 1:
            self.slider.configure(state="normal", from_=0, to=history_len - 1, number_of_steps=history_len - 1)
            self.slider.set(self.current_turn_idx)
            
            self.btn_first.configure(state="normal" if self.current_turn_idx > 0 else "disabled")
            self.btn_prev.configure(state="normal" if self.current_turn_idx > 0 else "disabled")
            self.btn_next.configure(state="normal" if self.current_turn_idx < history_len - 1 else "disabled")
            self.btn_last.configure(state="normal" if self.current_turn_idx < history_len - 1 else "disabled")
        else:
            # FIX: CustomTkinter crashes if 'from' and 'to' are identical. Provide safe dummy bounds.
            self.slider.configure(from_=0, to=1, number_of_steps=1)
            self.slider.set(0)
            self.slider.configure(state="disabled")
            for btn in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
                btn.configure(state="disabled")
                
        self._render_turn()

    def _on_slider_move(self, value):
        idx = int(value)
        if idx != self.current_turn_idx:
            self.current_turn_idx = idx
            self.refresh_timeline(go_to_last=False)

    def _navigate_timeline(self, direction):
        if direction == "first": self.current_turn_idx = 0
        elif direction == "prev" and self.current_turn_idx > 0: self.current_turn_idx -= 1
        elif direction == "next" and self.current_turn_idx < len(self.engine.history) - 1: self.current_turn_idx += 1
        elif direction == "last": self.current_turn_idx = len(self.engine.history) - 1
        self.refresh_timeline(go_to_last=False)


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
        cheats_allowed = self.engine.setup_data.get("allow_cheats", False)
        
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
            # Flatten to single line for the header display
            flat_action = raw_action.replace("\n", " ").replace("\r", " ")
            
            # 1. Pack button to the far RIGHT first so it stays fixed
            self.btn_action_more.pack(side="right", padx=(10, 0))
            self.btn_action_more.configure(command=lambda a=raw_action: self._show_full_action(a))
            
            # 2. Pack label to the LEFT and allow it to expand into the remaining middle space
            self.lbl_action.pack(side="left", fill="x", expand=True)
            # We provide the full text and set anchor="w" (West/Left). 
            # CustomTkinter will naturally clip the text at the button's margin.
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
            if idx > 0:
                self.bridge_tools.pack(fill="x", pady=(5, 0))
                ctk.CTkLabel(self.bridge_tools, text="Bridge:", font=("Arial", 11, "bold"), text_color="#90CAF9", width=40).pack(side="left")

                
                if is_valid_bridge:
                
                    btn_gen = ctk.CTkButton(self.bridge_tools, text="⟳ Reroll", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100", command=lambda: self._generate_bridge(idx))
                    btn_gen.pack(side="left", padx=2)
                    Tooltip(btn_gen, "Ask AI to regenerate a new version of the transition.")
                    
                    btn_exp = ctk.CTkButton(self.bridge_tools, text="✨ Expand", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F", command=lambda: self._trigger_bridge_edit(idx, "expand"))
                    btn_exp.pack(side="left", padx=2)
                    Tooltip(btn_exp, "AI Expansion: Make this bridge slightly longer and more descriptive.")
                    
                    btn_cond = ctk.CTkButton(self.bridge_tools, text="✨ Condense", width=60, height=24, font=("Arial", 11), fg_color="#3F51B5", hover_color="#303F9F", command=lambda: self._trigger_bridge_edit(idx, "condense"))
                    btn_cond.pack(side="left", padx=2)
                    Tooltip(btn_cond, "AI Edit: Make this bridge shorter and punchier.")
                    
                    btn_pol = ctk.CTkButton(self.bridge_tools, text="✨ Polish", width=60, height=24, font=("Arial", 11), fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: self._trigger_bridge_edit(idx, "polish"))
                    btn_pol.pack(side="left", padx=2)
                    Tooltip(btn_pol, "AI Copy-Edit: Fix grammar/flow of this bridge.")
                    
                    btn_edit_br = ctk.CTkButton(self.bridge_tools, text="✎ Edit", width=50, height=24, font=("Arial", 11), fg_color="#4A4A4A", hover_color="#333333", command=lambda idx=idx: self._open_edit_dialog(idx))
                    btn_edit_br.pack(side="left", padx=2)
                    Tooltip(btn_edit_br, "Manually edit this bridge.")
                    
                    btn_del = ctk.CTkButton(self.bridge_tools, text="X", width=28, height=24, font=("Arial", 11), fg_color="#B71C1C", hover_color="#7F0000", command=lambda: self._delete_bridge(idx))
                    btn_del.pack(side="left", padx=2)
                    Tooltip(btn_del, "Delete this transition.")
                    
                else:
                
                    btn_gen = ctk.CTkButton(self.bridge_tools, text="✨ Generate", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#E65100", command=lambda: self._generate_bridge(idx))
                    btn_gen.pack(side="left", padx=2)
                    Tooltip(btn_gen, "Ask AI to generate a narrative transition from the previous turn into this turn based on the selected choice.")
                

            self.story_tools.pack(fill="x", pady=(5, 5))
            ctk.CTkLabel(self.story_tools, text="Story:", font=("Arial", 11, "bold"), text_color="white", width=40).pack(side="left")
            
            if idx == history_len - 1:
                btn_redo = ctk.CTkButton(self.story_tools, text="⟳ Redo Turn", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100", command=self._trigger_redo)
                btn_redo.pack(side="left", padx=2)
                Tooltip(btn_redo, "Reroll this entire scene from scratch.")
                
            btn_rc = ctk.CTkButton(self.story_tools, text="⟳ Choices", width=60, height=24, font=("Arial", 11), fg_color="#0288D1", hover_color="#01579B", command=lambda: self._trigger_redo_choices(idx))
            btn_rc.pack(side="left", padx=2)
            Tooltip(btn_rc, "Keep text, but get new choices.")
            
            btn_exp = ctk.CTkButton(self.story_tools, text="✨ Expand", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F", command=lambda: self._trigger_expansion(idx))
            btn_exp.pack(side="left", padx=2)
            Tooltip(btn_exp, "AI Expansion: Add sensory depth to this scene.")

            btn_cond = ctk.CTkButton(self.story_tools, text="✨ Condense", width=60, height=24, font=("Arial", 11), fg_color="#3F51B5", hover_color="#303F9F", command=lambda: self._trigger_condense(idx))
            btn_cond.pack(side="left", padx=2)
            Tooltip(btn_cond, "AI Edit: Make this prose shorter and punchier.")
            
            btn_pol = ctk.CTkButton(self.story_tools, text="✨ Polish", width=60, height=24, font=("Arial", 11), fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: self._trigger_polish(idx))
            btn_pol.pack(side="left", padx=2)
            Tooltip(btn_pol, "AI Copy-Edit: Fix grammar/flow of this scene.")
            
            if cheats_allowed:
                btn_fix = ctk.CTkButton(self.story_tools, text="✨ Fix...", width=60, height=24, font=("Arial", 11), fg_color="#009688", hover_color="#00796B", command=lambda: self._trigger_fix(idx))
                btn_fix.pack(side="left", padx=2)
                Tooltip(btn_fix, "Instruct AI to change a specific detail.")
                
            # Right-aligned buttons (Packed in reverse order: Undo on the far right, Edit next to it)
            if cheats_allowed and idx == history_len - 1 and history_len > 1:
                btn_undo = ctk.CTkButton(self.story_tools, text="↶ Undo Turn", width=100, height=24, fg_color="#B71C1C", hover_color="#7F0000", command=self.on_undo)
                btn_undo.pack(side="right", padx=2)
                Tooltip(btn_undo, "Revert the game state to the previous turn.")
                
            if cheats_allowed:
                btn_edit_card = ctk.CTkButton(self.story_tools, text="✎ Edit Scene", width=90, height=24, fg_color="#4A4A4A", hover_color="#333333", command=lambda idx=idx: self._open_edit_dialog(idx))
                btn_edit_card.pack(side="right", padx=2)
                Tooltip(btn_edit_card, "Open the Narrative Editor to manually type changes.")

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
        if self.text_input.cget("state") == "disabled": return
        raw_text = self.text_input.get().strip()
        if not raw_text: return
        
        cmd_type = self.cmd_dropdown.get() if not self.engine.is_campaign else "Standard Action"
        self.text_input.delete(0, 'end') 
        
        if cmd_type == "Force Chapter":
            self._lock_ui("Architecting transition...")
            def worker():
                # Passes the raw description to be handled by the three-step engine logic
                result = self.engine.trigger_manual_chapter(prompt_desc=raw_text)
                self.after(0, lambda: self.refresh_timeline(go_to_last=True))
            import threading
            threading.Thread(target=worker, daemon=True).start()
            return

        # Standard routing for other commands
        if cmd_type == "Expand Notes": final_action = f"EXPAND: {raw_text}"
        elif cmd_type == "Force Setting": final_action = f"setting: {raw_text}"
        elif cmd_type == "Force Time": final_action = f"time: {raw_text}"
        elif cmd_type == "Force POV": final_action = f"pov: {raw_text}"
        else: final_action = raw_text

        self._execute_action(final_action)
        
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

    def on_undo(self):
        self._lock_ui("Undoing last choice...")
        def worker():
            self.engine.undo()
            self.after(0, lambda: self.refresh_timeline(go_to_last=True))
        threading.Thread(target=worker, daemon=True).start()

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
        ctk.CTkEntry(meta_grid, textvariable=loc_var, width=350, font=("Arial", 13)).grid(row=1, column=0, padx=(0, 20), sticky="w")
        
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
                def worker():
                    b_text = self.engine.request_bridge_generation(turn_idx)
                    def update_ui():
                        if b_text and b_text not in ["[OK]", "[FAILED]"]:
                            bridge_box.delete("1.0", "end")
                            bridge_box.insert("1.0", clean_prose(b_text))
                        elif b_text == "[OK]":
                            from tkinter import messagebox
                            messagebox.showinfo("Bridge", "The AI determined the transition is already seamless [OK].")
                        else:
                            from tkinter import messagebox
                            messagebox.showerror("Error", "Failed to generate bridge.")
                        btn_gen_br.configure(state="normal", text="⟳ Reroll")
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            def edit_bridge_async(edit_type, btn_ref):
                current_bridge = bridge_box.get("1.0", "end").strip()
                if not current_bridge: return
                orig_text = btn_ref.cget("text")
                btn_ref.configure(state="disabled", text="Working...")
                def worker():
                    from api import TomeWeaverAPI
                    # Pass the Engine so the API can construct the full Narrative Sandwich + RAG Lore
                    success, result = TomeWeaverAPI.edit_narrative_bridge(self.engine, turn_idx, current_bridge, edit_type)
                    
                    def update_ui():
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

        # --- RESTORED STORY TOOLS ---
        btn_p = ctk.CTkButton(header_frame, text="✨ Polish", width=70, height=24, fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: [dialog.destroy(), self._trigger_polish(turn_idx)])
        btn_p.pack(side="right", padx=2)
        Tooltip(btn_p, "AI Copy-Edit: Fix grammar/flow in this specific card.")

        btn_c = ctk.CTkButton(header_frame, text="✨ Condense", width=70, height=24, fg_color="#3F51B5", hover_color="#303F9F", command=lambda: [dialog.destroy(), self._trigger_condense(turn_idx)])
        btn_c.pack(side="right", padx=2)
        Tooltip(btn_c, "AI Edit: Make this prose shorter and punchier.")
        
        btn_e = ctk.CTkButton(header_frame, text="✨ Expand", width=70, height=24, fg_color="#00ACC1", hover_color="#00838F", command=lambda: [dialog.destroy(), self._trigger_expansion(turn_idx)])
        btn_e.pack(side="right", padx=2)
        Tooltip(btn_e, "AI Expansion: Add sensory depth to this specific card.")

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

        def on_save():
            self.engine.history[turn_idx]["location"] = loc_var.get().strip()
            self.engine.history[turn_idx]["pov_character"] = pov_var.get().strip()
            self.engine.history[turn_idx]["story_text"] = story_box.get("1.0", "end").strip().replace("\n", "\\n")
            if "choices" in turn: 
                self.engine.history[turn_idx]["choices"] = [v.get().strip() for v in choice_rows if v.get().strip()]
            
            if pc_var: 
                self.engine.history[turn_idx]["player_choice"] = pc_var.get().strip()
                
            if bridge_box is not None:
                b_text = bridge_box.get("1.0", "end").strip().replace("\n", "\\n")
                if b_text: self.engine.history[turn_idx]["narrative_bridge"] = b_text
                elif "narrative_bridge" in self.engine.history[turn_idx]: del self.engine.history[turn_idx]["narrative_bridge"]
            
            self.engine._resync_all_visibility()
            self.engine.save_state()
            self._render_turn() 
            dialog.destroy()

        def on_seed_save():
            seed_file = self.engine.adv_dir / "start_turn.json"
            import json
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(turn, f, indent=4)
            messagebox.showinfo("Seed Created", "This turn has been saved as the official Story Seed!\nAny new game will begin exactly here.")

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", pady=20, padx=20)
        
        ctk.CTkButton(btn_row, text="Commit All Changes", font=("Arial", 14, "bold"), height=40,
                      fg_color="#2E7D32", hover_color="#1B5E20", command=on_save).pack(side="right", padx=10)
        
        if turn.get("turn", 0) <= 1:
            ctk.CTkButton(btn_row, text="💾 Set as Story Seed", font=("Arial", 12, "bold"), height=40,
                                  fg_color="#1F6AA5", hover_color="#144870", command=on_seed_save).pack(side="left", padx=10)
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
        
        for w in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
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