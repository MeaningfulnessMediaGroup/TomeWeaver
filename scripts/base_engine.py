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

from config import load_json_safely, ENGINE_CONFIG, PROMPTS
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
        
        # 3. Load Long-Term Memory (RAG)
        self.memory_file = self.adv_dir / "memory.json"
        if self.memory_file.exists():
            self.memory = load_json_safely(self.memory_file, "memory.json")
            
            # --- AUTO MIGRATION: V1 to V1.1 Split Ledgers ---
            if "entity_ledger" in self.memory:
                self.memory["character_ledger"] = self.memory.pop("entity_ledger")
                self.memory["location_ledger"] = {}
                self.save_state()
                
            # Ensure alias dictionary exists
            if "aliases" not in self.memory:
                self.memory["aliases"] = {"character_ledger": {}, "location_ledger": {}, "artifact_ledger": {}}
                self.save_state()
                
            # Auto-migrate v1.2 Artifact Ledger
            if "artifact_ledger" not in self.memory:
                self.memory["artifact_ledger"] = {}
                self.memory["aliases"]["artifact_ledger"] = {}
                self.save_state()
                
            # Auto-migrate v1.3 Faction Ledger
            if "faction_ledger" not in self.memory:
                self.memory["faction_ledger"] = {}
                self.memory["aliases"]["faction_ledger"] = {}
                self.save_state()
                
            # Auto-migrate v1.4 Chapter Ledger
            if "chapter_ledger" not in self.memory:
                self.memory["chapter_ledger"] = []
                self.save_state()
        else:
            self.memory = {
                "plot_ledger": [], 
                "character_ledger": {}, 
                "location_ledger": {},
                "artifact_ledger": {},
                "faction_ledger": {},
                "chapter_ledger": [],
                "aliases": {"character_ledger": {}, "location_ledger": {}, "artifact_ledger": {}, "faction_ledger": {}}
            }
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
            from config import save_json_atomically
            save_json_atomically(self.setup_data, self.adv_dir / "setup.json")
        
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
        Commits the current history, chapters, and memory state to the disk using atomic writes, 
        ensuring that player progress is safely and persistently stored without corruption risk.
        """
        import time
        self.last_save_time = time.time() # Used by the UI to detect background updates
        
        from config import save_json_atomically
        save_json_atomically(self.history, self.history_file)
        save_json_atomically(self.chapters, self.adv_dir / "chapters.json")
        save_json_atomically(self.memory, self.memory_file)

    def get_next_turn_number(self):
        """Returns the next sequential turn number based on the history ledger."""
        if not self.history: return 0
        
        # If we are editing a historical turn, return that specific turn's number
        if hasattr(self, 'backup_turn_idx'):
            return self.history[self.backup_turn_idx].get("turn", self.backup_turn_idx + 1)
            
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
                    turn_data["inventory_and_state"] = " ".join([f"{k}: {v.get('val', '')}." for k, v in inv_setup.items()]).strip()
                else:
                    turn_data["inventory_and_state"] = str(inv_setup)
            
            # FIX: Turn 0 is mathematically incapable of being a Game Over. Force False.
            turn_data["is_game_over"] = False
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
                
            # FIX: Explicitly omit inventory data from the Epilogue
            turn_data["is_game_over"] = True
            return turn_data

        # --- THE STORY SEED INTERCEPTOR (TURN 1) ---
        is_at_start = (len(self.history) == 0 or (len(self.history) == 1 and str(self.history[0].get("player_choice", "")).startswith("Start Chapter")))
        seed_file = self.adv_dir / "start_turn.json"

        if is_at_start and seed_file.exists():
            seed_data = load_json_safely(seed_file, "start_turn.json")
            if isinstance(seed_data, list) and len(seed_data) > 0:
                turn_data = seed_data[-1]
            elif isinstance(seed_data, dict):
                turn_data = seed_data
            else:
                turn_data = None
                
            if turn_data:
                turn_data["turn"] = self.get_next_turn_number()
                turn_data["player_choice"] = None
                # FIX: Protect against "dirty" seeds that were saved during a Game Over state
                turn_data["is_game_over"] = False
                if "chapter_goal_achieved" in turn_data:
                    turn_data["chapter_goal_achieved"] = False
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
        pc_exact = str(player_choice).strip()
        if pc_exact == "Restart Game": return self.restart_campaign()
        if pc_exact.startswith("Undo (Cheat Death"): return self.undo()
        if pc_exact in ["Quit", "Export Story", "Export Tragic Ending"]: return None
        
        # Handle Chapter Wizard overrides from Sandbox Engine
        handled, p_choice = self.process_custom_command(player_choice, "")
        if handled and p_choice:
            player_choice = p_choice
            
        log_event(self.adv_dir, f"Player Action [Turn {len(self.history)}]: {player_choice}")
        print(f"\n{Fore.CYAN}▶ Action Submitted: '{player_choice}'{Style.RESET_ALL}")

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

        # Auto Narrative Bridge background hook
        if ENGINE_CONFIG.get("auto_narrative_bridge", False) and len(self.history) >= 1:
            self._generate_bridge_for_latest_action()

        print(f"{Style.DIM}Generating turn...{Style.RESET_ALL}")
        
        bypass = self._check_startup_bypasses()
        if bypass:
            self._process_valid_turn(bypass)
            print(f"{Fore.GREEN}✔ Turn {bypass['turn']} generated successfully (Bypass).{Style.RESET_ALL}")
            return bypass

        turn_data = self._generate_turn()
        if turn_data:
            self._process_valid_turn(turn_data)
            print(f"{Fore.GREEN}✔ Turn {turn_data['turn']} generated successfully.{Style.RESET_ALL}")
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
        print(f"\n{Fore.CYAN}▶ Action: Destructive Redo{Style.RESET_ALL}")
        print(f"{Style.DIM}Generating alternative version...{Style.RESET_ALL}")
        
        # 1. Pop the old turn, but save its Narrative Bridge
        old_turn = self.history.pop()
        self.save_state()
        
        existing_bridge = old_turn.get("narrative_bridge", "")
        
        # INJECT TEMPORARILY: Seamlessly attach the bridge to the previous turn's text
        # The architecture doesn't even need to know it's a bridge; the AI just reads it as story context.
        if existing_bridge and existing_bridge not in ["[OK]", "[FAILED]"] and self.history:
            original_story = self.history[-1].get("story_text", "")
            self.history[-1]["story_text"] = f"{original_story} {existing_bridge}"
        
        # 2. Generate the new turn (runs the full standard creative pipeline at 0.8 Temp)
        turn_data = self._generate_turn()
        
        # RESTORE: Clean up the temporary injection so it doesn't pollute the save file
        if existing_bridge and existing_bridge not in ["[OK]", "[FAILED]"] and self.history:
            self.history[-1]["story_text"] = original_story
            
        # 3. Restore the bridge to the new JSON object
        if turn_data: 
            if existing_bridge:
                turn_data["narrative_bridge"] = existing_bridge
            self._process_valid_turn(turn_data)
            print(f"{Fore.GREEN}✔ Alternative Turn {turn_data['turn']} generated successfully.{Style.RESET_ALL}")
        
        return turn_data

    def redo_choices(self, turn_idx=None):
        """Endpoint: Keeps the story prose but generates a new set of choices."""
        from logger import log_event
        if len(self.history) == 0: return None
        
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        log_event(self.adv_dir, f"Command: REDO CHOICES (Turn {idx})")
        print(f"\n{Fore.CYAN}▶ Action: Reroll Choices (Turn {idx}){Style.RESET_ALL}")
        print(f"{Style.DIM}Generating new choices...{Style.RESET_ALL}")
        
        self.backup_turn = self.history[idx].copy()
        self.backup_turn_idx = idx
        
        prompt = PROMPTS.get("USER_REDO_CHOICES", "").replace("{original_json}", json.dumps(self.backup_turn, indent=2))
        self.active_fix = prompt
        self.is_fix_mode = True
        
        turn_data = self._generate_turn()
        
        if turn_data:
            turn_data["story_text"] = self.backup_turn.get("story_text", "")
            turn_data["location"] = self.backup_turn.get("location", "Unknown")
            turn_data["pov_character"] = self.backup_turn.get("pov_character", "Unknown")
            if self.track_inventory:
                turn_data["inventory_and_state"] = self.backup_turn.get("inventory_and_state", "")
                
            turn_data["player_choice"] = self.backup_turn.get("player_choice")
            if "narrative_bridge" in self.backup_turn: turn_data["narrative_bridge"] = self.backup_turn["narrative_bridge"]
                
            self.active_fix = None
            self.is_fix_mode = False
            self.backup_turn = None
            delattr(self, 'backup_turn_idx')
            
            # Overwrite in place
            self.history[idx] = turn_data
            self.save_state()
                
            print(f"{Fore.GREEN}✔ New choices for Turn {idx} ready.{Style.RESET_ALL}")
            return turn_data
            
        self.active_fix = None
        self.is_fix_mode = False
        self.backup_turn = None
        delattr(self, 'backup_turn_idx')
        return None
        
    def request_expansion(self, turn_idx=None):
        """Endpoint: Generates a context-aware descriptive expansion DRAFT of the current turn."""
        if len(self.history) == 0: return None
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        print(f"\n{Fore.CYAN}▶ Action: Expand Prose (Turn {idx}){Style.RESET_ALL}")
        print(f"{Style.DIM}Expanding turn prose...{Style.RESET_ALL}")
        
        self.backup_turn = self.history[idx].copy()
        self.backup_turn_idx = idx 
        
        world_info = {
            "title": self.setup_data.get("title"),
            "tone": self.setup_data.get("tone"),
            "lore": self.setup_data.get("lore_and_rules"),
            "protagonist": self.setup_data.get("main_character")
        }
        
        prev_story = "This is the first turn of the adventure."
        if idx > 0:
            prev_turn = self.history[idx - 1]
            prev_story = f"PREVIOUS SCENE: {prev_turn.get('story_text', '')}\nACTION TAKEN: {prev_turn.get('player_choice', '')}"

        prompt = PROMPTS.get("USER_EXPAND", "")
        prompt = prompt.replace("{world_info}", json.dumps(world_info, indent=2))
        prompt = prompt.replace("{prev_story}", prev_story)
        prompt = prompt.replace("{original_json}", json.dumps(self.backup_turn, indent=2))
        
        self.active_fix = prompt
        self.is_fix_mode = True
        
        draft = self._generate_turn()
        if draft: 
            self._apply_draft_inheritance(draft)
            print(f"{Fore.GREEN}✔ Turn {idx} expansion draft ready.{Style.RESET_ALL}")
        return draft

    def request_condense(self, turn_idx=None):
        """Endpoint: Generates a shortened DRAFT. Supports historical turns."""
        if len(self.history) == 0: return None
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        
        self.backup_turn = self.history[idx].copy()
        self.backup_turn_idx = idx
        print(f"\n{Fore.CYAN}▶ Action: Condense Prose (Turn {idx}){Style.RESET_ALL}")
        print(f"{Style.DIM}Condensing turn prose...{Style.RESET_ALL}")
        
        prompt = PROMPTS.get("USER_CONDENSE", "").replace("{original_json}", json.dumps(self.backup_turn, indent=2))
        self.active_fix = prompt
        self.is_fix_mode = True
        
        draft = self._generate_turn()
        if draft: 
            self._apply_draft_inheritance(draft)
            print(f"{Fore.GREEN}✔ Turn {idx} condense draft ready.{Style.RESET_ALL}")
        return draft

    def request_polish(self, turn_idx=None):
        """Endpoint: Generates a polished DRAFT. Supports historical turns."""
        if len(self.history) == 0: return None
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        
        self.backup_turn = self.history[idx].copy()
        self.backup_turn_idx = idx
        print(f"\n{Fore.CYAN}▶ Action: Polish Prose (Turn {idx}){Style.RESET_ALL}")
        print(f"{Style.DIM}Polishing turn prose...{Style.RESET_ALL}")
        
        prompt = PROMPTS.get("USER_POLISH", "").replace("{original_json}", json.dumps(self.backup_turn, indent=2))
        self.active_fix = prompt
        self.is_fix_mode = True
        
        draft = self._generate_turn()
        if draft: 
            self._apply_draft_inheritance(draft)
            print(f"{Fore.GREEN}✔ Turn {idx} polish draft ready.{Style.RESET_ALL}")
        return draft

    def request_fix(self, instruction, turn_idx=None, temp_override=None):
        """Endpoint: Generates a targeted-edit DRAFT based on user instruction. Accepts optional temperature."""
        if len(self.history) == 0: return None
        idx = turn_idx if turn_idx is not None else len(self.history) - 1
        
        print(f"\n{Fore.CYAN}▶ Action: Director Fix (Turn {idx}){Style.RESET_ALL}")
        print(f"{Style.DIM}Applying fix: '{instruction[:30]}...'{Style.RESET_ALL}")
        self.backup_turn = self.history[idx].copy()
        self.backup_turn_idx = idx
        
        fix_prompt = PROMPTS.get("USER_FIX", "")
        fix_prompt = fix_prompt.replace("{instruction}", instruction)
        self.active_fix = fix_prompt.replace("{original_json}", json.dumps(self.backup_turn, indent=2))
        self.is_fix_mode = True
        self._temp_override = temp_override # Pass to generation loop
        
        draft = self._generate_turn()
        if draft: 
            self._apply_draft_inheritance(draft)
            print(f"{Fore.GREEN}✔ Turn {idx} fix draft ready.{Style.RESET_ALL}")
            
        if hasattr(self, "_temp_override"): delattr(self, "_temp_override")
        return draft

    def _apply_draft_inheritance(self, draft_turn):
        """STRICT INHERITANCE: Protects structural JSON metadata from AI hallucinations."""
        if self.backup_turn:
            draft_turn["choices"] = self.backup_turn.get("choices", [])
            draft_turn["location"] = self.backup_turn.get("location", "Unknown")
            draft_turn["pov_character"] = self.backup_turn.get("pov_character", "Unknown")
            if self.track_inventory: draft_turn["inventory_and_state"] = self.backup_turn.get("inventory_and_state", "")
            
    def request_reroll_draft(self):
        """Endpoint: Generates a new draft based on the currently active fix mode, WITHOUT popping history."""
        if not self.backup_turn: return None
        print(f"{Style.DIM}Rerolling draft...{Style.RESET_ALL}")
        draft = self._generate_turn()
        if draft: self._apply_draft_inheritance(draft)
        return draft

    def commit_draft(self, draft_turn):
        """Endpoint: Accepts the drafted turn and permanently saves it to history."""
        idx = getattr(self, 'backup_turn_idx', len(self.history)-1)
        
        # Run mechanical logic (goals/chapter tracking) on the draft
        self.post_generation_hook(draft_turn)
        
        # Inherit the historical player choice
        draft_turn["player_choice"] = self.history[idx].get("player_choice")
        if "narrative_bridge" in self.history[idx]: draft_turn["narrative_bridge"] = self.history[idx]["narrative_bridge"]
        
        # Overwrite in place
        self.history[idx] = draft_turn
        self.save_state()
        
        self.active_fix = None
        self.is_fix_mode = False
        self.backup_turn = None
        delattr(self, 'backup_turn_idx')
        print(f"{Fore.GREEN}✔ Draft accepted and committed to history.{Style.RESET_ALL}")
        return draft_turn

    def cancel_draft(self):
        """Endpoint: Discards the draft and restores the original turn state."""
        self.active_fix = None
        self.is_fix_mode = False
        self.backup_turn = None
        if hasattr(self, 'backup_turn_idx'): delattr(self, 'backup_turn_idx')
        print(f"{Fore.YELLOW}✖ Draft discarded. Original turn retained.{Style.RESET_ALL}")
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
        dynamic_max_tokens = ENGINE_CONFIG.get("max_tokens", 2000)
        
        if self.active_fix and self.is_fix_mode:
            editor_sys = self.system_prompt_text + "\n\n" + PROMPTS.get("SYS_EDITOR", "")
            base_messages = [
                {"role": "system", "content": editor_sys},
                {"role": "user", "content": self.active_fix}
            ]
            
            # DYNAMIC TOKEN SCALING FOR EDITORS
            if self.backup_turn:
                orig_text = self.backup_turn.get("story_text", "")
                word_count = len(orig_text.split())
                estimated_input_tokens = int(word_count * 1.5)
                
                if "CONDENSE" in self.active_fix:
                    # Condensing strictly reduces text
                    dynamic_max_tokens = max(150, estimated_input_tokens)
                elif "POLISH" in self.active_fix or "FIX" in self.active_fix:
                    # Polish/Fix keeps roughly the same length + small buffer
                    dynamic_max_tokens = max(300, estimated_input_tokens + 250)
                elif "EXPAND" in self.active_fix:
                    # Expand needs massive headroom
                    dynamic_max_tokens = max(500, estimated_input_tokens + 800)
                    
                # Never exceed the user's global hard cap
                global_cap = ENGINE_CONFIG.get("max_tokens", 2000)
                dynamic_max_tokens = min(global_cap, dynamic_max_tokens)
                
        else:
            base_messages = self.build_messages(self.get_next_turn_number())

        prev_turn_obj = self.history[-1] if self.history else None
        turn_data = None
        err = None

        # Check if the Director explicitly passed a temp override
        final_temp = getattr(self, "_temp_override", None)

        for attempt in range(max_retries):
        
            # --- THE FEEDBACK LOOP ---
            # Help the AI by telling it exactly what JSON syntax it broke
            active_messages = base_messages.copy()
            if attempt > 0 and err:
                feedback = PROMPTS.get("FEEDBACK_INVALID_JSON", "").replace("{error}", str(err))
                if "Expecting" in str(err) or "control character" in str(err).lower():
                    feedback += PROMPTS.get("FEEDBACK_CONTROL_CHAR", "")
                active_messages.append({"role": "user", "content": f"{feedback} Please correct it."})

            inv_schema = self.setup_data.get("inventory_dictionary", {})
            turn_data, err, raw = get_llm_response(
                active_messages, attempt, self.adv_dir, prev_turn_obj, self.is_fix_mode, 
                self.is_campaign, self.track_inventory, self.can_die, self.is_test_mode, inv_schema,
                override_tokens=dynamic_max_tokens, override_temp=final_temp
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
        polish_prompt = PROMPTS.get("USER_AUTO_POLISH", "").replace("{original_json}", json.dumps(draft, indent=2))
        polish_sys = self.system_prompt_text + "\n\n" + PROMPTS.get("SYS_EDITOR", "")
        polish_msgs = [
            {"role": "system", "content": polish_sys},
            {"role": "user", "content": polish_prompt}
        ]
        
        for p_attempt in range(max_retries):
            inv_schema = self.setup_data.get("inventory_dictionary", {})
            polished_data, _, _ = get_llm_response(
                polish_msgs, p_attempt, self.adv_dir, prev_turn_obj, False, 
                self.is_campaign, self.track_inventory, self.can_die, self.is_test_mode, inv_schema
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
            if turn_data.get("turn", 0) > 0 and str(turn_data.get("is_game_over", False)).lower() == "true":
                prev_choice = self.history[-1].get("player_choice", "") if self.history else ""
                if prev_choice == "Conclude the Story":
                    print(f"\n{Fore.GREEN}[System: CAMPAIGN COMPLETE! Victory achieved.]{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.RED}[System: GAME OVER! The protagonist has met their end.]{Style.RESET_ALL}")
                
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
        
        # --- AUTO-DECAY SCANNER ---
        # Catch entities mentioned in the AI's prose, bridge, and location strings immediately
        combined_text = f"{turn_data.get('story_text', '')} {turn_data.get('location', '')} {turn_data.get('narrative_bridge', '')}"
        self._update_entity_visibility(turn_data["turn"], combined_text)
        
        self.save_state()

    def _update_entity_visibility(self, current_turn, text_to_scan):
        """Python text scanner that auto-archives entities not seen in 40 turns, and revives them if mentioned."""
        import re
        threshold = ENGINE_CONFIG.get("memory_decay_threshold", 40)
        text_lower = text_to_scan.lower()
        
        ledgers = ["character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"]
        aliases_map = self.memory.get("aliases", {})
        
        changed = False
        for l_type in ledgers:
            if l_type not in self.memory: continue
            
            l_aliases = aliases_map.get(l_type, {})
            reverse_aliases = {}
            for alias, master in l_aliases.items():
                reverse_aliases.setdefault(master, []).append(alias.lower())
                
            for entity_name, data in self.memory[l_type].items():
                if isinstance(data, list): continue 
                
                # Initialize safety baseline
                if "last_seen_turn" not in data:
                    data["last_seen_turn"] = current_turn
                    changed = True
                    
                search_terms = [entity_name.lower()] + reverse_aliases.get(entity_name, [])
                
                # Scan text using word boundaries to prevent partial matches (e.g., 'Al' inside 'Always')
                mentioned = False
                for term in search_terms:
                    if re.search(rf'\b{re.escape(term)}\b', text_lower):
                        mentioned = True
                        break
                        
                if mentioned:
                    data["last_seen_turn"] = current_turn
                    if data.get("state", "active") == "archived":
                        data["state"] = "active" # Auto-Revive
                        changed = True
                        
                # Process Decay (Ignore pinned entities)
                last_seen = data.get("last_seen_turn", current_turn)
                if data.get("state", "active") == "active":
                    if (current_turn - last_seen) >= threshold:
                        data["state"] = "archived" # Auto-Archive
                        changed = True
                        
        if changed:
            self.save_state()

    def _resync_all_visibility(self):
        """Pure Python full-history sweep to definitively guarantee accurate last_seen_turn and states."""
        import re
        threshold = ENGINE_CONFIG.get("memory_decay_threshold", 40)
        max_turn = len(self.history)
        if max_turn == 0: return

        ledgers = ["character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"]
        aliases_map = self.memory.get("aliases", {})
        
        # 1. Pre-compile regex patterns for lightning-fast scanning
        search_dict = {}
        for l_type in ledgers:
            search_dict[l_type] = {}
            if l_type not in self.memory: continue
            
            l_aliases = aliases_map.get(l_type, {})
            reverse_aliases = {}
            for alias, master in l_aliases.items():
                reverse_aliases.setdefault(master, []).append(alias.lower())
                
            for entity_name, data in self.memory[l_type].items():
                if isinstance(data, list): continue
                terms = [entity_name.lower()] + reverse_aliases.get(entity_name, [])
                patterns = [re.compile(rf'\b{re.escape(t)}\b') for t in terms]
                search_dict[l_type][entity_name] = patterns
                
                # Default to 0 before the sweep
                if "last_seen_turn" not in data:
                    data["last_seen_turn"] = 0

        # 2. Sweep forward through ALL history
        for turn in self.history:
            t_num = turn.get("turn", 0)
            text_to_scan = f"{turn.get('story_text', '')} {turn.get('location', '')} {turn.get('narrative_bridge', '')}".lower()
            
            for l_type, entities in search_dict.items():
                for entity_name, patterns in entities.items():
                    for p in patterns:
                        if p.search(text_to_scan):
                            self.memory[l_type][entity_name]["last_seen_turn"] = t_num
                            break

        # 3. Apply decay states based on true last_seen_turn
        changed = False
        for l_type in ledgers:
            if l_type not in self.memory: continue
            for entity_name, data in self.memory[l_type].items():
                if isinstance(data, list): continue
                last_seen = data.get("last_seen_turn", 0)
                current_state = data.get("state", "active")
                
                if current_state != "pinned":
                    new_state = "archived" if (max_turn - last_seen) >= threshold else "active"
                    if current_state != new_state:
                        data["state"] = new_state
                        changed = True

        if changed:
            self.save_state()
            
    def _smart_merge_traits(self, existing_traits, new_traits):
        """
        Intelligently merges new AI-generated traits into an existing dictionary.
        Actively forces list-style data into Plural keys (Friend -> Friends, Ally -> Allies)
        and seamlessly upgrades existing singular keys when collisions occur.
        """
        if not isinstance(new_traits, dict) or not isinstance(existing_traits, dict): return
        
        list_keywords = ["relation", "friend", "quirk", "faction", "title", "affiliation", "role", "skill", "abilit", "allie", "ally", "enemie", "enemy"]

        for new_k, new_v in new_traits.items():
            target_k = str(new_k).strip()
            nk_l = target_k.lower()
            
            # 1. Detect collisions with existing keys
            matched_ek = None
            for ek in list(existing_traits.keys()): # Cast to list so we can mutate the dict safely
                ek_l = str(ek).lower().strip()
                if (nk_l == ek_l) or \
                   (nk_l == ek_l + "s") or (ek_l == nk_l + "s") or \
                   (nk_l.endswith("ies") and nk_l[:-3] + "y" == ek_l) or \
                   (ek_l.endswith("ies") and ek_l[:-3] + "y" == nk_l):
                    matched_ek = ek
                    break
            
            # 2. Force the Plural Key
            if matched_ek:
                ek_l = matched_ek.lower()
                # If the new key is plural but the old one is singular, UPGRADE the old one
                if (nk_l.endswith('s') and not ek_l.endswith('s')) or \
                   (nk_l.endswith('ies') and ek_l.endswith('y')):
                    existing_traits[target_k] = existing_traits.pop(matched_ek)
                else:
                    # The existing one is already plural, or neither are. Keep the existing one.
                    target_k = matched_ek
            else:
                # No collision. If it's a known list-category, auto-pluralize it immediately.
                if any(w in nk_l for w in list_keywords):
                    if nk_l.endswith("y"): target_k = target_k[:-1] + "ies"
                    elif not nk_l.endswith("s"): target_k = target_k + "s"

            # 3. Merge the value safely (Zero Data Loss)
            clean_v = str(new_v).strip()
            if target_k in existing_traits:
                exist_v = str(existing_traits[target_k]).strip()
                
                # Only merge if it's genuinely new information
                if clean_v.lower() not in exist_v.lower() and exist_v.lower() not in clean_v.lower():
                    if any(w in target_k.lower() for w in list_keywords):
                        existing_traits[target_k] = exist_v + ", " + clean_v
                    else:
                        # Combine distinct info instead of overwriting (e.g., "Tall | Wears a hat")
                        existing_traits[target_k] = exist_v + ", " + clean_v
            else:
                existing_traits[target_k] = clean_v

    def _trigger_memory_compilation(self, progress_callback=None, completion_callback=None):
        """
        Triggers the Master Compiler in the background when the turn threshold is met.
        Strictly overrides mode to 'missing' but respects the user's Auto-Reconcile preference.
        """
        chunk_size = ENGINE_CONFIG.get("context_window", 15)
        if not self.history: return False
        
        current_turn = self.history[-1]["turn"]
        active_chap = next((c for c in reversed(self.chapters) if c.get("start_turn") is not None and c.get("start_turn") <= current_turn), self.chapters[0])
        
        c_start = active_chap.get("start_turn")
        if not c_start: return
        
        # Calculate active turns strictly WITHIN the current chapter
        turns_active = current_turn - c_start + 1
        
        # Only trigger live if we hit an exact multiple of the chunk size within THIS chapter
        if turns_active == 0 or turns_active % chunk_size != 0: return False
            
        print(f"{Style.DIM}Triggering Long-Term Memory compilation (Turns {current_turn-chunk_size+1}-{current_turn})...{Style.RESET_ALL}")
        
        # Fetch the user's preference for Auto-Reconciliation
        auto_recon = self.setup_data.get("auto_reconcile", True)
        
        # Delegate directly to the Master Compiler (It inherently runs asynchronously)
        self.compile_missing_memories(
            compile_mode="missing", 
            run_reconciliation=auto_recon,
            progress_callback=progress_callback,
            completion_callback=completion_callback
        )
        return True

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
            
            
    def compile_missing_memories(self, compile_mode="missing", run_reconciliation=True, progress_callback=None, completion_callback=None):
        """
        Background worker that retroactively generates memory chunks.
        compile_mode: "base" (only setup.json), "missing" (only un-summarized chunks), "force" (re-read all chunks for entities).
        """
        def worker():
            from config import ENGINE_CONFIG
            from api import TomeWeaverAPI
            import math
            
            force_entities_only = (compile_mode == "force")
            
            # --- PHASE 0: AUTO-SEEDER (Base Lore) ---
            # Run if memory is completely empty, OR if the user explicitly requested it
            is_empty = not self.memory.get("character_ledger") and not self.memory.get("location_ledger") and not self.memory.get("artifact_ledger")
            
            if is_empty or compile_mode == "base":
                if progress_callback: progress_callback("Seeding", "Base Lore")
                
                # We dynamically inject Prologue text and Start Turn seeds into the setup data for parsing
                seed_data = self.setup_data.copy()
                if self.prologue_content: seed_data["prologue_text"] = self.prologue_content
                
                start_file = self.adv_dir / "start_turn.json"
                if start_file.exists():
                    from config import load_json_safely
                    start_data = load_json_safely(start_file, "start_turn.json")
                    if isinstance(start_data, dict): seed_data["start_turn"] = start_data.get("story_text", "")
                    
                track_facs = self.setup_data.get("track_factions", False)
                succ_seed, seed_res = TomeWeaverAPI.seed_initial_memory(seed_data, track_factions=track_facs)
                
                if succ_seed and isinstance(seed_res, dict):
                    def merge_seeds(extracted_dict, ledger_key):
                        if not isinstance(extracted_dict, dict): return
                        for k, v in extracted_dict.items():
                            if k not in self.memory[ledger_key]: 
                                self.memory[ledger_key][k] = {"characteristics": {}, "ledger": []}
                            if isinstance(v, dict):
                                traits = v.get("traits", {})
                                if isinstance(traits, dict) and traits:
                                    self._smart_merge_traits(self.memory[ledger_key][k]["characteristics"], traits)
                                    
                    merge_seeds(seed_res.get("Characters", {}), "character_ledger")
                    merge_seeds(seed_res.get("Locations", {}), "location_ledger")
                    merge_seeds(seed_res.get("Artifacts", {}), "artifact_ledger")
                    if track_facs: merge_seeds(seed_res.get("Factions", {}), "faction_ledger")
                    self.save_state()
                    
            if compile_mode == "base":
                if completion_callback: completion_callback(True, "Base Lore extraction complete! (No history was scanned).")
                return
                
            # --- PHASE 1.5: CONTINUITY VERIFICATION ---
            verification_report = ""
            if compile_mode == "verify":
                if progress_callback: progress_callback("Verifying", "Checking logic and continuity")
                
                # Gather Plot Summaries
                plot_ctx = "\n".join([f"Ch {p.get('chapter_number')}: {p.get('summary', '')}" for p in self.memory.get("plot_ledger", [])])
                if not plot_ctx: plot_ctx = "No plot summaries exist yet."
                
                # Gather Lore Bible
                def format_known(ledger):
                    res = ""
                    for k, data in self.memory.get(ledger, {}).items():
                        if isinstance(data, list): res += f"- {k}: {', '.join(data)}\n"
                        else:
                            t = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                            e = " ".join(data.get("ledger", []))
                            res += f"- {k} (Traits: {t}): {e}\n"
                    return res
                    
                track_facs = self.setup_data.get("track_factions", False)
                lore_ctx = "CHARACTERS:\n" + format_known("character_ledger")
                lore_ctx += "\nLOCATIONS:\n" + format_known("location_ledger")
                lore_ctx += "\nARTIFACTS:\n" + format_known("artifact_ledger")
                if track_facs: lore_ctx += "\nFACTIONS:\n" + format_known("faction_ledger")
                
                from api import TomeWeaverAPI
                succ_ver, report = TomeWeaverAPI.verify_memory_integrity(plot_ctx, lore_ctx)
                verification_report = report if succ_ver else "Verification failed to complete."
                
                # We do NOT return yet. We allow it to fall through to Phase 2 (Reconciliation) 
                # so the user's checkbox for Auto-Reconcile is honored.
            
            chunk_size = ENGINE_CONFIG.get("context_window", 15)
            target_chunks = []
            
            # --- PHASE 1: MATHEMATICAL CHUNKING (Chapter-Aware) ---
            for c in self.chapters:
                c_start = c.get("start_turn")
                if not c_start: continue
                
                c_end = c.get("end_turn")
                is_finished = c_end is not None
                if not is_finished: c_end = len(self.history)
                    
                total_turns = c_end - c_start + 1
                if total_turns <= 0: continue
                
                c_num = c.get("chapter_number", 1)
                c_title = c.get("title", "Chapter")
                
                if is_finished:
                    # User Math: Split completed chapters into perfectly equal parts
                    num_chunks = math.ceil(total_turns / chunk_size)
                    base_len = total_turns // num_chunks
                    rem = total_turns % num_chunks
                    
                    curr = c_start
                    for i in range(num_chunks):
                        length = base_len + 1 if i < rem else base_len
                        target_chunks.append({"start": curr, "end": curr + length - 1, "chap_num": c_num, "chap_title": c_title})
                        curr += length
                        
                    # Cleanup: Delete mismatched legacy summaries for this chapter so they don't duplicate
                    if not force_entities_only:
                        valid_bounds = [(tc["start"], tc["end"]) for tc in target_chunks if tc["chap_num"] == c_num]
                        self.memory["plot_ledger"] = [
                            p for p in self.memory.get("plot_ledger", [])
                            if not (p.get("chapter_number") == c_num and (p.get("start_turn"), p.get("end_turn")) not in valid_bounds)
                        ]
                else:
                    # Ongoing Chapter: Standard strides so we don't accidentally summarize the active, unfinished chunk
                    curr = c_start
                    while (c_end - curr + 1) >= chunk_size:
                        target_chunks.append({"start": curr, "end": curr + chunk_size - 1, "chap_num": c_num, "chap_title": c_title})
                        curr += chunk_size
                        
            # Determine which chunks actually need processing
            existing_plots = [(p.get("start_turn"), p.get("end_turn")) for p in self.memory.get("plot_ledger", [])]
            
            if force_entities_only:
                chunks_to_process = target_chunks
            elif compile_mode == "verify":
                chunks_to_process = [] # Verify skips historical raw-turn reading entirely
            else:
                chunks_to_process = [tc for tc in target_chunks if (tc["start"], tc["end"]) not in existing_plots]
                
            # Determine which chapters need high-level condensation
            condensed_nums = [c.get("chapter_number") for c in self.memory.get("chapter_ledger", [])]
            chapters_to_condense = [chap for chap in self.chapters if chap.get("end_turn") is not None and chap.get("chapter_number") not in condensed_nums]
                
            # Only abort if absolutely nothing needs to be done
            if not chunks_to_process and not chapters_to_condense and compile_mode != "verify" and not run_reconciliation:
                if completion_callback: completion_callback(True, "All memories are already up to date!")
                return
                
            for i, tc in enumerate(chunks_to_process):
                if progress_callback: progress_callback(i + 1, len(chunks_to_process))
                
                # Fetch turns safely using absolute turn values, completely ignoring list indices
                chunk = [t for t in self.history if tc["start"] <= t.get("turn", 0) <= tc["end"]]
                
                if not chunk: continue
                
                turns_text = ""
                for t in chunk:
                    turns_text += f"Turn {t['turn']} [Loc: {t.get('location', '')}]: {t.get('story_text', '')}\nAction: {t.get('player_choice', '')}\n\n"
                    
                chap_title = tc["chap_title"]
                chap_num = tc["chap_num"]
                
                # 1. Plot Summary (Skip if we are only backfilling entities)
                succ_plot = False
                if not force_entities_only:
                    succ_plot, plot_res = TomeWeaverAPI.generate_plot_summary(turns_text, chunk[0]["turn"], chunk[-1]["turn"], self.adv_dir)
                    if succ_plot:
                            self.memory.setdefault("plot_ledger", []).append({
                                "chapter_title": chap_title,
                                "chapter_number": chap_num,
                                "start_turn": chunk[0]["turn"],
                                "end_turn": chunk[-1]["turn"],
                                "summary": plot_res
                            })
                    
                # 2. Entity Status Extract (Auto-Detects New Entities & Traits)
                def format_known(ledger):
                    res = ""
                    for k, data in self.memory.get(ledger, {}).items():
                        if isinstance(data, list): res += f"- {k}: {', '.join(data)}\n"
                        else:
                            t = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                            e = " ".join(data.get("ledger", []))
                            res += f"- {k} (Traits: {t}): {e}\n"
                    return res
                    
                track_facs = self.setup_data.get("track_factions", False)
                succ_ent, ent_res = TomeWeaverAPI.extract_entity_updates(
                    turns_text, 
                    format_known("character_ledger"), 
                    format_known("location_ledger"),
                    format_known("artifact_ledger"),
                    format_known("faction_ledger") if track_facs else "",
                    track_factions=track_facs
                )
                if succ_ent and isinstance(ent_res, dict):
                    def merge_entities(extracted_dict, ledger_key):
                        if not isinstance(extracted_dict, dict): return
                        for k, v in extracted_dict.items():
                            
                            # THE ALIAS INTERCEPTOR: If 'k' is a known duplicate, redirect all data to the Master Entity
                            actual_k = self.memory.get("aliases", {}).get(ledger_key, {}).get(k, k)
                            
                            # Auto-migrate old list format to complex dict format seamlessly
                            if actual_k not in self.memory[ledger_key]: 
                                self.memory[ledger_key][actual_k] = {"characteristics": {}, "ledger": [], "author_notes": ""}
                            elif isinstance(self.memory[ledger_key][actual_k], list):
                                self.memory[ledger_key][actual_k] = {"characteristics": {}, "ledger": self.memory[ledger_key][actual_k], "author_notes": ""}
                                
                            if isinstance(v, dict):
                                event = v.get("event")
                                traits = v.get("traits", {})
                                if event and str(event).lower() != "null": 
                                    self.memory[ledger_key][actual_k]["ledger"].append(str(event))
                                if isinstance(traits, dict) and traits:
                                    self._smart_merge_traits(self.memory[ledger_key][actual_k]["characteristics"], traits)
                            elif isinstance(v, str):
                                self.memory[ledger_key][actual_k]["ledger"].append(v) # Fallback if AI hallucinates string
                                
                    merge_entities(ent_res.get("Locations", {}), "location_ledger")
                    merge_entities(ent_res.get("Artifacts", {}), "artifact_ledger")
                    if track_facs: merge_entities(ent_res.get("Factions", {}), "faction_ledger")
                        
                if succ_plot or succ_ent:
                    self.save_state()
                
            # --- PHASE 1.8: CONDENSE COMPLETED CHAPTERS ---
            for chap in chapters_to_condense:
                c_num = chap.get("chapter_number")
                chap_chunks = [p for p in self.memory.get("plot_ledger", []) if p.get("chapter_number") == c_num]
                if chap_chunks:
                    if progress_callback: progress_callback("Condensing", f"Summarizing Chapter {c_num}")
                    combined_text = "\n".join([f"Part {i+1}: {p.get('summary', '')}" for i, p in enumerate(chap_chunks)])
                    succ_chap, chap_res = TomeWeaverAPI.generate_chapter_summary(combined_text)
                    if succ_chap:
                        self.memory.setdefault("chapter_ledger", []).append({
                            "chapter_number": c_num,
                            "chapter_title": chap.get("title", "Chapter"),
                            "summary": chap_res
                        })
                        self.save_state()
                    
            # --- PHASE 2: RECONCILIATION (The AI Janitor) ---
            if run_reconciliation:
                if progress_callback: progress_callback("Reconciling", "Merging duplicates")
                
                # Check all 4 ledgers independently
                for l_type in ["character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"]:
                    if not self.memory.get(l_type): continue
                    
                    # Compress data into a lightweight string to save tokens
                    ctx = ""
                    for k, data in self.memory[l_type].items():
                        traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                        ctx += f"- {k} | Traits: {traits}\n"
                        
                    succ_recon, recon_res = TomeWeaverAPI.reconcile_aliases(ctx)
                    if succ_recon and isinstance(recon_res, dict):
                        for alias, master in recon_res.items():
                            # Safety check: Ensure both exist and aren't literally the same string
                            if alias in self.memory[l_type] and master in self.memory[l_type] and alias != master:
                                m_data = self.memory[l_type][master]
                                s_data = self.memory[l_type][alias]
                                
                                # Perform the merge using our Zero Data Loss utility
                                self._smart_merge_traits(m_data["characteristics"], s_data.get("characteristics", {}))
                                m_data["ledger"].extend(s_data.get("ledger", []))
                                
                                # Log the alias and delete the duplicate
                                self.memory.setdefault("aliases", {}).setdefault(l_type, {})[alias] = master
                                del self.memory[l_type][alias]
                                
                self.save_state()
                
            # --- PHASE 3: MASTER VISIBILITY SWEEP ---
            # Now that all entities are extracted and merged, do a lightning-fast 
            # pure Python sweep of the entire history.json to perfectly sync last_seen_turn and states.
            if progress_callback: progress_callback("Syncing", "Recalculating Last Seen timestamps")
            self._resync_all_visibility()
                    
            if completion_callback:
                if compile_mode == "verify":
                    completion_callback(True, verification_report)
                else:
                    completion_callback(True, f"Historical memory compilation complete. Processed {len(chunks_to_process)} chunks.")
            
        import threading
        threading.Thread(target=worker, daemon=True).start()