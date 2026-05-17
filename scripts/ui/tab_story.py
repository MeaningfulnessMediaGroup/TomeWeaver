import threading
import customtkinter as ctk
from tkinter import messagebox
from ui.tooltip import Tooltip

class StoryTab(ctk.CTkFrame):
    def __init__(self, parent, engine, workspace):
        super().__init__(parent, fg_color="transparent")
        self.engine = engine
        self.workspace = workspace

        # --- FONT & STYLE SETTINGS ---
        from config import ENGINE_CONFIG
        f_size = ENGINE_CONFIG.get("prose_font_size", 15)
        self.prose_font = ("Georgia", int(f_size))
        self.header_font = ("Arial", 12)
        self.action_font = ("Arial", 14, "bold")
        self.bridge_font = ("Georgia", 14, "italic")
        
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
        
        self.btn_undo = ctk.CTkButton(input_frame, text="↶ Undo", command=self.on_undo, width=60, fg_color="#FF9800", hover_color="#F57C00")
        self.btn_undo.pack(side="right", padx=5, pady=15)

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
        safe_width = width - 120 
        scale = self._get_widget_scaling()
        adjusted_wrap = int(safe_width / scale)
        for refs in self.recycled_cards:
            refs["prose"].configure(wraplength=adjusted_wrap)
            refs["hdr"].configure(wraplength=max(50, adjusted_wrap - 80))
            refs["choice"].configure(wraplength=adjusted_wrap)
            refs["bridge"].configure(wraplength=adjusted_wrap)

    def _wrap_heartbeat(self):
        current_width = self.timeline._parent_canvas.winfo_width()
        if current_width > 100 and current_width != self._last_width:
            self._last_width = current_width
            self._apply_wrapping(current_width)
        self.after(200, self._wrap_heartbeat)

    def _force_scroll_bottom(self):
        """Aggressively snaps the canvas to the absolute bottom, ensuring choices are visible."""
        self.timeline.update_idletasks()
        self.timeline._parent_canvas.yview_moveto(1.0)

    # ---------------------------------------------------------
    # WIDGET VIRTUALIZATION (The 3-Card Engine)
    # ---------------------------------------------------------

    def _initialize_recycled_cards(self):
        """Creates exactly 3 empty Card templates in memory. These will NEVER be destroyed."""
        for _ in range(self.MAX_CARDS):
            card = ctk.CTkFrame(
                self.timeline, corner_radius=10, 
                fg_color=("#EBEBEB", "#22252A"), border_width=1, border_color=("#D3D3D3", "#343638")
            )
            
            # Header Row
            hdr_frame = ctk.CTkFrame(card, fg_color="transparent")
            hdr_frame.pack(fill="x", padx=15, pady=(10, 5))
            btn_edit = ctk.CTkButton(hdr_frame, text="✎ Edit", width=50, height=24, fg_color="#4A4A4A", hover_color="#333333")
            btn_edit.pack(side="right")
            hdr_lbl = ctk.CTkLabel(hdr_frame, text="", text_color="gray", font=self.header_font, justify="left", anchor="w")
            hdr_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            # Prose
            prose_lbl = ctk.CTkLabel(card, text="", font=self.prose_font, justify="left", anchor="w")
            prose_lbl.pack(fill="x", padx=15, pady=5)
            
            # Footer (Action / Bridge)
            c_lbl = ctk.CTkLabel(card, text="", font=self.action_font, text_color="#4CAF50", justify="left", anchor="w")
            
            br_frame = ctk.CTkFrame(self.timeline, fg_color="transparent")
            br_lbl = ctk.CTkLabel(br_frame, text="", font=self.bridge_font, text_color="#82B1FF", justify="left", anchor="w")
            br_lbl.pack(fill="x")
            
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            
            self.recycled_cards.append({
                "card": card, "hdr": hdr_lbl, "prose": prose_lbl, "btn_edit": btn_edit,
                "choice": c_lbl, "br_frame": br_frame, "bridge": br_lbl, "btn_frame": btn_frame
            })

    def refresh_timeline(self):
        """Clears the screen, pulls the history from the engine, and renders the cards."""
        
        # Toggle Global Undo Button Visibility dynamically
        self.btn_submit.pack_forget()
        self.btn_undo.pack_forget()
        self.btn_submit.pack(side="right", padx=10, pady=15)
        if self.engine.setup_data.get("allow_cheats", False):
            self.btn_undo.pack(side="right", padx=5, pady=15)

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
        new_idx = int(value)
        if new_idx != self.current_top_idx:
            self.current_top_idx = new_idx
            self._render_visible_cards(auto_scroll=False)
            # When manually browsing history, always snap to the top of the slice
            self.timeline._parent_canvas.yview_moveto(0.0)

    def _render_visible_cards(self, auto_scroll=False):
        """Injects text from the current history slice into the 3 static recycled widgets."""
        history = self.engine.history
        
        for i in range(self.MAX_CARDS):
            target_idx = self.current_top_idx + i
            refs = self.recycled_cards[i]
            
            if target_idx < len(history):
                turn = history[target_idx]
                refs["card"].pack(fill="x", padx=20, pady=10) 
                
                loc = turn.get("location", "Unknown")
                pov = turn.get("pov_character", "Unknown")
                refs["hdr"].configure(text=f"Turn {turn.get('turn', '?')} • [{loc}] • POV: {pov}")
                
                # FIX: Pad with explicit newlines to prevent CTkLabel from horizontally clipping the bottom text
                prose_text = turn.get("story_text", "").replace("\\n", "\n")
                refs["prose"].configure(text=prose_text)
                
                cheats_allowed = self.engine.setup_data.get("allow_cheats", False)
                if cheats_allowed:
                    refs["btn_edit"].pack(side="right")
                    refs["btn_edit"].configure(command=lambda idx=target_idx: self._open_edit_dialog(idx))
                else:
                    refs["btn_edit"].pack_forget()
                
                refs["choice"].pack_forget()
                refs["br_frame"].pack_forget()
                for w in refs["btn_frame"].winfo_children(): w.destroy()
                refs["btn_frame"].pack_forget()
                
                choice = turn.get("player_choice")
                if choice is not None:
                    refs["choice"].configure(text=f"❯ {choice}")
                    refs["choice"].pack(fill="x", padx=15, pady=(5, 15))
                    
                    bridge = turn.get("narrative_bridge")
                    if bridge and bridge not in ["[OK]", "[FAILED]", ""]:
                        refs["bridge"].configure(text=bridge)
                        refs["br_frame"].pack(fill="x", padx=40, pady=(0, 5))
                else:
                    refs["btn_frame"].pack(fill="x", padx=10, pady=(10, 15))
                    
                    from ui.tooltip import Tooltip

                    # Inject Director Controls (AI Quality of Life) - ALWAYS VISIBLE
                    dir_frame = ctk.CTkFrame(refs["btn_frame"], fg_color="transparent")
                    dir_frame.pack(fill="x", pady=(0, 10), padx=5)
                    
                    btn_redo = ctk.CTkButton(dir_frame, text="⟳ Redo Turn", width=60, fg_color="#F57C00", hover_color="#E65100", command=self._trigger_redo)
                    btn_redo.pack(side="left", padx=(0, 5))
                    Tooltip(btn_redo, "Destructively erases this turn and asks the AI to write a completely new one.")
                    
                    btn_choices = ctk.CTkButton(dir_frame, text="⟳ Choices", width=60, fg_color="#0288D1", hover_color="#01579B", command=self._trigger_redo_choices)
                    btn_choices.pack(side="left", padx=5)
                    Tooltip(btn_choices, "Keeps the story text but asks the AI to generate a new set of choices.")
                    
                    btn_polish = ctk.CTkButton(dir_frame, text="✨ Polish", width=60, fg_color="#9C27B0", hover_color="#7B1FA2", command=self._trigger_polish)
                    btn_polish.pack(side="left", padx=5)
                    Tooltip(btn_polish, "Opens the Editor: Asks the AI to fix grammar and enhance the prose without altering the plot.")
                    
                    # Inject Cheats (Reality Alteration) - ONLY VISIBLE IF ALLOWED
                    if cheats_allowed:
                        btn_fix = ctk.CTkButton(dir_frame, text="🔧 Fix...", width=60, fg_color="#009688", hover_color="#00796B", command=self._trigger_fix)
                        btn_fix.pack(side="left", padx=5)
                        Tooltip(btn_fix, "Opens the Editor: Instructs the AI to alter a specific detail in the text.")
                    
                    # Inject standard choices
                    for c in turn.get("choices", []):
                        # Hardcore Mode check: Hide the "Cheat Death" fallback choice
                        if not cheats_allowed and "Cheat Death" in c:
                            continue 
                            
                        color = "#1F6AA5"; hover = "#144870"
                        if "Cheat Death" in c: color = "#D32F2F"; hover = "#9A0007"
                        elif "Start Chapter:" in c or "Conclude the Story" in c: color = "#7B1FA2"; hover = "#4A148C"
                        
                        btn = ctk.CTkButton(refs["btn_frame"], text=c, fg_color=color, hover_color=hover, anchor="w", command=lambda action=c: self._execute_action(action))
                        btn.pack(fill="x", pady=3, padx=5)
                        
            else:
                refs["card"].pack_forget()
                refs["br_frame"].pack_forget()

        # Instantly apply wrapping to new text before calculating scroll height
        current_width = self.timeline._parent_canvas.winfo_width()
        if current_width > 100:
            self._apply_wrapping(current_width)
            self._last_width = current_width
            
        if auto_scroll:
            # THE BARRAGE SCROLL: Tkinter takes unpredictable amounts of time to wrap massive text.
            # Firing this across 1 second guarantees it catches the final layout frame and pins it to the floor.
            for ms in [50, 150, 300, 500, 850]:
                self.after(ms, self._force_scroll_bottom)


    # ---------------------------------------------------------
    # UI CARD EDITOR (The "Magic Pencil")
    # ---------------------------------------------------------

    def _open_edit_dialog(self, turn_idx):
        """Opens a modal dialog allowing the user to directly edit JSON history data."""
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
        """Displays a modal comparing the original text with the AI's new draft."""
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

        # Compare the tokens
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
        self._lock_ui("Undoing last choice...")
        def worker():
            self.engine.undo()
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_redo(self):
        self._lock_ui("Generating alternative version...")
        def worker():
            # Directly call the destructive redo endpoint and refresh the screen
            self.engine.redo_turn()
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_redo_choices(self):
        self._lock_ui("Generating new choices...")
        def worker():
            self.engine.redo_choices()
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()
        
    def _trigger_polish(self):
        self._lock_ui("Generating polished prose...")
        def worker():
            draft = self.engine.request_polish()
            self.after(0, lambda: self._show_draft_diff(draft, "polish"))
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
        self._lock_ui(f"Submitting: '{action_string[:20]}...'")
        def worker():
            self.engine.submit_action(action_string)
            self.after(0, self.refresh_timeline)
        threading.Thread(target=worker, daemon=True).start()

    def _async_init(self):
        try: self.engine.initialize_game()
        except Exception as e: self.after(0, lambda: messagebox.showerror("Engine Error", str(e)))
        finally: self.after(0, self.refresh_timeline)

    def _lock_ui(self, status_msg):
        self.status_var.set(status_msg)
        self.btn_submit.configure(state="disabled")
        self.btn_undo.configure(state="disabled")
        self.text_input.configure(state="disabled")
        self.cmd_dropdown.configure(state="disabled")
        self.history_slider.configure(state="disabled")
        
        for refs in self.recycled_cards:
            for w in refs["btn_frame"].winfo_children():
                if isinstance(w, ctk.CTkButton): w.configure(state="disabled")

    def _unlock_ui(self, status_msg):
        self.status_var.set(status_msg)
        self.btn_submit.configure(state="normal")
        self.btn_undo.configure(state="normal")
        self.text_input.configure(state="normal")
        self.cmd_dropdown.configure(state="normal")
        if len(self.engine.history) > self.MAX_CARDS:
            self.history_slider.configure(state="normal")