"""
TomeWeaver: Base Engine Module (Headless API)
---------------------------------------------
The foundational headless architecture for TomeWeaver. Handles state management, 
API error handling, and core LLM generation loops. Designed to be operated by 
an external Graphical User Interface (GUI) via event-driven method calls.
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from colorama import Fore, Style

from config import load_json_safely, ENGINE_CONFIG
from llm import get_llm_response, generate_recap

# ---------------------------------------------------------
# BASE ENGINE CLASS
# ---------------------------------------------------------

class BaseEngine:

    # ---------------------------------------------------------
    # CONSTRUCTOR
    # ---------------------------------------------------------

    def __init__(self, adv_dir, setup_data):
        self.adv_dir = Path(adv_dir)
        self.setup_data = setup_data
        
        # --- LOAD PROLOGUE/EPILOGUE TEXT FILES ---
        self.prologue_content = ""
        self.epilogue_content = ""
        
        p_file = self.adv_dir / "prologue.txt"
        if p_file.exists():
            with open(p_file, "r", encoding="utf-8") as f:
                self.prologue_content = f.read().strip()
                
        e_file = self.adv_dir / "epilogue.txt"
        if e_file.exists():
            with open(e_file, "r", encoding="utf-8") as f:
                self.epilogue_content = f.read().strip()
        
        # History & Config
        self.history_file = self.adv_dir / "history.json"
        
        prompt_file = self.adv_dir / "system_prompt.txt"
        with open(prompt_file, "r", encoding="utf-8") as f:
            self.system_prompt_text = f.read()

        # 1. Load History
        self.history = load_json_safely(self.history_file, "history.json") if self.history_file.exists() else []
        
        # 2. Load Chapters (CRITICAL: Must happen before any save_state triggers)
        self.chapters = self.load_chapters()
        
        # --- AUTO-MIGRATION & REPAIR ---
        needs_save = False
        
        if "starting_inventory" in self.setup_data:
            raw_inv = str(self.setup_data.pop("starting_inventory"))
            self.setup_data["inventory_dictionary"] = self._parse_legacy_inventory(raw_inv)
            needs_save = True
            
        # Fix the ambiguous key if it was created during the buggy generation
        if "inventory_and_state" in self.setup_data:
            inv_data = self.setup_data.pop("inventory_and_state")
            if isinstance(inv_data, dict):
                if len(inv_data) == 1 and "Status" in inv_data and ":" in str(inv_data["Status"].get("val", "")):
                    self.setup_data["inventory_dictionary"] = self._parse_legacy_inventory(str(inv_data["Status"].get("val", "")))
                else:
                    self.setup_data["inventory_dictionary"] = inv_data
            else:
                self.setup_data["inventory_dictionary"] = self._parse_legacy_inventory(str(inv_data))
            needs_save = True
                    
        if needs_save:
            with open(self.adv_dir / "setup.json", "w", encoding="utf-8") as f:
                json.dump(self.setup_data, f, indent=4)
        
        # 3. Protect ledger integrity from manual file edits
        if self.history:
            self.resync_master_clock()
        
        self.is_campaign = False
        self.allow_manual_chapters = True
        self.track_inventory = self.setup_data.get("track_inventory", False)
        self.can_die = self.setup_data.get("can_die", False)
        self.allow_fix_command = self.setup_data.get("allow_cheats", True)
        
        # State Flags for GUI-Driven Non-Destructive Editing
        self.active_fix = None
        self.is_fix_mode = False
        self.backup_turn = None
        self.is_test_mode = False

        # --- AUTO NARRATIVE BRIDGE: STARTUP CATCH-UP ---
        # If enabled, automatically process any missing bridges on launch
        if ENGINE_CONFIG.get("auto_narrative_bridge", False):
            # We spawn this in a thread so it doesn't freeze the GUI while loading 10,000 old turns
            import threading
            threading.Thread(target=self.novelize_history, kwargs={"silent": False}, daemon=True).start()

    def _parse_legacy_inventory(self, raw_str):
        """Converts an old v1.0 inventory string into a v1.1 Schema Dictionary."""
        import re
        raw_str = raw_str.replace("[Status]", "").strip()
        new_schema = {}
        
        # Hunt for Key: Value patterns
        patterns = re.findall(r'([A-Za-z0-9_]+)\s*:\s*(.*?)(?=(?:[A-Za-z0-9_]+\s*:|$))', raw_str)
        
        if patterns:
            for k, v in patterns:
                clean_k = k.strip()
                clean_v = v.strip(' .,;')
                if not clean_v or clean_v.lower() == "none": clean_v = "None"
                
                # Apply smart coloring
                icon = "🎒"; color = "#1F6AA5"
                k_lower = clean_k.lower()
                if "health" in k_lower or "hp" in k_lower: icon = "❤️"; color = "#B71C1C"
                elif "state" in k_lower or "status" in k_lower: icon = "🧠"; color = "#7B1FA2"
                elif "gold" in k_lower or "money" in k_lower: icon = "🪙"; color = "#E65100"
                
                new_schema[clean_k] = {"val": clean_v, "icon": icon, "color": color}
        else:
            # Absolute fallback if it was a plain sentence
            new_schema["Inventory"] = {"val": raw_str, "icon": "🎒", "color": "#1F6AA5"}
            
        return new_schema

    # ---------------------------------------------------------
    # STATE & FILE MANAGEMENT
    # ---------------------------------------------------------

    def resync_master_clock(self):
        """
        Scans history and ensures all turn numbers are strictly sequential.
        Uses the first turn's number as the anchor to preserve user preference 
        while fixing duplicates and gaps caused by manual JSON edits.
        """
        if not self.history: return
        try: start_num = int(self.history[0].get("turn", 0))
        except (ValueError, TypeError): start_num = 0
            
        changed = False
        for i, turn in enumerate(self.history):
            expected_turn = start_num + i
            if turn.get("turn") != expected_turn:
                turn["turn"] = expected_turn
                changed = True
        
        if changed:
            from logger import log_event
            log_event(self.adv_dir, f"SYSTEM: Master Clock resynced (Anchor: {start_num}).")
            self.save_state()

    def load_chapters(self):
        """
        Loads the chapters.json file. If it does not exist, it initializes 
        a default chapter structure to track pacing and transitions.
        """
        chapters_file = self.adv_dir / "chapters.json"
        if not chapters_file.exists():
            initial_chapters = [{
                "chapter_number": 1,
                "title": self.setup_data.get("title", "Chapter 1"),
                "start_turn": 1,
                "end_turn": None
            }]
            with open(chapters_file, "w", encoding="utf-8") as f:
                json.dump(initial_chapters, f, indent=4)
            return initial_chapters
        return load_json_safely(chapters_file, "chapters.json")

    def save_state(self):
        """
        Commits the current history and chapters state to the disk, 
        ensuring that player progress is safely and persistently stored.
        """
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=4)
        with open(self.adv_dir / "chapters.json", "w", encoding="utf-8") as f:
            json.dump(self.chapters, f, indent=4)

    def get_next_turn_number(self):
        """Returns the next sequential turn number based on the history ledger."""
        if not self.history: return 0
        try: return int(self.history[-1].get("turn", 0)) + 1
        except (ValueError, TypeError): return len(self.history)


    # ---------------------------------------------------------
    # ABSTRACT ENGINE HOOKS (Implemented by Subclasses)
    # ---------------------------------------------------------

    def build_messages(self, target_turn):
        """Constructs the LLM prompt payload. Implemented by Sandbox/Campaign."""
        raise NotImplementedError("Must be implemented by child class")

    def post_generation_hook(self, turn_data):
        """Allows child classes to inject logic immediately after LLM generation."""
        pass 

    def process_custom_command(self, cmd_key, cmd_val):
        """Intercepts mode-specific commands (e.g., Sandbox Chapter Wizard)."""
        return False, None


    # ---------------------------------------------------------
    # CORE API: INITIALIZATION & ACTION FLOW (GUI ENDPOINTS)
    # ---------------------------------------------------------

    def initialize_game(self):
        """
        Endpoint: Called by the GUI when a story is loaded.
        Returns the current turn to display. If the story is brand new, 
        it handles Prologue/Seed logic or generates Turn 1.
        """
        print(f"{Fore.CYAN}Initializing Engine: {self.setup_data.get('title', 'Unknown')}...{Style.RESET_ALL}")
        
        if self.history:
            # Game is already in progress, return the latest state
            return self.history[-1]

        # Check for Startup Bypasses (Prologue or Story Seed)
        turn_data = self._check_startup_bypasses()
        if turn_data:
            self._process_valid_turn(turn_data)
            return turn_data

        # If no bypasses exist, generate the first turn from scratch
        print(f"{Style.DIM}Generating opening scene...{Style.RESET_ALL}")
        turn_data = self._generate_turn()
        if turn_data:
            self._process_valid_turn(turn_data)
        return turn_data


    def _check_startup_bypasses(self):
        """Checks for As-Is Prologues, Epilogues, or start_turn.json seeds."""
        is_first_turn = (len(self.history) == 0)
        is_concluding = (len(self.history) > 0 and self.history[-1].get("player_choice") == "Conclude the Story")
        
        narr_cfg = self.setup_data.get("narrative", {})
        p_style = narr_cfg.get("prologue", "expand").lower()
        e_style = narr_cfg.get("epilogue", "expand").lower()

        # --- PROLOGUE AS-IS BYPASS ---
        if is_first_turn and p_style == "as_is" and self.prologue_content:
            first_chap = self.chapters[0]
            turn_data = {
                "story_text": self.prologue_content,
                "pov_character": self.setup_data.get("main_character", "Protagonist"),
                "location": self.setup_data.get("setting", "The Beginning"),
                "input_type": "choice",
                "choices": [f"Start Chapter 1: {first_chap['title']}"],
                "text_prompt": None,
                "turn": self.get_next_turn_number(),
                "player_choice": None
            }
            if self.is_campaign:
                turn_data["goal_progress"] = "Setting the scene."
                turn_data["chapter_goal_achieved"] = False
            if self.track_inventory: 
                inv_setup = self.setup_data.get("inventory_dictionary", "")
                if isinstance(inv_setup, dict):
                    turn_data["inventory_dictionary"] = " ".join([f"{k}: {v.get('val', '')}." for k, v in inv_setup.items()]).strip()
                else:
                    turn_data["inventory_dictionary"] = str(inv_setup)
            if self.can_die: turn_data["is_game_over"] = False
            return turn_data

        # --- EPILOGUE AS-IS BYPASS ---
        elif is_concluding and e_style == "as_is" and self.epilogue_content:
            turn_data = {
                "story_text": self.epilogue_content + "\n\n*** THE END. ***",
                "turn": self.get_next_turn_number(),
                "pov_character": self.setup_data.get("main_character", "Protagonist"),
                "location": "The End",
                "input_type": "choice",
                "choices": ["Export Story", "Restart Game", "Quit"],
                "text_prompt": None,
                "player_choice": None
            }
            if self.is_campaign:
                turn_data["goal_progress"] = "Journey Complete."
                turn_data["chapter_goal_achieved"] = True
            if self.track_inventory: 
                inv_setup = self.setup_data.get("inventory_dictionary", "")
                if isinstance(inv_setup, dict):
                    turn_data["inventory_dictionary"] = " ".join([f"{k}: {v.get('val', '')}." for k, v in inv_setup.items()]).strip()
                else:
                    turn_data["inventory_dictionary"] = str(inv_setup)
            turn_data["is_game_over"] = True
            return turn_data

        # --- THE STORY SEED INTERCEPTOR (TURN 1) ---
        is_at_start = (len(self.history) == 0 or (len(self.history) == 1 and str(self.history[0].get("player_choice", "")).startswith("Start Chapter")))
        seed_file = self.adv_dir / "start_turn.json"

        if is_at_start and seed_file.exists():
            seed_data = load_json_safely(seed_file, "start_turn.json")
            # Safely handle empty lists to prevent IndexError crashes
            if isinstance(seed_data, list) and len(seed_data) > 0:
                turn_data = seed_data[-1]
            elif isinstance(seed_data, dict):
                turn_data = seed_data
            else:
                turn_data = None
                
            if turn_data:
                turn_data["turn"] = self.get_next_turn_number()
                turn_data["player_choice"] = None
                return turn_data

        return None


    def submit_action(self, player_choice):
        """
        Endpoint: Called by the GUI when the player selects or types an action.
        Commits the choice, generates the next turn, and returns the new state.
        """
        from logger import log_event
        if not self.history: return None
        
        # --- META-CHOICE INTERCEPTOR ---
        # If the GUI blindly passes back one of the Engine's Game Over / Victory buttons,
        # we intercept it here to prevent the AI from generating a story about the UI.
        pc_exact = str(player_choice).strip()
        if pc_exact == "Restart Game": return self.restart_campaign()
        if pc_exact.startswith("Undo (Cheat Death"): return self.undo()
        if pc_exact in ["Quit", "Export Story", "Export Tragic Ending"]: return None
        
        # Handle Chapter Wizard overrides from Sandbox Engine
        handled, p_choice = self.process_custom_command(player_choice, "")
        if handled and p_choice:
            player_choice = p_choice
            
        log_event(self.adv_dir, f"Player Action [Turn {len(self.history)}]: {player_choice}")

        # Update Chapter Markers if jumping
        if player_choice.startswith("Start Chapter:"):
            pending = next((c for c in self.chapters if c.get("start_turn") is None), None)
            if pending:
                pending["start_turn"] = len(self.history) + 1
                if len(self.chapters) > 1: 
                    self.chapters[-2]["end_turn"] = len(self.history)

        # Save action to ledger
        self.history[-1]["player_choice"] = player_choice
        self.save_state()

        # Auto Narrative Bridge background hook: Render gap before generating next turn
        if ENGINE_CONFIG.get("auto_narrative_bridge", False) and len(self.history) >= 1:
            self._generate_bridge_for_latest_action()

        print(f"{Style.DIM}Generating turn...{Style.RESET_ALL}")
        
        # Check if the player choice triggered a bypass (like "Conclude the Story")
        bypass = self._check_startup_bypasses()
        if bypass:
            self._process_valid_turn(bypass)
            return bypass

        # Standard generation route
        turn_data = self._generate_turn()
        if turn_data:
            self._process_valid_turn(turn_data)
        return turn_data


    # ---------------------------------------------------------
    # CORE API: DRAFT EDITING (GUI Driven)
    # ---------------------------------------------------------
    # These endpoints replace the old CLI "review_mode" loop. The GUI calls one 
    # of these to get a proposed JSON object, displays a diff to the user, and 
    # then calls commit_draft() or cancel_draft().

    def redo_turn(self):
        """Endpoint: Destructively pops the current turn and immediately commits a completely new one."""
        from logger import log_event
        if len(self.history) == 0: return None
        
        log_event(self.adv_dir, "Command: REDO (User destructively rerolled turn)")
        print(f"{Style.DIM}Generating alternative version...{Style.RESET_ALL}")
        
        # 1. Completely discard the current turn
        self.history.pop()
        self.save_state()
        
        # 2. Generate a brand new turn from scratch (NO draft inheritance)
        turn_data = self._generate_turn()
        
        # 3. Commit it automatically
        if turn_data: 
            self._process_valid_turn(turn_data)
        
        return turn_data

    def redo_choices(self, turn_idx=None):
        """Endpoint: Keeps the story prose but generates a new set of choices. Supports historical turns."""
        from logger import log_event
        if len(self.history) == 0: return None
        
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        log_event(self.adv_dir, f"Command: REDO CHOICES (Turn {idx})")
        print(f"{Style.DIM}Generating new choices for Turn {idx}...{Style.RESET_ALL}")
        
        self.backup_turn = self.history.pop(idx)
        
        prompt = (
            "EDIT MODE: Generate 3 to 6 completely NEW, actionable, and immersive choices for the player based on the current scene. "
            "Do NOT include meta-notes, director instructions, or outcomes. Keep them brief.\n"
            "CRITICAL: Keep the 'story_text' EXACTLY the same.\n"
            f"Original JSON:\n{json.dumps(self.backup_turn, indent=2)}"
        )
        self.active_fix = prompt
        self.is_fix_mode = True
        
        turn_data = self._generate_turn()
        
        if turn_data:
            # REVERSE INHERITANCE: Forcefully overwrite the AI's text with the original backup text.
            # This mathematically guarantees the prose, location, and POV cannot be altered by hallucinations.
            turn_data["story_text"] = self.backup_turn.get("story_text", "")
            turn_data["location"] = self.backup_turn.get("location", "Unknown")
            turn_data["pov_character"] = self.backup_turn.get("pov_character", "Unknown")
            if self.track_inventory:
                turn_data["inventory_and_state"] = self.backup_turn.get("inventory_and_state", "")
                
            # Restore historical player choices and bridges if we are editing the past
            if "player_choice" in self.backup_turn: turn_data["player_choice"] = self.backup_turn["player_choice"]
            if "narrative_bridge" in self.backup_turn: turn_data["narrative_bridge"] = self.backup_turn["narrative_bridge"]
                
            self.active_fix = None
            self.is_fix_mode = False
            self.backup_turn = None
            
            # Reinsert safely
            if idx == len(self.history):
                self._process_valid_turn(turn_data)
            else:
                self.history.insert(idx, turn_data)
                self.save_state()
            return turn_data
            
        # If the LLM completely fails, safely restore the original turn
        self.history.insert(idx, self.backup_turn)
        self.save_state()
        self.active_fix = None
        self.is_fix_mode = False
        self.backup_turn = None
        return None
        
    def request_expansion(self):
        """Endpoint: Generates a context-aware descriptive expansion DRAFT of the current turn."""
        if len(self.history) == 0: return None
        print(f"{Style.DIM}Expanding turn prose...{Style.RESET_ALL}")
        
        # 1. Stage the turn to be expanded
        self.backup_turn = self.history.pop(idx)
        self.backup_turn_idx = idx 
        
        # 2. Gather World Context
        world_info = {
            "title": self.setup_data.get("title"),
            "tone": self.setup_data.get("tone"),
            "lore": self.setup_data.get("lore_and_rules"),
            "protagonist": self.setup_data.get("main_character")
        }
        
        # 3. Gather Narrative Context (The turn immediately preceding this one)
        prev_story = "This is the first turn of the adventure."
        if idx > 0:
            prev_turn = self.history[idx - 1]
            prev_story = f"PREVIOUS SCENE: {prev_turn.get('story_text', '')}\nACTION TAKEN: {prev_turn.get('player_choice', '')}"

        # 4. Construct High-Context Prompt
        prompt = (
            "EDIT MODE (EXPAND): You are a literary expansion agent. Your task is to take a short 'story_text' "
            "and expand it into 3-5 rich, cinematic paragraphs.\n\n"
            "--- WORLD CONTEXT ---\n"
            f"{json.dumps(world_info, indent=2)}\n\n"
            "--- NARRATIVE CONTEXT ---\n"
            f"{prev_story}\n\n"
            "--- TASK ---\n"
            "Expand the 'story_text' in the Original JSON below. Use the World and Narrative context above to ensure "
            "consistency in tone and continuity.\n"
            "1. USE sensory details (textures, lighting, smells) and internal character emotions.\n"
            "2. CRITICAL: DO NOT change the plot or resolve the current moment. Stay strictly within the current scene.\n"
            "3. CRITICAL: DO NOT introduce new items or characters not mentioned in the context.\n"
            "4. CRITICAL: DO NOT touch dialogue. Leave text inside quotation marks EXACTLY as written.\n\n"
            f"Original JSON to Expand:\n{json.dumps(self.backup_turn, indent=2)}"
        )
        
        self.active_fix = prompt
        self.is_fix_mode = True
        
        draft = self._generate_turn()
        if draft: self._apply_draft_inheritance(draft)
        return draft
        
    def request_polish(self, turn_idx=None):
        """Endpoint: Generates a polished DRAFT. Supports historical turns."""
        if len(self.history) == 0: return None
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        
        self.backup_turn = self.history.pop(idx)
        self.backup_turn_idx = idx
        print(f"{Style.DIM}Polishing Turn {idx} prose...{Style.RESET_ALL}")
        
        prompt = (
            "EDIT MODE (POLISH): Proofread and elevate the 'story_text' to professional novel quality. "
            "Fix grammar and vocabulary. DO NOT change the plot or touch dialogue.\n"
            f"Original JSON:\n{json.dumps(self.backup_turn, indent=2)}"
        )
        self.active_fix = prompt
        self.is_fix_mode = True
        
        draft = self._generate_turn()
        if draft: self._apply_draft_inheritance(draft)
        return draft


    def request_fix(self, instruction, turn_idx=None):
        """Endpoint: Generates a targeted-edit DRAFT based on user instruction."""
        if len(self.history) == 0: return None
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        
        print(f"{Style.DIM}Generating fix for Turn {idx}...{Style.RESET_ALL}")
        self.backup_turn = self.history.pop(idx)
        self.backup_turn_idx = idx
        
        self.active_fix = f"EDIT MODE: Apply this fix: '{instruction}'. Original JSON:\n{json.dumps(self.backup_turn, indent=2)}"
        self.is_fix_mode = True
        
        draft = self._generate_turn()
        if draft: self._apply_draft_inheritance(draft)
        return draft

    def _apply_draft_inheritance(self, draft_turn):
        """STRICT INHERITANCE: Protects structural JSON metadata from AI hallucinations."""
        if self.backup_turn:
            draft_turn["choices"] = self.backup_turn.get("choices", [])
            draft_turn["location"] = self.backup_turn.get("location", "Unknown")
            draft_turn["pov_character"] = self.backup_turn.get("pov_character", "Unknown")
            if self.track_inventory: draft_turn["inventory_and_state"] = self.backup_turn.get("inventory_and_state", "")
            # Preserve history for targeted edits
            if "player_choice" in self.backup_turn: draft_turn["player_choice"] = self.backup_turn["player_choice"]
            if "narrative_bridge" in self.backup_turn: draft_turn["narrative_bridge"] = self.backup_turn["narrative_bridge"]
                
    def request_reroll_draft(self):
        """Endpoint: Generates a new draft based on the currently active fix mode, WITHOUT popping history."""
        if not self.backup_turn: return None
        print(f"{Style.DIM}Rerolling draft...{Style.RESET_ALL}")
        draft = self._generate_turn()
        if draft: self._apply_draft_inheritance(draft)
        return draft

    def commit_draft(self, draft_turn):
        """Endpoint: Accepts the drafted turn and permanently saves it to history."""
        idx = getattr(self, 'backup_turn_idx', len(self.history))
        self.active_fix = None
        self.is_fix_mode = False
        self.backup_turn = None
        
        # If it's the active turn, run the mechanical hooks (goals/game over)
        if idx == len(self.history):
            self._process_valid_turn(draft_turn)
        else:
            # If editing history, just surgically insert it to prevent breaking plot logic
            self.history.insert(idx, draft_turn)
            self.save_state()
            
        if hasattr(self, 'backup_turn_idx'): delattr(self, 'backup_turn_idx')
        return draft_turn

    def cancel_draft(self):
        """Endpoint: Discards the draft and restores the original turn state."""
        if self.backup_turn:
            idx = getattr(self, 'backup_turn_idx', len(self.history))
            self.history.insert(idx, self.backup_turn)
            self.save_state()
            
        self.active_fix = None
        self.is_fix_mode = False
        self.backup_turn = None
        if hasattr(self, 'backup_turn_idx'): delattr(self, 'backup_turn_idx')
        return self.history[-1] if self.history else None

    def request_bridge_generation(self, turn_idx):
        """Endpoint: Manually asks the AI to generate a narrative bridge for a specific turn."""
        if turn_idx <= 0 or turn_idx >= len(self.history): return None
        
        prev_turn = self.history[turn_idx - 1]
        curr_turn = self.history[turn_idx]
        action = prev_turn.get("player_choice")
        
        if not action: return None
        
        print(f"{Style.DIM}Generating manual bridge for Turn {turn_idx}...{Style.RESET_ALL}")
        from llm import generate_narrative_bridge
        return generate_narrative_bridge(prev_turn, action, curr_turn)
        
    # ---------------------------------------------------------
    # CORE API: UTILITIES
    # ---------------------------------------------------------

    def undo(self):
        """Endpoint: Pops the last turn and reverts the previous choice."""
        from logger import log_event
        if len(self.history) > 1:
            log_event(self.adv_dir, "Command: UNDO (User backtracked via GUI)")
            self.history.pop()
            self.history[-1]["player_choice"] = None 
            
            # Revert Chapter markers
            t_turn = len(self.history) + 1
            if self.chapters[-1].get("start_turn") == t_turn:
                self.chapters[-1]["start_turn"] = None
                if len(self.chapters) > 1: self.chapters[-2]["end_turn"] = None
            elif self.chapters[-1].get("start_turn") is None and len(self.chapters) > 1:
                self.chapters.pop()
            
            self.save_state()
        return self.history[-1] if self.history else None

    def restart_campaign(self):
        """Endpoint: Wipes all progress safely and restarts the engine."""
        from logger import log_event
        log_event(self.adv_dir, "Command: RESTART ADVENTURE")
        self.history.clear()
        
        # Reset Chapter bounds depending on Mode
        if self.is_campaign:
            for c in self.chapters:
                c["start_turn"] = 1 if c["chapter_number"] == 1 else None
                c["end_turn"] = None
        else:
            self.chapters = [self.chapters[0]]
            self.chapters[0]["start_turn"] = 1
            self.chapters[0]["end_turn"] = None
        
        # Flush the session log file so debugging is clean for the new run
        log_file = self.adv_dir / "session_log.txt"
        if log_file.exists():
            try: log_file.unlink() 
            except Exception: pass

        self.save_state()
        return self.initialize_game()

    def toggle_test_mode(self, enabled: bool):
        """Endpoint: Allows the GUI to enable/disable Autopilot routing."""
        self.is_test_mode = enabled
        return self.is_test_mode
        
    def manual_edit_turn(self, turn_index, field, new_text):
        """Endpoint: Allows the GUI to directly overwrite a string in history (e.g., fixing a typo)."""
        if 0 <= turn_index < len(self.history):
            if field in self.history[turn_index]:
                self.history[turn_index][field] = new_text
                self.save_state()
                return True
        return False

    def request_recap(self):
        """Endpoint: Triggers the LLM to write a summary of the adventure so far."""
        return generate_recap(self.setup_data, self.history)

    def export_adventure(self, export_type=1, use_novelization=True, custom_path=None):
        """Endpoint: Routes export requests to the exporter module."""
        from exporter import export_story
        return export_story(self.adv_dir, self.setup_data, self.history, self.chapters, export_type, use_novelization, custom_path)


    # ---------------------------------------------------------
    # THE LLM GENERATION PIPELINE
    # ---------------------------------------------------------

    def _generate_turn(self):
        """
        The underlying generation loop. Contacts the LLM, handles retries, 
        rate limits, auto-polishing, and missing choice generation.
        """
        from logger import log_event
        max_retries = ENGINE_CONFIG.get("max_retries", 10)
        
        # --- CONTEXT OVERRIDE FOR FIX/POLISH ---
        if self.active_fix and self.is_fix_mode:
            editor_sys = self.system_prompt_text + "\n\nCRITICAL: You are acting as a professional editor. You output ONLY valid JSON matching the schema above."
            base_messages = [
                {"role": "system", "content": editor_sys},
                {"role": "user", "content": self.active_fix}
            ]
        else:
            base_messages = self.build_messages(self.get_next_turn_number())

        prev_turn_obj = self.history[-1] if self.history else None
        turn_data = None
        err = None

        for attempt in range(max_retries):
        
            # --- THE FEEDBACK LOOP ---
            # Help the AI by telling it exactly what JSON syntax it broke
            active_messages = base_messages.copy()
            if attempt > 0 and err:
                feedback = f"Your previous JSON was invalid. Error: {err}."
                if "Expecting" in str(err) or "control character" in str(err).lower():
                    feedback += " CRITICAL: Use \\\" for dialogue and \\n for new lines. Do NOT press Enter inside a JSON string."
                active_messages.append({"role": "user", "content": f"{feedback} Please correct it."})

            turn_data, err, raw = get_llm_response(
                active_messages, attempt, self.adv_dir, prev_turn_obj, self.is_fix_mode, 
                self.is_campaign, self.track_inventory, self.can_die, self.is_test_mode
            )
            
            if turn_data:
                # --- THE INDESTRUCTIBLE STAMP ---
                # Overwrite hallucinated turn numbers with the true Master Clock
                turn_data["turn"] = self.get_next_turn_number()
                break 
                
            # --- THE API ERROR SUITE ---
            print(f"{Fore.RED}[!] Attempt {attempt+1} Failed: {err}{Style.RESET_ALL}")
            err_str = str(err).lower()
            if any(x in err_str for x in ["429", "quota", "too many requests"]):
                delay = 15.0 
                if attempt < max_retries - 1:
                    print(f"{Style.DIM}Backing off to respect API limits...{Style.RESET_ALL}")
                    time.sleep(delay)
            elif any(x in err_str for x in ["503", "502", "504", "unavailable"]):
                if attempt < max_retries - 1: time.sleep(10)
            elif attempt < max_retries - 1:
                time.sleep(1)
        
        if not turn_data:
            print(f"{Fore.RED}Critical Error: LLM failed to produce valid JSON after {max_retries} attempts.{Style.RESET_ALL}")
            log_event(self.adv_dir, "SYSTEM FAILURE: Max retries exceeded.")
            return None
            
        # --- AUTO-POLISH INTERCEPTOR ---
        if ENGINE_CONFIG.get("auto_polish", False) and not self.is_fix_mode:
            print(f"{Style.DIM}Auto-polishing prose...{Style.RESET_ALL}")
            turn_data = self._auto_polish_pass(turn_data, prev_turn_obj, max_retries)

        # --- MISSING CHOICES INTERCEPTOR ---
        is_concluding = (len(self.history) > 0 and self.history[-1].get("player_choice") == "Conclude the Story")
        if not is_concluding and not self.is_fix_mode:
            current_choices = turn_data.get("choices", [])
            if len(current_choices) < 2:
                is_override = False
                if self.is_campaign and turn_data.get("chapter_goal_achieved"): is_override = True
                if not self.is_campaign and next((c for c in self.chapters if c.get("start_turn") is None), None): is_override = True
                    
                if not is_override:
                    from llm import generate_missing_choices
                    new_choices = generate_missing_choices(turn_data.get("story_text", ""), self.get_next_turn_number())
                    if len(new_choices) >= 2: turn_data["choices"] = new_choices

        return turn_data

    def _auto_polish_pass(self, draft, prev_turn_obj, max_retries):
        """Silently upgrades the prose of a freshly generated turn."""
        polish_prompt = (
            "EDIT MODE (POLISH): You are a professional copy-editor. Your task is to proofread and heavily elevate the 'story_text' "
            "of the provided JSON to the quality of a published novel.\n"
            "1. You MUST fix missing determiners, prepositions, and correct awkward phrasing.\n"
            "2. You MUST enhance sentence flow, vocabulary, and descriptive imagery.\n"
            "3. CRITICAL: DO NOT touch dialogue. Leave all text inside quotation marks EXACTLY as written to preserve character accents.\n"
            "4. CRITICAL: Do NOT alter the plot, setting, POV, or choices. Only enhance the prose delivery.\n"
            f"Original JSON:\n{json.dumps(draft, indent=2)}"
        )
        polish_msgs = [
            {"role": "system", "content": self.system_prompt_text + "\n\nCRITICAL: You are acting as a professional editor. You output ONLY valid JSON matching the schema above."},
            {"role": "user", "content": polish_prompt}
        ]
        
        for p_attempt in range(max_retries):
            polished_data, _, _ = get_llm_response(
                polish_msgs, p_attempt, self.adv_dir, prev_turn_obj, False, 
                self.is_campaign, self.track_inventory, self.can_die, self.is_test_mode
            )
            if polished_data:
                # Inheritance protection to ensure the editor didn't break game logic
                polished_data["choices"] = draft.get("choices", [])
                polished_data["location"] = draft.get("location", "Unknown")
                polished_data["pov_character"] = draft.get("pov_character", "Unknown")
                if self.track_inventory: polished_data["inventory_and_state"] = draft.get("inventory_and_state", "")
                polished_data["turn"] = self.get_next_turn_number()
                return polished_data
            time.sleep(1)
        return draft

    def _process_valid_turn(self, turn_data):
        """Finalizes the turn data, runs mechanical hooks, and saves to history."""
        # 1. Run Mechanical Hooks (Campaign Goals, Chapter logic)
        self.post_generation_hook(turn_data)

        # 2. Sandbox Chapter Logic (Injects transitional choices)
        if not self.is_campaign:
            pending_chap = next((c for c in self.chapters if c.get("start_turn") is None), None)
            if pending_chap and turn_data.get("player_choice") is None and not turn_data.get("is_game_over"):
                turn_data["choices"] = [f"Start Chapter: {pending_chap['title']}"]

        # 3. Mortality/Victory Interceptor
        if self.can_die:
            if str(turn_data.get("is_game_over", False)).lower() == "true":
                prev_choice = self.history[-1].get("player_choice", "") if self.history else ""
                if prev_choice == "Conclude the Story":
                    print(f"\n{Fore.GREEN}[System: CAMPAIGN COMPLETE! Victory achieved.]{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}[System: GAME OVER! The protagonist has met their end.]{Style.RESET_ALL}")
                
                # Force the UI to display meta-options instead of standard gameplay choices
                turn_data["input_type"] = "choice"
                turn_data["choices"] = [
                    "Undo (Cheat Death and try a different action)",
                    "Restart Game",
                    "Export Tragic Ending",
                    "Quit"
                ]

        # 4. Finalize and Save
        self.active_fix = None
        self.is_fix_mode = False
        turn_data["player_choice"] = None 
        self.history.append(turn_data)
        self.save_state()

    def _generate_bridge_for_latest_action(self):
        """Background hook to weave novelized prose seamlessly during gameplay."""
        if len(self.history) < 2: return
        prev_turn = self.history[-2]
        action = prev_turn.get("player_choice")
        ui_cmds = ["Start Chapter:", "Conclude the Story", "Restart", "Export", "Undo", "Quit", "Cheat Death"]
        
        is_chapter_jump = str(action).startswith("Start Chapter:") or str(action) == "Complete the Chapter"
        
        if action and not is_chapter_jump and not any(ui in str(action) for ui in ui_cmds):
            print(f"{Style.DIM}Weaving narrative bridge...{Style.RESET_ALL}")
            from llm import generate_narrative_bridge
            bridge_data = generate_narrative_bridge(prev_turn, action, self.history[-1])
            if bridge_data:
                self.history[-1]["narrative_bridge"] = bridge_data
                self.save_state()

    def novelize_history(self, silent=True):
        """Background worker to loop through the entire history and patch missing bridges."""
        from llm import generate_narrative_bridge
        processed_count = 0
        ui_commands = ["Start Chapter:", "Conclude the Story", "Restart", "Export", "Undo", "Quit", "Cheat Death"]

        for i in range(1, len(self.history)):
            current_turn = self.history[i]
            prev_turn = self.history[i-1]
            action = prev_turn.get("player_choice")
            
            if not action or any(ui in str(action) for ui in ui_commands): continue
            
            existing = current_turn.get("narrative_bridge")
            if existing and existing not in ["[FAILED]", "", {}]: continue
                
            if str(action).startswith("Start Chapter:") or str(action) == "Complete the Chapter": continue
            
            if not silent: print(f"{Style.DIM}Auto-Bridging Turn {current_turn['turn']}...{Style.RESET_ALL}")
            bridge_data = generate_narrative_bridge(prev_turn, action, current_turn)
            
            if bridge_data:
                current_turn["narrative_bridge"] = bridge_data
                if bridge_data not in ["[OK]", "[FAILED]"]: processed_count += 1
                self.save_state()

        if not silent and processed_count > 0:
            print(f"{Fore.GREEN}Auto Narrative Bridge: {processed_count} gaps patched.{Style.RESET_ALL}")