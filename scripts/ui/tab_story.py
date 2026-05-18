"""
    TomeWeaver: Story Timeline UI
    -----------------------------
    The core gameplay interface. Displays the adventure as a series of cards.
    Implements UI Virtualization (re-using 3 cards) to maintain high performance 
    even if the story grows to 500+ turns. Handles user input, Non-Destructive 
    Editing (Visual Diffs), and asynchronous engine communication.
"""
import threading
import customtkinter as ctk
from tkinter import messagebox
from ui.tooltip import Tooltip


class StoryTab(ctk.CTkFrame):

    """
    Story Timeline UI
    """
    def __init__(self, parent, engine, workspace):
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        self.workspace = workspace

        # --- FONT & STYLE SETTINGS ---
        from config import ENGINE_CONFIG
        f_family = ENGINE_CONFIG.get("prose_font_family", "Georgia")
        f_size = ENGINE_CONFIG.get("prose_font_size", 15)
        
        self.prose_font = (f_family, int(f_size))
        self.header_font = ("Arial", 12)
        self.action_font = ("Arial", 14, "bold")
        self.bridge_font = (f_family, max(10, int(f_size)-1), "italic")
        
        # --- VIRTUALIZATION & RESIZE STATE ---
        self.MAX_CARDS = 3
        self.current_top_idx = 0
        self.recycled_cards = []
        self._resize_timer = None
        self._last_width = 0

        # --- LAYOUT: Timeline & Virtual Scrollbar ---
        top_area = ctk.CTkFrame(self, fg_color="transparent")
        top_area.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.timeline = ctk.CTkScrollableFrame(top_area, fg_color="transparent")
        self.timeline.pack(side="left", fill="both", expand=True)

        slider_frame = ctk.CTkFrame(top_area, fg_color="transparent", width=40)
        slider_frame.pack(side="right", fill="y", padx=(5, 0))
        
        ctk.CTkLabel(slider_frame, text="Time\nTravel", font=("Arial", 10, "bold"), text_color="gray").pack(pady=(0, 5))
        self.history_slider = ctk.CTkSlider(slider_frame, orientation="vertical", command=self._on_slider_move)
        self.history_slider.pack(fill="y", expand=True)

        # --- LAYOUT: Bottom Input Bar ---
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.cmd_dropdown = ctk.CTkOptionMenu(
            input_frame, 
            values=["Standard Action", "Expand Notes", "Force Setting", "Force Time", "Force POV"],
            width=140
        )
        
        # Only show Director Overrides in Sandbox Mode
        if not self.engine.is_campaign:
            self.cmd_dropdown.pack(side="left", padx=10, pady=15)

        self.text_input = ctk.CTkEntry(input_frame, placeholder_text="Type a custom action or dialogue...", font=("Arial", 14))
        self.text_input.pack(side="left", fill="x", expand=True, padx=10, pady=15)
        self.text_input.bind("<Return>", lambda e: self.on_submit())

        self.btn_submit = ctk.CTkButton(input_frame, text="Submit", command=self.on_submit, width=100)
        self.btn_submit.pack(side="right", padx=10, pady=15)

        self.status_var = ctk.StringVar(value="Ready.")
        ctk.CTkLabel(self, textvariable=self.status_var, font=("Arial", 12, "italic"), text_color="gray").pack(side="bottom", anchor="w", padx=15, pady=(0, 5))

        # --- INITIALIZATION ---
        self._initialize_recycled_cards()
        self.refresh_timeline()
        # Start the silent heartbeat to manage text wrapping
        self._wrap_heartbeat()


    # ---------------------------------------------------------
    # GEOMETRY WRAPPING & SMART SCROLLING
    # ---------------------------------------------------------

    def _apply_wrapping(self, width):
        """Forces the Tkinter text labels to wrap cleanly based on canvas width."""
        from config import ENGINE_CONFIG
        wrap_margin = ENGINE_CONFIG.get("ui_wrap_margin", 150)
        
        safe_width = width - wrap_margin 
        scale = self._get_widget_scaling()
        adjusted_wrap = int(safe_width / scale)
        
        for refs in self.recycled_cards:
            refs["prose"].configure(wraplength=adjusted_wrap)
            refs["hdr"].configure(wraplength=max(50, adjusted_wrap - 80))
            refs["choice"].configure(wraplength=adjusted_wrap)
            # Apply wrapping to the new Bridge Card
            refs["br_prose"].configure(wraplength=adjusted_wrap)
            refs["br_hdr"].configure(wraplength=max(50, adjusted_wrap - 80))

    def _wrap_heartbeat(self):
        """
        An infinitely repeating background loop. Checks if the user resized the 
        application window, and recalculates the paragraph wrapping boundaries if so.
        """
        current_width = self.timeline._parent_canvas.winfo_width()
        if current_width > 100 and current_width != self._last_width:
            self._last_width = current_width
            self._apply_wrapping(current_width)
        self.after(200, self._wrap_heartbeat)

    def _force_scroll_bottom(self):
        """Forces the Canvas to update its bounding box, then drops to the absolute floor."""
        self.timeline.update_idletasks()
        
        # Manually force the canvas to recognize the exact physical height of all the cards
        bbox = self.timeline._parent_canvas.bbox("all")
        if bbox:
            self.timeline._parent_canvas.configure(scrollregion=bbox)
            
        # Now that the canvas knows its true height, 1.0 will flawlessly hit the bottom
        self.timeline._parent_canvas.yview_moveto(1.0)

    # ---------------------------------------------------------
    # WIDGET VIRTUALIZATION (The 3-Card Engine)
    # ---------------------------------------------------------

    def _initialize_recycled_cards(self):
        """
        Creates exactly 3 empty Card templates and 3 Bridge templates in memory.
        Instead of destroying and recreating UI elements (which causes memory leaks),
        we simply slide data in and out of these permanent widget shells.
        """
        from ui.tooltip import Tooltip
        
        for _ in range(self.MAX_CARDS):
            # --- 1. THE BRIDGE CARD ---
            br_card = ctk.CTkFrame(self.timeline, corner_radius=10, fg_color=("#EBEBEB", "#22252A"), border_width=1, border_color=("#D3D3D3", "#343638"))
            
            br_hdr_frame = ctk.CTkFrame(br_card, fg_color="transparent")
            br_hdr_frame.pack(fill="x", padx=15, pady=(10, 5))
            
            br_btn_del = ctk.CTkButton(br_hdr_frame, text="X", width=28, height=24, fg_color="#B71C1C", hover_color="#7F0000")
            Tooltip(br_btn_del, "Delete this narrative bridge.")
            
            br_btn_gen = ctk.CTkButton(br_hdr_frame, text="✨", width=28, height=24, fg_color="#00ACC1", hover_color="#00838F")
            Tooltip(br_btn_gen, "Ask AI to regenerate this bridge.")
            
            br_btn_edit = ctk.CTkButton(br_hdr_frame, text="✎ Edit", width=50, height=24, fg_color="#4A4A4A", hover_color="#333333")
            Tooltip(br_btn_edit, "Open the Narrative Editor to tweak this bridge.")
            
            br_hdr_lbl = ctk.CTkLabel(br_hdr_frame, text="", text_color="gray", font=self.header_font, justify="left", anchor="w")
            br_hdr_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            br_prose_lbl = ctk.CTkLabel(br_card, text="", font=self.prose_font, justify="left", anchor="w")
            br_prose_lbl.pack(fill="x", padx=20, pady=(5, 25))

            # --- 2. THE STORY CARD ---
            card = ctk.CTkFrame(self.timeline, corner_radius=10, fg_color=("#EBEBEB", "#22252A"), border_width=1, border_color=("#D3D3D3", "#343638"))
            
            hdr_frame = ctk.CTkFrame(card, fg_color="transparent")
            hdr_frame.pack(fill="x", padx=15, pady=(10, 0)) # Reduced bottom padding to make room for inventory
            
            btn_edit = ctk.CTkButton(hdr_frame, text="✎ Edit", width=50, height=24, fg_color="#4A4A4A", hover_color="#333333")
            btn_bridge = ctk.CTkButton(hdr_frame, text="✨ Bridge", width=60, height=24, fg_color="#00ACC1", hover_color="#00838F")
            
            hdr_lbl = ctk.CTkLabel(hdr_frame, text="", text_color="gray", font=self.header_font, justify="left", anchor="w")
            hdr_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            # Sub-header for Inventory & Status
            inv_frame = ctk.CTkFrame(card, fg_color="transparent")
            inv_frame.pack(fill="x", padx=15, pady=(0, 5))
            inv_lbl = ctk.CTkLabel(inv_frame, text="", text_color="#0288D1", font=self.header_font, justify="left", anchor="w")
            inv_lbl.pack(side="left", fill="x", expand=True, padx=2)
            
            prose_lbl = ctk.CTkLabel(card, text="", font=self.prose_font, justify="left", anchor="w")
            prose_lbl.pack(fill="x", padx=20, pady=5)
            
            c_lbl = ctk.CTkLabel(card, text="", font=self.action_font, text_color="#4CAF50", justify="left", anchor="w")
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            
            self.recycled_cards.append({
                "br_card": br_card, "br_hdr": br_hdr_lbl, "br_prose": br_prose_lbl, 
                "br_btn_edit": br_btn_edit, "br_btn_gen": br_btn_gen, "br_btn_del": br_btn_del,
                "card": card, "hdr": hdr_lbl, "inv_frame": inv_frame, "inv_lbl": inv_lbl, 
                "prose": prose_lbl, "btn_edit": btn_edit, "btn_bridge": btn_bridge,
                "choice": c_lbl, "btn_frame": btn_frame
            })

    def refresh_timeline(self):
        """
        Master Update Endpoint. Syncs the slider scale to the history length, 
        evaluates UI configurations, and triggers a visual render of the cards.
        """
        
        # 1. Repoll the global config
        from config import ENGINE_CONFIG
        f_family = ENGINE_CONFIG.get("prose_font_family", "Georgia")
        f_size = ENGINE_CONFIG.get("prose_font_size", 15)
        self.prose_font = (f_family, int(f_size))
        self.bridge_font = (f_family, max(10, int(f_size)-1), "italic")
        
        # 2. Force all recycled textboxes to adopt the new font immediately
        for refs in self.recycled_cards:
            refs["prose"].configure(font=self.prose_font)
            refs["br_prose"].configure(font=self.bridge_font)
        
        # Toggle Global Undo Button Visibility dynamically
        self.btn_submit.pack_forget()
        self.btn_submit.pack(side="right", padx=10, pady=15)

        if not self.engine.history:
            self._lock_ui("Initializing story...")
            threading.Thread(target=self._async_init, daemon=True).start()
            return

        # Resume Session Hook (If engine crashed before LLM could reply)
        last_turn = self.engine.history[-1]
        if last_turn.get("player_choice") is not None:
            if self.btn_submit.cget("state") == "normal":
                self._lock_ui("Resuming interrupted generation...")
                def worker():
                    action_to_resume = last_turn["player_choice"]
                    self.engine.submit_action(action_to_resume)
                    self.after(0, self.refresh_timeline)
                threading.Thread(target=worker, daemon=True).start()

        max_start = max(0, len(self.engine.history) - self.MAX_CARDS)
        if max_start > 0:
            self.history_slider.configure(state="normal", from_=max_start, to=0, number_of_steps=max_start)
            self.history_slider.set(max_start)
        else:
            self.history_slider.configure(from_=1, to=0, number_of_steps=1) 
            self.history_slider.set(0)
            self.history_slider.configure(state="disabled")

        self.current_top_idx = max_start
        self._render_visible_cards(auto_scroll=True)
        self._unlock_ui("Ready.")

    def _on_slider_move(self, value):
        """Callback for the 'Time Travel' scroll bar."""
        new_idx = int(value)
        if new_idx != self.current_top_idx:
            self.current_top_idx = new_idx
            self._render_visible_cards(auto_scroll=False)
            # When manually browsing history, always snap to the top of the slice
            self.timeline._parent_canvas.yview_moveto(0.0)

    def _render_visible_cards(self, auto_scroll=False):
        """
        Draws the actual history data into the 3 empty widget shells.
        Automatically unpacks tools (like Edit, Polish, Fix) depending on 
        whether the turn is historical or active.
        """
        history = self.engine.history
        cheats_allowed = self.engine.setup_data.get("allow_cheats", False)
        from ui.tooltip import Tooltip

        # 0. Unpack EVERYTHING first to guarantee correct visual rendering order
        for refs in self.recycled_cards:
            refs["br_card"].pack_forget()
            refs["card"].pack_forget()

        for i in range(self.MAX_CARDS):
            target_idx = self.current_top_idx + i
            refs = self.recycled_cards[i]
            
            if target_idx < len(history):
                turn = history[target_idx]
                
                # 1. RENDER BRIDGE CARD (Packed FIRST so it sits above the Story Card)
                bridge = turn.get("narrative_bridge")
                is_valid_bridge = bridge and bridge not in ["[OK]", "[FAILED]", ""]
                
                if target_idx > 0 and is_valid_bridge:
                    # Reduced top padding from 15 to 5, so it visually hugs the previous action
                    refs["br_card"].pack(fill="x", padx=20, pady=(5, 0))
                    refs["br_hdr"].configure(text=f"Narrative Bridge between Turn {target_idx-1} and Turn {target_idx}")
                    refs["br_prose"].configure(text=bridge)
                    if cheats_allowed:
                        refs["br_btn_del"].pack(side="right", padx=(5, 0))
                        refs["br_btn_gen"].pack(side="right", padx=(5, 0))
                        refs["br_btn_edit"].pack(side="right", padx=(5, 0))
                        
                        refs["br_btn_edit"].configure(command=lambda idx=target_idx: self._open_edit_dialog(idx))
                        refs["br_btn_gen"].configure(command=lambda idx=target_idx: self._generate_bridge_timeline(idx))
                        refs["br_btn_del"].configure(command=lambda idx=target_idx: self._delete_bridge_timeline(idx))
                    else:
                        refs["br_btn_del"].pack_forget()
                        refs["br_btn_gen"].pack_forget()
                        refs["br_btn_edit"].pack_forget()

                # 2. RENDER STORY CARD (Packed SECOND)
                refs["card"].pack(fill="x", padx=20, pady=10) 
                
                loc = turn.get("location", "Unknown")
                pov = turn.get("pov_character", "Unknown")
                refs["hdr"].configure(text=f"Turn {turn.get('turn', '?')} • [{loc}] • POV: {pov}")
                
                # Conditionally render the Inventory Sub-Header
                refs["inv_frame"].pack_forget()
                if self.engine.track_inventory:
                    inv_data = turn.get("inventory_and_state", "")
                    if inv_data:
                        refs["inv_frame"].pack(fill="x", padx=15, pady=(0, 5))
                        refs["inv_lbl"].configure(text=f"Status: {inv_data}")
                
                refs["btn_edit"].pack_forget()
                refs["btn_bridge"].pack_forget()
                
                if cheats_allowed:
                    refs["btn_edit"].pack(side="right")
                    refs["btn_edit"].configure(command=lambda idx=target_idx: self._open_edit_dialog(idx))
                    
                    # RENDER '✨ BRIDGE' BUTTON: Only if bridge is missing/failed and not perfectly seamless [OK]
                    if target_idx > 0 and not is_valid_bridge and bridge != "[OK]":
                        refs["btn_bridge"].pack(side="right", padx=(0, 5))
                        refs["btn_bridge"].configure(command=lambda idx=target_idx: self._generate_bridge_timeline(idx))
                        Tooltip(refs["btn_bridge"], "Generate a narrative transition from the previous turn.")
                        
                prose_text = turn.get("story_text", "").replace("\\n", "\n") + "\n"
                refs["prose"].configure(text=prose_text)
                
                # 3. RENDER FOOTER
                refs["choice"].pack_forget()
                refs["btn_frame"].pack_forget()
                for w in refs["btn_frame"].winfo_children(): w.destroy()
                
                choice = turn.get("player_choice")
                if choice is not None:
                    # RENDER PAST TURN (Just shows what the player typed/clicked)
                    refs["choice"].configure(text=f"❯ {choice}")
                    # FIX ARROW 1: Massive 25px top padding to separate the old choice from the prose
                    refs["choice"].pack(fill="x", padx=20, pady=(25, 20))
                else:
                    # RENDER ACTIVE TURN (Shows Director Tools and Choices)
                    refs["btn_frame"].pack(fill="x", padx=15, pady=(0, 20))
                    
                    is_over = str(turn.get("is_game_over", False)).lower() == "true"
                    is_victory = turn.get("chapter_goal_achieved", False)
                    
                    show_redo = True
                    if is_over and is_victory:
                        e_style = self.engine.setup_data.get("narrative", {}).get("epilogue", "expand").lower()
                        if e_style in ["as_is", "none"]: show_redo = False

                    show_qol = not is_over
                    show_fix = cheats_allowed and not is_over

                    # Tools are hidden during Auto-Play
                    if not self.engine.is_test_mode:
                        # Always create the director frame so Undo has a place to live
                        dir_frame = ctk.CTkFrame(refs["btn_frame"], fg_color="transparent")
                        # FIX ARROW 3: 20px top margin separating the prose from the colorful buttons
                        dir_frame.pack(fill="x", pady=(20, 15), padx=5)
                        
                        if show_redo:
                            btn_rt = ctk.CTkButton(dir_frame, text="⟳ Redo Turn", width=60, fg_color="#F57C00", hover_color="#E65100", command=self._trigger_redo)
                            btn_rt.pack(side="left", padx=(0, 5))
                            Tooltip(btn_rt, "Reroll this entire scene.")

                        if show_qol:
                            btn_rc = ctk.CTkButton(dir_frame, text="⟳ Choices", width=60, fg_color="#0288D1", hover_color="#01579B", command=lambda: self._trigger_redo_choices(target_idx))
                            btn_rc.pack(side="left", padx=5)
                            Tooltip(btn_rc, "Keep text, but get new choices.")
                            
                            btn_exp = ctk.CTkButton(dir_frame, text="✨ Expand", width=60, fg_color="#00ACC1", hover_color="#00838F", command=lambda: self._trigger_expansion(target_idx))
                            btn_exp.pack(side="left", padx=5)
                            Tooltip(btn_exp, "Add sensory depth to this scene.")

                            btn_pol = ctk.CTkButton(dir_frame, text="✨ Polish", width=60, fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: self._trigger_polish(target_idx))
                            btn_pol.pack(side="left", padx=5)
                            Tooltip(btn_pol, "Fix grammar/style.")
                        
                        if show_fix:
                            btn_fix = ctk.CTkButton(dir_frame, text="🔧 Fix...", width=60, fg_color="#009688", hover_color="#00796B", command=lambda: self._trigger_fix(target_idx))
                            btn_fix.pack(side="left", padx=5)
                            Tooltip(btn_fix, "Instruct AI to change a specific detail.")
                            
                        # Pack UNDO on the far right, perfectly isolated
                        if cheats_allowed and len(history) > 1:
                            btn_undo = ctk.CTkButton(dir_frame, text="↶ Undo Last Turn", width=120, fg_color="#FF9800", hover_color="#F57C00", command=self.on_undo)
                            btn_undo.pack(side="right", padx=(5, 0))
                            Tooltip(btn_undo, "Revert the game state to the previous turn.")

                    for c in turn.get("choices", []):
                        if not cheats_allowed and "Cheat Death" in c: continue
                        color = "#1F6AA5"; hover = "#144870"
                        if "Restart Game" in c: color = "#D32F2F"; hover = "#9A0007"
                        elif "Quit" in c: color = "#4A4A4A"; hover = "#333333"
                        elif "Export" in c: color = "#388E3C"; hover = "#1B5E20"
                        elif "Undo (Cheat Death" in c: color = "#D32F2F"; hover = "#9A0007"
                        elif "Start Chapter:" in c or "Conclude the Story" in c: color = "#7B1FA2"; hover = "#4A148C"
                        
                        btn = ctk.CTkButton(refs["btn_frame"], text=c, fg_color=color, hover_color=hover, anchor="w", command=lambda action=c: self._execute_action(action))
                        btn.pack(fill="x", pady=2, padx=5)

        current_width = self.timeline._parent_canvas.winfo_width()
        if current_width > 100:
            self._apply_wrapping(current_width)
            self._last_width = current_width
            
        if auto_scroll:
            self._force_scroll_bottom() 
            for ms in [50, 150, 300, 500, 850]:
                self.after(ms, self._force_scroll_bottom)

    # ---------------------------------------------------------
    # UI CARD EDITOR (The "Magic Pencil")
    # ---------------------------------------------------------

    def _open_edit_dialog(self, turn_idx):
        """Opens the Full Narrative IDE for a specific turn."""
        if turn_idx < 0 or turn_idx >= len(self.engine.history): return
        turn = self.engine.history[turn_idx]
        
        # Re-poll config to ensure the editor uses the correct font
        from config import ENGINE_CONFIG
        f_family = ENGINE_CONFIG.get("prose_font_family", "Georgia")
        f_size = ENGINE_CONFIG.get("prose_font_size", 15)
        self.prose_font = (f_family, int(f_size))
        self.bridge_font = (f_family, max(10, int(f_size)-1), "italic")
        
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Narrative Editor: Turn {turn.get('turn', '?')}")
        dialog.geometry("900x850")
        dialog.attributes("-topmost", True)
        dialog.grab_set() 
        
        from ui.tooltip import Tooltip

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        # --- METADATA SECTION ---
        meta_grid = ctk.CTkFrame(scroll, fg_color="transparent")
        meta_grid.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(meta_grid, text="Location:", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w")
        loc_var = ctk.StringVar(value=turn.get("location", ""))
        ctk.CTkEntry(meta_grid, textvariable=loc_var, width=350, font=("Arial", 13)).grid(row=1, column=0, padx=(0, 20), sticky="w")
        
        ctk.CTkLabel(meta_grid, text="POV:", font=("Arial", 12, "bold")).grid(row=0, column=1, sticky="w")
        pov_var = ctk.StringVar(value=turn.get("pov_character", ""))
        ctk.CTkEntry(meta_grid, textvariable=pov_var, width=250, font=("Arial", 13)).grid(row=1, column=1, sticky="w")

        # --- NARRATIVE BRIDGE (Transition INTO this turn) ---
        if turn_idx > 0:
            br_hdr = ctk.CTkFrame(scroll, fg_color="transparent")
            br_hdr.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(br_hdr, text="Narrative Bridge (Transition from previous turn):", font=("Arial", 12, "bold")).pack(side="left")
            
            # Clear Textbox Button
            btn_clear_br = ctk.CTkButton(br_hdr, text="X Clear", width=60, fg_color="#B71C1C", hover_color="#7F0000")
            btn_clear_br.pack(side="right", padx=5)
            Tooltip(btn_clear_br, "Wipe the textbox below.")

            btn_gen_br = ctk.CTkButton(br_hdr, text="✨ Generate", width=80, fg_color="#00ACC1", hover_color="#00838F")
            btn_gen_br.pack(side="right", padx=5)
            
            bridge_box = ctk.CTkTextbox(scroll, height=100, wrap="word", font=self.prose_font)
            bridge_box.insert("1.0", turn.get("narrative_bridge", "").replace("\\n", "\n"))
            bridge_box.pack(fill="x", pady=(0, 20))
            
            btn_clear_br.configure(command=lambda: bridge_box.delete("1.0", "end"))
            
            # Async Generation Logic
            def generate_bridge_async():
                btn_gen_br.configure(state="disabled", text="Generating...")
                def worker():
                    b_text = self.engine.request_bridge_generation(turn_idx)
                    def update_ui():
                        if b_text and b_text not in ["[OK]", "[FAILED]"]:
                            bridge_box.delete("1.0", "end")
                            bridge_box.insert("1.0", b_text)
                        elif b_text == "[OK]":
                            from tkinter import messagebox
                            messagebox.showinfo("Bridge", "The AI determined the transition is already seamless [OK].")
                        else:
                            from tkinter import messagebox
                            messagebox.showerror("Error", "Failed to generate bridge.")
                        btn_gen_br.configure(state="normal", text="✨ Generate")
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            btn_gen_br.configure(command=generate_bridge_async)
            Tooltip(btn_gen_br, "Ask AI to generate a bridge connecting the previous action to this prose.")
        else:
            bridge_box = None

        # --- PROSE SECTION ---
        header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(header_frame, text="Story Prose:", font=("Arial", 16, "bold")).pack(side="left")
        
        btn_p = ctk.CTkButton(header_frame, text="✨ Polish", width=80, fg_color="#9C27B0", hover_color="#7B1FA2", 
                              command=lambda: [dialog.destroy(), self._trigger_polish(turn_idx)])
        btn_p.pack(side="right", padx=5)
        Tooltip(btn_p, "AI Copy-Edit: Fix grammar/flow in this specific card.")
        
        btn_e = ctk.CTkButton(header_frame, text="✨ Expand", width=80, fg_color="#00ACC1", hover_color="#00838F", 
                              command=lambda: [dialog.destroy(), self._trigger_expansion(turn_idx)])
        btn_e.pack(side="right", padx=5)
        Tooltip(btn_e, "AI Expansion: Add sensory depth to this specific card.")

        story_box = ctk.CTkTextbox(scroll, height=250, wrap="word", font=self.prose_font)
        story_box.insert("1.0", turn.get("story_text", "").replace("\\n", "\n"))
        story_box.pack(fill="x", pady=(0, 20))

        # --- CHOICES SECTION ---
        ctk.CTkLabel(scroll, text="Action Choices:", font=("Arial", 16, "bold")).pack(anchor="w", pady=(10, 5))
        
        self.choice_rows = []
        choices_container = ctk.CTkFrame(scroll, fg_color="transparent")
        choices_container.pack(fill="x")

        def render_choice_list():
            for w in choices_container.winfo_children(): w.destroy()
            self.choice_rows.clear()
            
            curr_choices = turn.get("choices", [])
            for i, c_text in enumerate(curr_choices):
                row = ctk.CTkFrame(choices_container, fg_color="transparent")
                row.pack(fill="x", pady=2)
                
                var = ctk.StringVar(value=c_text)
                ctk.CTkLabel(row, text=f"{i+1}.").pack(side="left", padx=5)
                entry = ctk.CTkEntry(row, textvariable=var, font=("Arial", 13))
                entry.pack(side="left", fill="x", expand=True)
                
                if not self.engine.is_campaign:
                    btn_del = ctk.CTkButton(row, text="X", width=25, fg_color="#B71C1C", hover_color="#7F0000", 
                                            command=lambda idx=i: [turn["choices"].pop(idx), render_choice_list()])
                    btn_del.pack(side="left", padx=2)
                    Tooltip(btn_del, "Remove this choice.")
                
                self.choice_rows.append(var)

            if not self.engine.is_campaign:
                btn_row = ctk.CTkFrame(choices_container, fg_color="transparent")
                btn_row.pack(fill="x", pady=(10, 0))
                
                btn_add = ctk.CTkButton(btn_row, text="+ Add Choice", width=100, fg_color="#4A4A4A", hover_color="#333333",
                                        command=lambda: [turn["choices"].append("New action..."), render_choice_list()])
                btn_add.pack(side="left", padx=(0, 10))
                
                btn_reroll_ch = ctk.CTkButton(btn_row, text="⟳ Reroll Choices", width=120, fg_color="#0288D1", hover_color="#01579B",
                                        command=lambda: [dialog.destroy(), self._trigger_redo_choices(turn_idx)])
                btn_reroll_ch.pack(side="left")
                Tooltip(btn_reroll_ch, "Ask AI to generate a fresh set of choices for this exact card.")

        render_choice_list()

        # --- HISTORICAL PLAYER ACTION (Leaves this turn) ---
        pc_var = None
        if turn.get("player_choice") is not None:
            ctk.CTkLabel(scroll, text="Player Action Taken:", font=("Arial", 14, "bold")).pack(anchor="w", pady=(20, 0))
            pc_var = ctk.StringVar(value=turn.get("player_choice", ""))
            ctk.CTkEntry(scroll, textvariable=pc_var, font=("Arial", 14), text_color="#4CAF50").pack(fill="x", pady=(0, 15))

        # --- SAVE ACTIONS ---
        def on_save():
            self.engine.history[turn_idx]["location"] = loc_var.get().strip()
            self.engine.history[turn_idx]["pov_character"] = pov_var.get().strip()
            self.engine.history[turn_idx]["story_text"] = story_box.get("1.0", "end").strip().replace("\n", "\\n")
            if "choices" in turn: 
                self.engine.history[turn_idx]["choices"] = [v.get().strip() for v in self.choice_rows if v.get().strip()]
            
            if pc_var: 
                self.engine.history[turn_idx]["player_choice"] = pc_var.get().strip()
                
            # Bridge handling
            if bridge_box is not None:
                b_text = bridge_box.get("1.0", "end").strip().replace("\n", "\\n")
                if b_text:
                    self.engine.history[turn_idx]["narrative_bridge"] = b_text
                elif "narrative_bridge" in self.engine.history[turn_idx]:
                    del self.engine.history[turn_idx]["narrative_bridge"]
            
            self.engine.save_state()
            self._render_visible_cards()
            dialog.destroy()

        def on_seed_save():
            seed_file = self.engine.adv_dir / "start_turn.json"
            import json
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(turn, f, indent=4)
            from tkinter import messagebox
            messagebox.showinfo("Seed Created", "This turn has been saved as the official Story Seed!\nAny new game will begin exactly here.")

        # --- FOOTER BUTTON ROW ---
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", pady=20, padx=20)
        
        ctk.CTkButton(btn_row, text="Commit All Changes", font=("Arial", 14, "bold"), height=40,
                      fg_color="#2E7D32", hover_color="#1B5E20", command=on_save).pack(side="right", padx=10)
        
        if turn.get("turn", 0) <= 1:
            btn_s = ctk.CTkButton(btn_row, text="💾 Set as Story Seed", font=("Arial", 12, "bold"), height=40,
                                  fg_color="#1F6AA5", hover_color="#144870", command=on_seed_save)
            btn_s.pack(side="left", padx=10)
            Tooltip(btn_s, "Lock this prose and choices as the permanent starting point for new games.")

            
    def _open_edit_dialog_(self, turn_idx):
        """(Legacy) Opens a modal dialog allowing the user to directly edit JSON history data."""
        if turn_idx < 0 or turn_idx >= len(self.engine.history): return
        turn = self.engine.history[turn_idx]
        
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Editing Turn {turn.get('turn', '?')}")
        dialog.geometry("800x800")
        dialog.attributes("-topmost", True)
        dialog.grab_set() 
        
        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(scroll, text="Location:", font=("Arial", 14, "bold")).pack(anchor="w")
        loc_var = ctk.StringVar(value=turn.get("location", ""))
        ctk.CTkEntry(scroll, textvariable=loc_var, font=("Arial", 14)).pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(scroll, text="POV Character:", font=("Arial", 14, "bold")).pack(anchor="w")
        pov_var = ctk.StringVar(value=turn.get("pov_character", ""))
        ctk.CTkEntry(scroll, textvariable=pov_var, font=("Arial", 14)).pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(scroll, text="Story Text (Use exact line breaks):", font=("Arial", 14, "bold")).pack(anchor="w")
        story_box = ctk.CTkTextbox(scroll, height=250, wrap="word", font=self.prose_font)
        story_box.insert("1.0", turn.get("story_text", "").replace("\\n", "\n"))
        story_box.pack(fill="x", pady=(0, 15))
        
        choice_vars = []
        if "choices" in turn:
            ctk.CTkLabel(scroll, text="Available Choices:", font=("Arial", 14, "bold")).pack(anchor="w")
            for i, c in enumerate(turn["choices"], 1):
                c_frame = ctk.CTkFrame(scroll, fg_color="transparent")
                c_frame.pack(fill="x", pady=2)
                ctk.CTkLabel(c_frame, text=f"{i}.").pack(side="left", padx=(0, 5))
                var = ctk.StringVar(value=c)
                ctk.CTkEntry(c_frame, textvariable=var, font=("Arial", 14)).pack(side="left", fill="x", expand=True)
                choice_vars.append(var)
                
        pc_var = None
        if turn.get("player_choice") is not None:
            ctk.CTkLabel(scroll, text="Player Action Taken:", font=("Arial", 14, "bold")).pack(anchor="w", pady=(15, 0))
            pc_var = ctk.StringVar(value=turn.get("player_choice", ""))
            ctk.CTkEntry(scroll, textvariable=pc_var, font=("Arial", 14), text_color="#4CAF50").pack(fill="x", pady=(0, 15))
            
            # Allow editing the Narrative Bridge
            ctk.CTkLabel(scroll, text="Narrative Bridge (Prose transition):", font=("Arial", 14, "bold")).pack(anchor="w", pady=(15, 0))
            bridge_var = ctk.StringVar(value=turn.get("narrative_bridge", ""))
            ctk.CTkEntry(scroll, textvariable=bridge_var, font=self.bridge_font, text_color="#82B1FF").pack(fill="x", pady=(0, 15))

        def on_save():
            # Update the exact dictionary using the guaranteed absolute index
            self.engine.history[turn_idx]["location"] = loc_var.get().strip()
            self.engine.history[turn_idx]["pov_character"] = pov_var.get().strip()
            self.engine.history[turn_idx]["story_text"] = story_box.get("1.0", "end").strip().replace("\n", "\\n")
            
            if "choices" in turn: 
                self.engine.history[turn_idx]["choices"] = [v.get().strip() for v in choice_vars if v.get().strip()]
            
            if pc_var: 
                self.engine.history[turn_idx]["player_choice"] = pc_var.get().strip()
                # Bridge variable only exists if player_choice exists
                if bridge_var.get().strip():
                    self.engine.history[turn_idx]["narrative_bridge"] = bridge_var.get().strip()
                elif "narrative_bridge" in self.engine.history[turn_idx]:
                    # If they cleared the box, delete the key so it doesn't show an empty string
                    del self.engine.history[turn_idx]["narrative_bridge"]
            
            self.engine.save_state()
            self._render_visible_cards() # Visually refresh the timeline
            dialog.destroy()
            
        def on_seed_save():
            """Exports this exact turn as the start_turn.json seed."""
            seed_file = self.engine.adv_dir / "start_turn.json"
            import json
            with open(seed_file, "w", encoding="utf-8") as f:
                json.dump(turn, f, indent=4)
            messagebox.showinfo("Seed Created", "This turn has been saved as the official Story Seed!\nAny new game will begin exactly here.")

        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(pady=20)
        
        ctk.CTkButton(btn_row, text="Save Changes", font=("Arial", 14, "bold"), fg_color="#2E7D32", hover_color="#1B5E20", command=on_save).pack(side="left", padx=10)
        
        # Only show the Seed generator option for Turn 0 or Turn 1
        if turn.get("turn", 0) <= 1:
            ctk.CTkButton(btn_row, text="💾 Set as Story Seed", font=("Arial", 12, "bold"), fg_color="#1F6AA5", hover_color="#144870", command=on_seed_save).pack(side="left", padx=10)

    # ---------------------------------------------------------
    # NON-DESTRUCTIVE EDITING (DIFF UI)
    # ---------------------------------------------------------

    def _show_draft_diff(self, draft_turn, action_type, instruction=None):
        """
        Displays a side-by-side modal comparing the original text with the AI's new draft.
        Uses Python's difflib to highlight inserted/deleted words like a Git commit.
        The player can Accept, Reroll, or Cancel the proposed draft.
        """
        if not draft_turn:
            self._unlock_ui("Ready.")
            messagebox.showerror("Error", "The engine failed to generate a draft. Check the Developer Console.")
            self.engine.cancel_draft()
            self.refresh_timeline()
            return
            
        dialog = ctk.CTkToplevel(self)
        title_str = f"Review Draft ({action_type.capitalize()})"
        if instruction: title_str += f": '{instruction}'"
        dialog.title(title_str)
        dialog.geometry("1000x700")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        # --- EXTRACT AND COMPARE TEXT ---
        orig_text = self.engine.backup_turn.get("story_text", "").replace("\\n", "\n").strip()
        new_text = draft_turn.get("story_text", "").replace("\\n", "\n").strip()
        is_identical = (orig_text == new_text)

        # --- THE "IN YOUR FACE" IDENTICAL ALERT ---
        if is_identical:
            warn_frame = ctk.CTkFrame(dialog, fg_color="#FBC02D", corner_radius=8)
            warn_frame.pack(fill="x", padx=20, pady=(20, 0))
            ctk.CTkLabel(
                warn_frame, 
                text="⚠️ NO CHANGES DETECTED: The AI returned the exact same text! Hit 'Reroll' to try again. ⚠️", 
                font=("Arial", 16, "bold"), text_color="black"
            ).pack(pady=10)

        # Split screen container
        grid = ctk.CTkFrame(dialog, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20, pady=20)
        grid.columnconfigure(0, weight=1, uniform="group1")
        grid.columnconfigure(1, weight=1, uniform="group1")
        grid.rowconfigure(1, weight=1)

        # Headers
        ctk.CTkLabel(grid, text="Original Text", font=("Arial", 16, "bold"), text_color="#F44336").grid(row=0, column=0, pady=(0, 10))
        
        new_hdr_color = "#FBC02D" if is_identical else "#4CAF50"
        new_hdr_text = "Proposed Revision (IDENTICAL)" if is_identical else "Proposed Revision"
        ctk.CTkLabel(grid, text=new_hdr_text, font=("Arial", 16, "bold"), text_color=new_hdr_color).grid(row=0, column=1, pady=(0, 10))

        # Text Boxes
        orig_box = ctk.CTkTextbox(grid, wrap="word", font=self.prose_font)
        orig_box.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        
        new_box = ctk.CTkTextbox(grid, wrap="word", font=self.prose_font)
        new_box.grid(row=1, column=1, sticky="nsew", padx=(10, 0))

        # --- VISUAL DIFF HIGHLIGHTING ---
        import difflib
        import re

        # Configure color tags for highlighting
        orig_box.tag_config("delete", background="#5C1B1B") # Dark Red
        orig_box.tag_config("replace", background="#7A4B00") # Dark Orange
        
        new_box.tag_config("insert", background="#1B4B1B") # Dark Green
        new_box.tag_config("replace", background="#7A4B00") # Dark Orange

        # Split text while preserving whitespace so the formatting remains perfect
        orig_tokens = re.split(r'(\s+)', orig_text)
        new_tokens = re.split(r'(\s+)', new_text)

        # Compare the tokens using difflib
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

        # Disable editing after inserting text
        orig_box.configure(state="disabled")
        new_box.configure(state="disabled")

        # Button Bar
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        def on_accept():
            self.engine.commit_draft(draft_turn)
            dialog.destroy()
            self.refresh_timeline()

        def on_cancel():
            self.engine.cancel_draft()
            dialog.destroy()
            self.refresh_timeline()

        def on_retry():
            # Trash this draft, lock the UI, and ask the LLM for a new one using the SAFE endpoint
            dialog.destroy()
            
            # Special handling for retry loops
            if action_type == "expansion":
                self._trigger_expansion()
            else:
                self._lock_ui(f"Rerolling {action_type} draft...")
                def worker():
                    new_draft = self.engine.request_reroll_draft()
                    self.after(0, lambda: self._show_draft_diff(new_draft, action_type, instruction))
                threading.Thread(target=worker, daemon=True).start()
                

        ctk.CTkButton(btn_frame, text="Cancel (Discard)", fg_color="#D32F2F", hover_color="#9A0007", width=120, command=on_cancel).pack(side="left")
        
        # Center the Retry button
        center_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
        center_frame.pack(side="left", expand=True)
        ctk.CTkButton(center_frame, text="⟳ Reroll Draft", fg_color="#FF9800", hover_color="#F57C00", width=120, command=on_retry).pack()
        
        ctk.CTkButton(btn_frame, text="Accept Revision", fg_color="#388E3C", hover_color="#1B5E20", width=120, command=on_accept).pack(side="right") 
        
    # ---------------------------------------------------------
    # ACTION SUBMISSION & ASYNC THREADING
    # ---------------------------------------------------------

    def on_submit(self):
        """Gathers text from the input bar and passes it to the engine."""
        raw_text = self.text_input.get().strip()
        if not raw_text: return
        
        # Force Standard Action if Campaign mode hides the dropdown
        cmd_type = self.cmd_dropdown.get() if not self.engine.is_campaign else "Standard Action"
        self.text_input.delete(0, 'end') 
        
        if cmd_type == "Expand Notes": final_action = f"EXPAND: {raw_text}"
        elif cmd_type == "Force Setting": final_action = f"setting: {raw_text}"
        elif cmd_type == "Force Time": final_action = f"time: {raw_text}"
        elif cmd_type == "Force POV": final_action = f"pov: {raw_text}"
        else: final_action = raw_text

        self._execute_action(final_action)
        
    def on_undo(self):
        """Destructively pops the last action from history."""
        self._lock_ui("Undoing last choice...")
        def worker():
            self.engine.undo()
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_redo(self):
        """Destructively rerolls the entire current turn."""
        self._lock_ui("Generating alternative version...")
        def worker():
            # Directly call the destructive redo endpoint and refresh the screen
            self.engine.redo_turn()
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_redo_choices(self, turn_idx=None):
        self._lock_ui("Generating new choices...")
        def worker():
            self.engine.redo_choices(turn_idx)
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_polish(self, turn_idx=None):
        self._lock_ui("Generating polished prose...")
        def worker():
            draft = self.engine.request_polish(turn_idx)
            self.after(0, lambda: self._show_draft_diff(draft, "polish"))
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_expansion(self, turn_idx=None):
        self._lock_ui("Expanding turn prose...")
        def worker():
            draft = self.engine.request_expansion(turn_idx)
            self.after(0, lambda: self._show_draft_diff(draft, "expansion"))
        threading.Thread(target=worker, daemon=True).start()
        
    def _trigger_fix(self):
        dialog = ctk.CTkInputDialog(text="Enter edit instruction (e.g., 'Make it raining'):", title="Director Fix")
        instruction = dialog.get_input()
        if not instruction: return
        
        self._lock_ui(f"Applying fix: {instruction[:15]}...")
        def worker():
            draft = self.engine.request_fix(instruction)
            self.after(0, lambda: self._show_draft_diff(draft, "fix", instruction))
        threading.Thread(target=worker, daemon=True).start()
        
    def _execute_action(self, action_string):
        """Sends the user's action to the engine on a background thread to prevent UI freezing."""
        self._lock_ui(f"Submitting: '{action_string[:20]}...'")
        def worker():
            self.engine.submit_action(action_string)
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()

    def _delete_bridge_timeline(self, turn_idx):
        """Instantly deletes a bridge directly from the timeline card."""
        if messagebox.askyesno("Delete Bridge", "Are you sure you want to delete this narrative bridge?"):
            if "narrative_bridge" in self.engine.history[turn_idx]:
                del self.engine.history[turn_idx]["narrative_bridge"]
                self.engine.save_state()
                self._render_visible_cards()

    def _generate_bridge_timeline(self, turn_idx):
        """Triggers the LLM to rewrite the bridge directly from the timeline card."""
        self._lock_ui("Regenerating narrative bridge...")
        def worker():
            b_text = self.engine.request_bridge_generation(turn_idx)
            def update_ui():
                if b_text and b_text not in ["[OK]", "[FAILED]"]:
                    self.engine.history[turn_idx]["narrative_bridge"] = b_text
                    self.engine.save_state()
                elif b_text == "[OK]":
                    messagebox.showinfo("Bridge", "The AI determined the transition is already seamless [OK].")
                else:
                    messagebox.showerror("Error", "Failed to generate bridge.")
                    
                self._unlock_ui("Ready.")
                self._render_visible_cards()
            self.after(0, update_ui)
            
        import threading
        threading.Thread(target=worker, daemon=True).start()
        
    def _async_init(self):
        """Runs the Turn 1 / Prologue startup logic in the background."""
        try: self.engine.initialize_game()
        except Exception as e: self.after(0, lambda: messagebox.showerror("Engine Error", str(e)))
        finally: self.after(0, self.refresh_timeline)

    def _lock_ui(self, status_msg):
        """Disables all input controls while the AI is generating."""
        self.status_var.set(status_msg)
        self.btn_submit.configure(state="disabled")
        self.text_input.configure(state="disabled")
        self.cmd_dropdown.configure(state="disabled")
        self.history_slider.configure(state="disabled")
        
        for refs in self.recycled_cards:
            if "btn_bridge" in refs: refs["btn_bridge"].configure(state="disabled")
            if "br_btn_gen" in refs: refs["br_btn_gen"].configure(state="disabled")
            
            for w in refs["btn_frame"].winfo_children():
                if isinstance(w, ctk.CTkButton): 
                    w.configure(state="disabled")
                elif isinstance(w, ctk.CTkFrame): # Look inside dir_frame
                    for sub_w in w.winfo_children():
                        if isinstance(sub_w, ctk.CTkButton): sub_w.configure(state="disabled")

    def _unlock_ui(self, status_msg):
        """Restores interactivity after an AI generation completes."""
        self.status_var.set(status_msg)
        self.btn_submit.configure(state="normal")
        self.text_input.configure(state="normal")
        self.cmd_dropdown.configure(state="normal")
        if len(self.engine.history) > self.MAX_CARDS:
            self.history_slider.configure(state="normal")
            
        for refs in self.recycled_cards:
            if "btn_bridge" in refs: refs["btn_bridge"].configure(state="normal")
            if "br_btn_gen" in refs: refs["br_btn_gen"].configure(state="normal")

        # --- AUTOPILOT HOOK ---
        if self.engine.is_test_mode:
            # Check if there is an active turn with choices to click
            if self.engine.history:
                last_turn = self.engine.history[-1]
                is_over = str(last_turn.get("is_game_over", False)).lower() == "true"
                
                if not is_over and last_turn.get("choices"):
                    # Select Choice #1 (The Golden Path)
                    auto_choice = last_turn["choices"][0]
                    self.status_var.set(f"Autopilot: Selecting '{auto_choice[:20]}...' in 2s")
                    
                    # --- SAFETY CHECK LAMBDA ---
                    # We check is_test_mode inside the timer. If the user clicked 
                    # "Stop Test" during the 2s wait, this will gracefully abort.
                    def auto_step():
                        if self.engine.is_test_mode:
                            self._execute_action(auto_choice)
                        else:
                            self.status_var.set("Autopilot aborted.")

                    self.after(2000, auto_step)
                elif is_over:
                    # Game ended, stop the test
                    self.workspace._toggle_test()