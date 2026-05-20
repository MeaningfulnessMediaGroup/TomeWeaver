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

        
        
def get_darker_shade(hex_color, factor=0.4):
    """Generates a deep-background pill color from a bright hex code."""
    try:
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6: return "#1A1A1B" # Default dark grey
        rgb = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
        dark = [max(0, int(c * factor)) for c in rgb]
        return f"#{dark[0]:02x}{dark[1]:02x}{dark[2]:02x}"
    except Exception:
        return "#1A1A1B"


class CTkFlowFrame(ctk.CTkFrame):
    """A custom frame that uses native packing to simulate a flow layout."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.rows = []

    def flow(self, pill_widgets):
        """Packs a list of widgets into horizontal rows, wrapping as needed."""
        # 1. Clear existing rows
        for row in self.rows:
            row.destroy()
        self.rows.clear()
        
        if not pill_widgets: return
        
        self.update_idletasks()
        max_width = self.winfo_width()
        if max_width <= 10: max_width = 800
        
        # 2. Start the first row
        current_row = ctk.CTkFrame(self, fg_color="transparent")
        current_row.pack(fill="x", anchor="w", pady=(0, 5))
        self.rows.append(current_row)
        
        current_width = 0
        pad_x = 8
        
        # 3. Pack widgets into the row until full, then spawn a new row
        for pill in pill_widgets:
            pill.update_idletasks()
            w = pill.winfo_reqwidth()
            
            if current_width + w > max_width and current_width > 0:
                current_row = ctk.CTkFrame(self, fg_color="transparent")
                current_row.pack(fill="x", anchor="w", pady=(0, 5))
                self.rows.append(current_row)
                current_width = 0
                
            # Reparent the pill into the row and pack it natively
            pill.master = current_row
            pill.pack(side="left", padx=(0, pad_x))
            current_width += w + pad_x


        
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
        # 1. We remove the outer background frame to keep the UI flat
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        # 2. We align the frame's padding to match the left margin of the cards (10 + internal canvas padding)
        # and the right margin to account for the width of the Time Travel slider (40px + 5px gap + 10px scrollbar)
        input_frame.pack(fill="x", padx=(25, 75), pady=(0, 10))

        self.cmd_dropdown = ctk.CTkOptionMenu(
            input_frame, 
            values=["Standard Action", "Expand Notes", "Force Setting", "Force Time", "Force POV"],
            width=140
        )
        
        # Only show Director Overrides in Sandbox Mode
        if not self.engine.is_campaign:
            self.cmd_dropdown.pack(side="left", padx=(0, 10), pady=10)

        self.text_input = ctk.CTkEntry(input_frame, placeholder_text="Type a custom action or dialogue...", font=("Arial", 14))
        # 3. Text input packed tightly to the left
        self.text_input.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=10)
        self.text_input.bind("<Return>", lambda e: self.on_submit())

        self.btn_submit = ctk.CTkButton(input_frame, text="Submit", command=self.on_submit, width=100)
        # 4. Submit button packed tightly to the right
        self.btn_submit.pack(side="right", padx=0, pady=10)

        self.status_var = ctk.StringVar(value="Ready.")
        ctk.CTkLabel(self, textvariable=self.status_var, font=("Arial", 12, "italic"), text_color="gray").pack(side="bottom", anchor="w", padx=15, pady=(0, 5))

        # --- INITIALIZATION & VIRTUALIZATION ---
        self._initialize_recycled_cards()
        
        # --- STARTUP FRAME (Deferred Generation) ---
        self.startup_frame = ctk.CTkFrame(self.timeline, fg_color="transparent")
        self.btn_start_adv = ctk.CTkButton(
            self.startup_frame, 
            text="✨ Start Adventure (Generate Opening Scene) ✨", 
            font=("Arial", 18, "bold"), 
            height=60, 
            fg_color="#2E7D32", 
            hover_color="#1B5E20",
            command=self._trigger_startup
        )
        self.btn_start_adv.pack(expand=True)

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
            if "br_prose" in refs: refs["br_prose"].configure(wraplength=adjusted_wrap)
            if "br_hdr" in refs: refs["br_hdr"].configure(wraplength=max(50, adjusted_wrap - 80))

    def _wrap_heartbeat(self):
        """
        An infinitely repeating background loop. 
        Recalculates text wrap margins if the window resizes, and GUARANTEES 
        the inventory textbox height is always perfectly snapped to its content.
        """
        current_width = self.timeline._parent_canvas.winfo_width()
        if current_width > 100 and current_width != self._last_width:
            self._last_width = current_width
            self._apply_wrapping(current_width)
            
        # CRITICAL FIX: Always verify Inventory box height on every tick!
        # When a new turn is generated, Tkinter packs the widget before it knows its true width.
        # This caused the text to temporarily wrap to 5+ lines, trapping the height at a huge value.
        # Checking this continuously ensures it snaps back down instantly once fully drawn.
        for refs in self.recycled_cards:
            if "inv_box" in refs and refs["inv_box"].winfo_exists():
                tb = refs["inv_box"]._textbox
                lines = tb.count("1.0", "end", "displaylines")
                num_lines = lines[0] if lines else 1
                
                # 32px per line + 10px padding is the perfect tight fit
                calc_h = (num_lines * 32) + 10
                
                if refs["inv_box"].cget("height") != calc_h:
                    refs["inv_box"].configure(height=calc_h)

        self.after(200, self._wrap_heartbeat)

    def _maintain_scroll_position(self, target_y=None):
        """
        Forces the Canvas to update its bounding box and then snaps the viewport 
        to a specific coordinate, preventing the screen from jumping after an edit.
        """
        self.timeline.update_idletasks()
        
        bbox = self.timeline._parent_canvas.bbox("all")
        if bbox:
            self.timeline._parent_canvas.configure(scrollregion=bbox)
            
        if target_y is not None:
            self.timeline._parent_canvas.yview_moveto(target_y)

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
            # --- 0. THE CHAPTER MARKER CARD ---
            chap_card = ctk.CTkFrame(self.timeline, fg_color="transparent")
            chap_lbl = ctk.CTkLabel(chap_card, text="", font=("Georgia", 22, "bold", "italic"), text_color="#00ACC1")
            chap_lbl.pack(pady=(40, 10))
            
            # --- 1. THE BRIDGE CARD ---
            br_card = ctk.CTkFrame(self.timeline, corner_radius=10, fg_color=("#EBEBEB", "#22252A"), border_width=1, border_color=("#D3D3D3", "#343638"))
            
            br_hdr_frame = ctk.CTkFrame(br_card, fg_color="transparent")
            br_hdr_frame.pack(fill="x", padx=15, pady=(10, 5))
            
            br_btn_del = ctk.CTkButton(br_hdr_frame, text="X", width=28, height=24, fg_color="#B71C1C", hover_color="#7F0000")
            Tooltip(br_btn_del, "Delete this narrative bridge.")
            
            br_btn_gen = ctk.CTkButton(br_hdr_frame, text="⟳ Reroll", width=60, height=24, font=("Arial", 11), fg_color="#F57C00", hover_color="#E65100")
            Tooltip(br_btn_gen, "Ask AI to generate a brand new bridge from scratch.")
            
            br_btn_pol = ctk.CTkButton(br_hdr_frame, text="✨ Polish", width=60, height=24, font=("Arial", 11), fg_color="#9C27B0", hover_color="#7B1FA2")
            Tooltip(br_btn_pol, "AI Copy-Edit: Fix grammar/flow of this bridge.")
            
            br_btn_exp = ctk.CTkButton(br_hdr_frame, text="✨ Expand", width=60, height=24, font=("Arial", 11), fg_color="#00ACC1", hover_color="#00838F")
            Tooltip(br_btn_exp, "AI Expansion: Make this bridge slightly longer and more descriptive.")
            
            br_btn_edit = ctk.CTkButton(br_hdr_frame, text="✎ Edit", width=50, height=24, font=("Arial", 11), fg_color="#4A4A4A", hover_color="#333333")
            Tooltip(br_btn_edit, "Open the Narrative Editor to manually type changes.")
            
            br_hdr_lbl = ctk.CTkLabel(br_hdr_frame, text="", text_color="gray", font=self.header_font, justify="left", anchor="w")
            br_hdr_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            br_prose_lbl = ctk.CTkLabel(br_card, text="", font=self.prose_font, justify="left", anchor="w")
            br_prose_lbl.pack(fill="x", padx=20, pady=(5, 25))

            # --- 2. THE STORY CARD ---
            card = ctk.CTkFrame(self.timeline, corner_radius=10, fg_color=("#EBEBEB", "#22252A"), border_width=1, border_color=("#D3D3D3", "#343638"))
            
            hdr_frame = ctk.CTkFrame(card, fg_color="transparent")
            hdr_frame.pack(fill="x", padx=15, pady=(10, 0))
            
            btn_edit = ctk.CTkButton(hdr_frame, text="✎ Edit", width=50, height=24, fg_color="#4A4A4A", hover_color="#333333")
            btn_bridge = ctk.CTkButton(hdr_frame, text="✨ Bridge", width=60, height=24, fg_color="#00ACC1", hover_color="#00838F")
            
            hdr_lbl = ctk.CTkLabel(hdr_frame, text="", text_color="gray", font=self.header_font, justify="left", anchor="w")
            hdr_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            # Native horizontal row container for inventory pills
            inv_frame = ctk.CTkFrame(card, fg_color="transparent")
            inv_frame.pack(fill="x", padx=15, pady=(0, 5))
            
            # FIX: Anchor North-West so text always hugs the top, rather than floating in center
            prose_lbl = ctk.CTkLabel(card, text="", font=self.prose_font, justify="left", anchor="nw")
            prose_lbl.pack(fill="x", padx=20, pady=5)
            
            # FIX: Anchor North-West for the choice label as well
            c_lbl = ctk.CTkLabel(card, text="", font=self.action_font, text_color="#4CAF50", justify="left", anchor="nw")
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            
            self.recycled_cards.append({
                "chap_card": chap_card, "chap_lbl": chap_lbl,
                "br_card": br_card, "br_hdr": br_hdr_lbl, "br_prose": br_prose_lbl, 
                "br_btn_edit": br_btn_edit, "br_btn_gen": br_btn_gen, "br_btn_del": br_btn_del,
                "br_btn_pol": br_btn_pol, "br_btn_exp": br_btn_exp,
                "card": card, "hdr": hdr_lbl, "inv_frame": inv_frame,
                "prose": prose_lbl, "btn_edit": btn_edit, "btn_bridge": btn_bridge,
                "choice": c_lbl, "btn_frame": btn_frame
            })

    def refresh_timeline(self, retain_scroll=False):
        """
        Master Update Endpoint. Syncs the slider scale to the history length, 
        evaluates UI configurations, and triggers a visual render of the cards.
        """
        from config import ENGINE_CONFIG
        f_family = ENGINE_CONFIG.get("prose_font_family", "Georgia")
        f_size = ENGINE_CONFIG.get("prose_font_size", 15)
        self.prose_font = (f_family, int(f_size))
        self.bridge_font = (f_family, max(10, int(f_size)-1), "italic")
        
        for refs in self.recycled_cards:
            refs["prose"].configure(font=self.prose_font)
            refs["br_prose"].configure(font=self.bridge_font)
        
        # Preserve the new tight packing alignment when the UI redraws
        self.btn_submit.pack_forget()
        self.btn_submit.pack(side="right", padx=0, pady=10)

        if not self.engine.history:
            self._unlock_ui("Waiting for Director to start the adventure...")
            
            # Lock the input tools explicitly so they can't type before the game starts
            self.btn_submit.configure(state="disabled")
            self.text_input.configure(state="disabled")
            self.cmd_dropdown.configure(state="disabled")
            self.history_slider.configure(state="disabled")
            
            # Hide recycled cards and show the giant Start button
            for refs in self.recycled_cards:
                if "chap_card" in refs: refs["chap_card"].pack_forget()
                refs["br_card"].pack_forget()
                refs["card"].pack_forget()
                
            self.startup_frame.pack(fill="both", expand=True, pady=(100, 0))
            
            # FIX: Force the canvas to recalculate its height and snap to the absolute top
            self.timeline.update_idletasks()
            if hasattr(self.timeline, "_parent_canvas"):
                self.timeline._parent_canvas.yview_moveto(0.0)
                
            return
            
        self.startup_frame.pack_forget()

        # 1. Calculate boundaries and update slider
        max_start = max(0, len(self.engine.history) - self.MAX_CARDS)
        if max_start > 0:
            self.history_slider.configure(state="normal", from_=max_start, to=0, number_of_steps=max_start)
            self.history_slider.set(max_start)
        else:
            self.history_slider.configure(from_=1, to=0, number_of_steps=1) 
            self.history_slider.set(0)
            self.history_slider.configure(state="disabled")

        self.current_top_idx = max_start
        
        # 2. Draw the cards to the screen
        self._render_visible_cards(retain_scroll=retain_scroll)
        
        # 3. Unlock the UI explicitly (Resets all states)
        self._unlock_ui("Ready.")

    def _trigger_startup(self):
        """Fires when the user clicks the giant Start Adventure button on an empty timeline."""
        self.startup_frame.pack_forget()
        self._lock_ui("Generating opening scene...")
        import threading
        threading.Thread(target=self._async_init, daemon=True).start()

    def _calculate_inventory_state(self, up_to_idx):
        """Rebuilds the current inventory state by parsing history up to the target index."""
        base_schema = self.engine.setup_data.get("inventory_and_state", {})
        if not isinstance(base_schema, dict): base_schema = {}
        
        # Start with the baseline values from setup.json
        state = {k: v.get("val", "") for k, v in base_schema.items()}
        
        import re
        for i in range(up_to_idx + 1):
            if i >= len(self.engine.history) or i < 0: break
            inv_str = self.engine.history[i].get("inventory_and_state", "")
            if inv_str:
                inv_str = inv_str.replace("[Status]", "").strip()
                patterns = re.findall(r'([A-Za-z0-9_]+)\s*:\s*(.*?)(?=(?:[A-Za-z0-9_]+\s*:|$))', inv_str)
                for k, v in patterns:
                    clean_k = k.strip()
                    # Persistence Check: Only update keys that exist in our schema
                    if clean_k in state:
                        state[clean_k] = v.strip(' .,;')
        return state
        
    def _on_slider_move(self, value):
        """Callback for the 'Time Travel' scroll bar."""
        new_idx = int(value)
        if new_idx != self.current_top_idx:
            self.current_top_idx = new_idx
            self._render_visible_cards(auto_scroll=False)
            # When manually browsing history, always snap to the top of the slice
            self.timeline._parent_canvas.yview_moveto(0.0)

    def _render_visible_cards(self, retain_scroll=False):
        """
        Draws the actual history data into the 3 empty widget shells.
        If retain_scroll is True, it memorizes the exact pixel position of the viewport
        before redrawing, and restores it afterward to prevent UI jumping.
        """
        # Capture exactly where the user is looking before we destroy the layout
        current_scroll_y = None
        if retain_scroll and hasattr(self.timeline, "_parent_canvas"):
            current_scroll_y = self.timeline._parent_canvas.yview()[0]
            
        history = self.engine.history
        cheats_allowed = self.engine.setup_data.get("allow_cheats", False)
        from ui.tooltip import Tooltip

        # 0. Unpack EVERYTHING first to guarantee correct visual rendering order
        for refs in self.recycled_cards:
            if "chap_card" in refs: refs["chap_card"].pack_forget()
            refs["br_card"].pack_forget()
            refs["card"].pack_forget()

        for i in range(self.MAX_CARDS):
            target_idx = self.current_top_idx + i
            refs = self.recycled_cards[i]
            
            if target_idx < len(history):
                turn = history[target_idx]
                
                try: actual_turn = int(turn.get("turn", 0))
                except (ValueError, TypeError): actual_turn = 0
                
                # --- CHAPTER IDENTIFICATION LOGIC ---
                active_chap = self.engine.chapters[0]
                for c in reversed(self.engine.chapters):
                    s_turn = c.get("start_turn")
                    if s_turn is not None and s_turn <= actual_turn:
                        active_chap = c
                        break
                        
                is_epilogue = str(turn.get("is_game_over", False)).lower() == "true" and str(turn.get("chapter_goal_achieved", False)).lower() == "true"
                is_chap_start = False
                chap_title_for_card = ""
                chap_name_for_header = ""
                
                if actual_turn == 0:
                    chap_name_for_header = "Prologue"
                    if target_idx == 0:
                        is_chap_start = True
                        chap_title_for_card = "Prologue"
                elif is_epilogue:
                    chap_name_for_header = "Epilogue"
                    prev_over = str(history[target_idx-1].get("is_game_over", False)).lower() == "true" if target_idx > 0 else False
                    if not prev_over:
                        is_chap_start = True
                        chap_title_for_card = "Epilogue"
                else:
                    chap_name_for_header = f"Chapter {active_chap.get('chapter_number', 1)}"
                    if active_chap.get("start_turn") == actual_turn:
                        is_chap_start = True
                        c_title = active_chap.get('title', chap_name_for_header)
                        if c_title.lower() == chap_name_for_header.lower():
                            chap_title_for_card = chap_name_for_header
                        else:
                            chap_title_for_card = f"{chap_name_for_header}: {c_title}"
                            
                # 1. RENDER CHAPTER MARKER (Packed FIRST so it sits above everything)
                if is_chap_start and "chap_card" in refs:
                    refs["chap_card"].pack(fill="x")
                    refs["chap_lbl"].configure(text=f"~ {chap_title_for_card} ~")
                
                # 2. RENDER BRIDGE CARD (Packed SECOND)
                bridge = turn.get("narrative_bridge")
                is_valid_bridge = bridge and bridge not in ["[OK]", "[FAILED]", ""]
                
                if target_idx > 0 and is_valid_bridge:
                    refs["br_card"].pack(fill="x", padx=20, pady=(5, 0))
                    refs["br_hdr"].configure(text=f"Narrative Bridge between Turn {target_idx-1} and Turn {target_idx}")
                    refs["br_prose"].configure(text=bridge)
                    
                    # Bridges are post-production polish, so they are ALWAYS editable regardless of 'allow_cheats'
                    refs["br_btn_del"].pack(side="right", padx=(5, 0))
                    refs["br_btn_edit"].pack(side="right", padx=(5, 0))
                    refs["br_btn_pol"].pack(side="right", padx=(5, 0))
                    refs["br_btn_exp"].pack(side="right", padx=(5, 0))
                    refs["br_btn_gen"].pack(side="right", padx=(5, 0))
                    
                    refs["br_btn_edit"].configure(command=lambda idx=target_idx: self._open_edit_dialog(idx))
                    refs["br_btn_del"].configure(command=lambda idx=target_idx: self._delete_bridge_timeline(idx))
                    refs["br_btn_pol"].configure(command=lambda idx=target_idx: self._trigger_bridge_edit(idx, "polish"))
                    refs["br_btn_exp"].configure(command=lambda idx=target_idx: self._trigger_bridge_edit(idx, "expand"))
                    refs["br_btn_gen"].configure(command=lambda idx=target_idx: self._generate_bridge_timeline(idx))


                # 3. RENDER STORY CARD (Packed THIRD)
                refs["card"].pack(fill="x", padx=20, pady=10) 
                
                loc_raw = turn.get("location", "Unknown").strip()
                pov_raw = turn.get("pov_character", "Unknown").strip()
                
                # Smart Header formatting: Prevent massive lore dumps from breaking the single-line UI
                loc_hdr = loc_raw if len(loc_raw) <= 100 else "Current Location"
                pov_hdr = pov_raw if len(pov_raw) <= 100 else "Main Character"
                
                refs["hdr"].configure(text=f"{chap_name_for_header} - Turn {actual_turn} • [{loc_hdr}] • POV: {pov_hdr}")
                
                
                # 4. RENDER RPG INVENTORY PILLS
                refs["inv_frame"].pack_forget()
                for w in refs["inv_frame"].winfo_children(): 
                    w.destroy()
                
                schema = self.engine.setup_data.get("inventory_dictionary", {})
                is_game_over = str(turn.get("is_game_over", False)).lower() == "true"
                
                if self.engine.track_inventory and schema and isinstance(schema, dict) and not is_game_over:
                    inv_str = turn.get("inventory_and_state", "").replace("[Status]", "").strip()
                    import re
                    current_state = {}
                    for k, v in re.findall(r'([A-Za-z0-9_]+)\s*:\s*(.*?)(?=(?:[A-Za-z0-9_]+\s*:|$))', inv_str):
                        current_state[k.strip()] = v.strip(' .,;')
                    
                    refs["inv_frame"].pack(fill="x", padx=20, pady=(15, 0))
                    
                    # THE ULTIMATE TKINTER HACK: Textbox Window Embedding.
                    inv_box = ctk.CTkTextbox(
                        refs["inv_frame"], 
                        wrap="word", 
                        height=42, # Start tightly collapsed for 1 line
                        fg_color="transparent",
                        font=("Arial", 13, "bold"),
                        # API-Safe scrollbar cloaking (matches the card background exactly)
                        scrollbar_button_color=("#EBEBEB", "#22252A"),
                        scrollbar_button_hover_color=("#EBEBEB", "#22252A")
                    )
                    inv_box.pack(fill="x")
                    
                    # Save reference so the heartbeat can dynamically adjust the height
                    refs["inv_box"] = inv_box
                    
                    schema_items = list(schema.items())
                    for idx, (key, info) in enumerate(schema_items):
                        val = current_state.get(key, "None")
                        if not val or str(val).strip() == "": val = "None"
                        
                        icon = info.get("icon", "🎒")
                        base_color = info.get("color", "#1F6AA5")
                        is_last = (idx == len(schema_items) - 1)
                        
                        # Create a flat, transparent container for the icon + text
                        p_frame = ctk.CTkFrame(inv_box, fg_color="transparent")
                        
                        i_lbl = ctk.CTkLabel(p_frame, text=icon, font=("Segoe UI Emoji", 14), text_color=base_color, width=0)
                        i_lbl.pack(side="left", padx=(0, 4))
                        
                        v_lbl = ctk.CTkLabel(p_frame, text=val, font=("Arial", 12, "bold"), text_color="#B3E5FC", width=0)
                        v_lbl.pack(side="left")
                        
                        Tooltip(p_frame, key)
                        
                        # MAGIC: Embed the entire UI frame directly into the textbox
                        inv_box._textbox.window_create("end", window=p_frame)
                        
                        if not is_last:
                            inv_box.insert("end", "   |   ", "sep")
                            
                    inv_box.configure(state="disabled")
                            
                
                # 5. RENDER EDIT BUTTONS & TEXT
                refs["btn_edit"].pack_forget()
                refs["btn_bridge"].pack_forget()
                
                # Manual turn editing is a cheat, but Bridge generation is always allowed
                if cheats_allowed:
                    refs["btn_edit"].pack(side="right")
                    refs["btn_edit"].configure(command=lambda idx=target_idx: self._open_edit_dialog(idx))
                    
                if target_idx > 0 and not is_valid_bridge and bridge != "[OK]":
                    refs["btn_bridge"].pack(side="right", padx=(0, 5))
                    refs["btn_bridge"].configure(command=lambda idx=target_idx: self._generate_bridge_timeline(idx))
                    Tooltip(refs["btn_bridge"], "Generate a narrative transition from the previous turn.")
                        
                # FIX: Aggressively strip trailing newlines to prevent phantom vertical space
                prose_text = turn.get("story_text", "").replace("\\n", "\n").strip()
                
                # Inject massive lore dumps into the main prose body so they are readable
                injected_lore = ""
                if len(loc_raw) > 100: injected_lore += f"[Location]: {loc_raw}\n\n"
                if len(pov_raw) > 100: injected_lore += f"[POV]: {pov_raw}\n\n"
                
                if injected_lore:
                    prose_text = f"{injected_lore.strip()}\n\n***\n\n{prose_text}"
                    
                # Ensure the text box doesn't have internal padding fighting our layout
                refs["prose"].configure(text=prose_text)
                refs["prose"].pack(fill="x", padx=20, pady=(5, 0)) # Snap to top
                
                # 6. RENDER FOOTER & CHOICES
                refs["choice"].pack_forget()
                refs["btn_frame"].pack_forget()
                for w in refs["btn_frame"].winfo_children(): w.destroy()
                
                choice = turn.get("player_choice")
                if choice is not None:
                    refs["choice"].configure(text=f"❯ {choice}")
                    refs["choice"].pack(fill="x", padx=20, pady=(10, 15))
                else:
                    # FIX: Explicitly clear the string to force Tkinter to drop the cached height
                    refs["choice"].configure(text="")
                    refs["btn_frame"].pack(fill="x", padx=15, pady=(0, 20))
                    is_over = str(turn.get("is_game_over", False)).lower() == "true"
                    is_victory = turn.get("chapter_goal_achieved", False)
                    
                    show_redo = True
                    if is_over and is_victory:
                        e_style = self.engine.setup_data.get("narrative", {}).get("epilogue", "expand").lower()
                        if e_style in ["as_is", "none"]: show_redo = False

                    show_qol = not is_over
                    show_fix = cheats_allowed and not is_over

                    if not self.engine.is_test_mode:
                        dir_frame = ctk.CTkFrame(refs["btn_frame"], fg_color="transparent")
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

                            btn_cond = ctk.CTkButton(dir_frame, text="✨ Condense", width=60, fg_color="#3F51B5", hover_color="#303F9F", command=lambda: self._trigger_condense(target_idx))
                            btn_cond.pack(side="left", padx=5)
                            Tooltip(btn_cond, "Condense the prose to be shorter and punchier.")

                            btn_pol = ctk.CTkButton(dir_frame, text="✨ Polish", width=60, fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: self._trigger_polish(target_idx))
                            btn_pol.pack(side="left", padx=5)
                            Tooltip(btn_pol, "Fix grammar/style.")
                        
                        if show_fix:
                            btn_fix = ctk.CTkButton(dir_frame, text="🔧 Fix...", width=60, fg_color="#009688", hover_color="#00796B", command=lambda: self._trigger_fix(target_idx))
                            btn_fix.pack(side="left", padx=5)
                            Tooltip(btn_fix, "Instruct AI to change a specific detail.")
                            
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
            
        # Apply the layout and restore the camera
        target_y = current_scroll_y if retain_scroll else 1.0
        
        self._maintain_scroll_position(target_y) 
        # Multi-pass ensures it sticks even if images/text wrap late
        for ms in [50, 150, 300]:
            self.after(ms, lambda y=target_y: self._maintain_scroll_position(y))
                
                
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
            
            # Action Buttons
            btn_clear_br = ctk.CTkButton(br_hdr, text="X Clear", width=60, height=24, fg_color="#B71C1C", hover_color="#7F0000")
            btn_clear_br.pack(side="right", padx=2)
            Tooltip(btn_clear_br, "Wipe the textbox below.")

            btn_gen_br = ctk.CTkButton(br_hdr, text="⟳ Reroll", width=70, height=24, fg_color="#F57C00", hover_color="#E65100")
            btn_gen_br.pack(side="right", padx=2)
            Tooltip(btn_gen_br, "Ask AI to generate a brand new bridge connecting the previous action to this prose.")
            
            btn_pol_br = ctk.CTkButton(br_hdr, text="✨ Polish", width=70, height=24, fg_color="#9C27B0", hover_color="#7B1FA2")
            btn_pol_br.pack(side="right", padx=2)
            Tooltip(btn_pol_br, "AI Copy-Edit: Fix grammar/flow of this bridge.")
            
            btn_exp_br = ctk.CTkButton(br_hdr, text="✨ Expand", width=70, height=24, fg_color="#00ACC1", hover_color="#00838F")
            btn_exp_br.pack(side="right", padx=2)
            Tooltip(btn_exp_br, "AI Expansion: Make this bridge slightly longer and more descriptive.")
            
            bridge_box = ctk.CTkTextbox(scroll, height=100, wrap="word", font=self.prose_font)
            bridge_box.insert("1.0", turn.get("narrative_bridge", "").replace("\\n", "\n"))
            bridge_box.pack(fill="x", pady=(0, 20))
            
            # Enable OS standard shortcuts
            from ui.tooltip import apply_global_text_bindings
            try: bind_modern_text_shortcuts(bridge_box._textbox) # Fallback if global fails
            except: pass
            
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
                    if edit_type == "polish":
                        shorthand = f"Proofread and elevate the prose of this transition sentence: '{current_bridge}'"
                    else:
                        shorthand = f"Slightly expand this transition sentence by adding sensory detail: '{current_bridge}'"
                        
                    success, result = TomeWeaverAPI.generate_field_data(self.engine.setup_data, "tone", shorthand)
                    
                    def update_ui():
                        btn_ref.configure(state="normal", text=orig_text)
                        if success and result:
                            clean_res = result.strip('"\'')
                            bridge_box.delete("1.0", "end")
                            bridge_box.insert("1.0", clean_res)
                        else:
                            from tkinter import messagebox
                            messagebox.showerror("Error", f"Failed to {edit_type} bridge.\n{result}")
                            
                    self.after(0, update_ui)
                import threading
                threading.Thread(target=worker, daemon=True).start()
                
            btn_gen_br.configure(command=generate_bridge_async)
            btn_pol_br.configure(command=lambda: edit_bridge_async("polish", btn_pol_br))
            btn_exp_br.configure(command=lambda: edit_bridge_async("expand", btn_exp_br))
        else:
            bridge_box = None

        # --- PROSE SECTION ---
        header_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(header_frame, text="Story Prose:", font=("Arial", 16, "bold")).pack(side="left")
        
        btn_p = ctk.CTkButton(header_frame, text="✨ Polish", width=80, fg_color="#9C27B0", hover_color="#7B1FA2", command=lambda: [dialog.destroy(), self._trigger_polish(turn_idx)])
        btn_p.pack(side="right", padx=5)
        Tooltip(btn_p, "AI Copy-Edit: Fix grammar/flow in this specific card.")

        btn_c = ctk.CTkButton(header_frame, text="✨ Condense", width=80, fg_color="#3F51B5", hover_color="#303F9F", command=lambda: [dialog.destroy(), self._trigger_condense(turn_idx)])
        btn_c.pack(side="right", padx=5)
        Tooltip(btn_c, "AI Edit: Make this prose shorter and punchier.")
        
        btn_e = ctk.CTkButton(header_frame, text="✨ Expand", width=80, fg_color="#00ACC1", hover_color="#00838F", command=lambda: [dialog.destroy(), self._trigger_expansion(turn_idx)])
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
                    # --- INDIVIDUAL REROLL BUTTON ---
                    btn_reroll = ctk.CTkButton(row, text="⟳", width=25, fg_color="#F57C00", hover_color="#E65100")
                    btn_reroll.pack(side="left", padx=2)
                    Tooltip(btn_reroll, "Generate a new action to replace this one.")
                    
                    def do_reroll(target_var=var, target_btn=btn_reroll):
                        target_btn.configure(state="disabled", text="...")
                        
                        # Extract UI strings on the main thread safely before spawning the worker
                        current_story = story_box.get("1.0", "end").strip()
                        
                        # Gather choices to avoid, stripping out empty strings and the UI placeholder
                        existing_choices = [
                            v.get().strip() for v in self.choice_rows 
                            if v.get().strip() and v.get().strip() != "New action..."
                        ]
                        
                        def worker():
                            from llm import generate_single_choice
                            new_choice = generate_single_choice(current_story, existing_choices)
                            
                            def update_ui():
                                if new_choice:
                                    target_var.set(new_choice)
                                else:
                                    from tkinter import messagebox
                                    messagebox.showerror("Error", "Failed to generate a new choice. Check developer console.")
                                target_btn.configure(state="normal", text="⟳")
                            
                            # Push UI update back to main thread
                            self.after(0, update_ui)
                            
                        import threading
                        threading.Thread(target=worker, daemon=True).start()
                        
                    btn_reroll.configure(command=do_reroll)
                    
                    # --- INDIVIDUAL DELETE BUTTON ---
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
            self._render_visible_cards(retain_scroll=True) 
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
            self.refresh_timeline(retain_scroll=True)

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
            elif action_type == "condense":
                self._trigger_condense()
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

    def _trigger_condense(self, turn_idx=None):
        self._lock_ui("Condensing turn prose...")
        def worker():
            draft = self.engine.request_condense(turn_idx)
            self.after(0, lambda: self._show_draft_diff(draft, "condense"))
        threading.Thread(target=worker, daemon=True).start()
        
    def _trigger_fix(self, turn_idx=None):
        dialog = ctk.CTkInputDialog(text="Enter edit instruction (e.g., 'Make it raining'):", title="Director Fix")
        instruction = dialog.get_input()
        if not instruction: return
        
        self._lock_ui(f"Applying fix: {instruction[:15]}...")
        def worker():
            draft = self.engine.request_fix(instruction, turn_idx)
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
                self._render_visible_cards(retain_scroll=True) 
            self.after(0, update_ui)
            
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _trigger_bridge_edit(self, turn_idx, edit_type):
        """Uses the robust World Builder API to instantly Polish or Expand a specific bridge."""
        if turn_idx <= 0 or turn_idx >= len(self.engine.history): return
        
        current_bridge = self.engine.history[turn_idx].get("narrative_bridge", "").strip()
        if not current_bridge: return
            
        self._lock_ui(f"Applying {edit_type} to bridge...")
        
        def worker():
            from api import TomeWeaverAPI
            # We "trick" the field generator by passing it a custom shorthand instruction
            if edit_type == "polish":
                shorthand = f"Proofread and elevate the prose of this transition sentence: '{current_bridge}'"
            else:
                shorthand = f"Slightly expand this transition sentence by adding sensory detail: '{current_bridge}'"
                
            # 'tone' is a safe field key to pass so it borrows the world's vibe
            success, result = TomeWeaverAPI.generate_field_data(self.engine.setup_data, "tone", shorthand)
            
            def update_ui():
                if success and result:
                    # Strip quotes if the LLM wrapped it
                    clean_res = result.strip('"\'')
                    self.engine.history[turn_idx]["narrative_bridge"] = clean_res
                    self.engine.save_state()
                    self._render_visible_cards(retain_scroll=True) 
                else:
                    messagebox.showerror("Error", f"Failed to {edit_type} bridge.\n{result}")
                self._unlock_ui("Ready.")
                
            self.after(0, update_ui)
            
        import threading
        threading.Thread(target=worker, daemon=True).start()

        
    def _async_init(self):
        """Runs the Turn 1 / Prologue startup logic in the background."""
        try: 
            self.engine.initialize_game()
        except Exception as e: 
            self.after(0, lambda: messagebox.showerror("Engine Error", str(e)))
            
        def on_init_complete():
            self.refresh_timeline()
            
            # THE RESUME HOOK
            # Catches interrupted sessions immediately on launch without firing during normal gameplay
            if self.engine.history:
                last_turn = self.engine.history[-1]
                if last_turn.get("player_choice") is not None:
                    self._lock_ui("Resuming interrupted generation...")
                    def worker():
                        action_to_resume = last_turn["player_choice"]
                        self.engine.submit_action(action_to_resume)
                        self.after(0, self.refresh_timeline)
                    import threading
                    threading.Thread(target=worker, daemon=True).start()

        self.after(0, on_init_complete)

    def _lock_ui(self, status_msg):
        """Disables all input controls while the AI is generating."""
        if status_msg and status_msg != "Ready." and not status_msg.startswith("Autopilot:"):
            from colorama import Style
            print(f"{Style.DIM}[UI] {status_msg}{Style.RESET_ALL}")
            
        self.winfo_toplevel().configure(cursor="watch") # Spin cursor
            
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
                elif isinstance(w, ctk.CTkFrame):
                    for sub_w in w.winfo_children():
                        if isinstance(sub_w, ctk.CTkButton): sub_w.configure(state="disabled")

    def _unlock_ui(self, status_msg):
        """Restores interactivity after an AI generation completes."""
        if status_msg and status_msg != "Ready." and not status_msg.startswith("Autopilot:"):
            from colorama import Style
            print(f"{Style.DIM}[UI] {status_msg}{Style.RESET_ALL}")
            
        self.winfo_toplevel().configure(cursor="") # Restore cursor
            
        self.status_var.set(status_msg)
        self.btn_submit.configure(state="normal")
            
        for refs in self.recycled_cards:
            if "btn_bridge" in refs: refs["btn_bridge"].configure(state="normal")
            if "br_btn_gen" in refs: refs["br_btn_gen"].configure(state="normal")

        # --- AUTOPILOT HOOK ---
        if self.engine.is_test_mode:
            # Check if there is an active turn with choices to click
            if self.engine.history:
                last_turn = self.engine.history[-1]
                
                # Check for Game Over OR Epilogue completion
                is_over = str(last_turn.get("is_game_over", False)).lower() == "true"
                is_victory = str(last_turn.get("chapter_goal_achieved", False)).lower() == "true"
                
                # If it's a Victory Epilogue, it sets is_game_over to True, so we must stop.
                if is_over or (is_victory and last_turn.get("turn", 0) > 0):
                    self.workspace._toggle_test()
                    self.status_var.set("Autopilot finished: Campaign Complete.")
                    return
                
                if last_turn.get("choices"):
                    # Select Choice #1 (The Golden Path)
                    auto_choice = last_turn["choices"][0]
                    self.status_var.set(f"Autopilot: Selecting '{auto_choice[:20]}...' in 2s")
                    
                    def auto_step():
                        if self.engine.is_test_mode:
                            self._execute_action(auto_choice)
                        else:
                            self.status_var.set("Autopilot aborted.")

                    self.after(2000, auto_step)
                    
                    