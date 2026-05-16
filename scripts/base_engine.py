"""
TomeWeaver: Base Engine Module
------------------------------
The foundational architecture for TomeWeaver. Handles the core game loop, 
state management, API error handling, and terminal rendering. Both Sandbox 
and Campaign engines inherit from this class.
"""

import os
import sys
import json
import time
import random
import re
from pathlib import Path
from colorama import Fore, Style

from config import load_json_safely, ENGINE_CONFIG, clear_screen
from llm import get_llm_response, generate_recap, generate_narrative_bridge

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
        
        # --- NEW: LOAD PROLOGUE/EPILOGUE TEXT FILES ---
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
        
        # History
        self.history_file = self.adv_dir / "history.json"
        
        prompt_file = self.adv_dir / "system_prompt.txt"
        with open(prompt_file, "r", encoding="utf-8") as f:
            self.system_prompt_text = f.read()

        # 1. Load History
        self.history = load_json_safely(self.history_file, "history.json") if self.history_file.exists() else []
        
        # 2. Load Chapters (CRITICAL: Must happen before any save_state triggers)
        self.chapters = self.load_chapters()
        
        # 3. Protect ledger integrity from manual edits
        if self.history:
            self.resync_master_clock()
        
        self.is_campaign = False
        self.allow_manual_chapters = True
        self.active_fix = None
        self.is_fix_mode = False
        self.track_inventory = self.setup_data.get("track_inventory", False)
        self.can_die = self.setup_data.get("can_die", False)
        self.allow_fix_command = self.setup_data.get("allow_cheats", True)
        
        self.is_test_mode = False

        # --- INSTANT NOVELIZER: STARTUP CATCH-UP ---
        # If enabled, automatically process any missing bridges on launch
        if ENGINE_CONFIG.get("instant_novelizer", False):
            self.novelize_history(silent=True)

    
    # ---------------------------------------------------------
    # FIX DUPLICATE OR OUT-OF-ORDER TURN NUMBERING
    # ---------------------------------------------------------

    def resync_master_clock(self):
        """
        Scans history and ensures all turn numbers are strictly sequential.
        Uses the first turn's number as the anchor to preserve user preference 
        (e.g., starting at 0 or 1) while fixing duplicates and gaps.
        """
        if not self.history:
            return

        try:
            start_num = int(self.history[0].get("turn", 0))
        except (ValueError, TypeError):
            start_num = 0
            
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


    # ---------------------------------------------------------
    # STATE & FILE MANAGEMENT
    # ---------------------------------------------------------

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
        if not self.history:
            return 0  # Start at Turn 0 for the Introduction
        
        last_turn = self.history[-1]
        try:
            # We cast to int just in case a previous bug put a string in the ledger
            return int(last_turn.get("turn", 0)) + 1
        except (ValueError, TypeError):
            # If the ledger is corrupted, we fallback to length as a last resort
            return len(self.history)


    # ---------------------------------------------------------
    # NARRATIVE & UTILITY COMMANDS
    # ---------------------------------------------------------

    def print_help_menu(self):
        """
        Prints the interactive command menu to the terminal.
        Dynamically shows or hides commands based on the active engine configuration.
        """
        print(f"\n{Fore.CYAN}--- COMMAND MENU ---")
        print(f"{Fore.YELLOW}[Custom Action]{Fore.WHITE}: Type a custom action directly into the prompt!")
        if self.allow_manual_chapters:
            print(f"{Fore.YELLOW}chapter      {Fore.WHITE}: Opens Wizard to transition to a new Chapter.")
        print(f"{Fore.YELLOW}export       {Fore.WHITE}: Export the story to TXT, MD, or HTML.")
        print(f"{Fore.YELLOW}novelize     {Fore.WHITE}: Manually weaves player choices into seamless prose.")
        print(f"{Fore.YELLOW}clear        {Fore.WHITE}: Clears the screen and redraws the current turn.")
        print(f"{Fore.YELLOW}redo         {Fore.WHITE}: Rerolls the current turn completely.")
        print(f"{Fore.YELLOW}undo         {Fore.WHITE}: Goes back in time one turn.")
        if self.allow_fix_command:
            print(f"{Fore.YELLOW}fix: [reason]{Fore.WHITE}: Keeps current turn but edits it (e.g. 'fix: make it raining').")
        print(f"{Fore.YELLOW}recap/summary{Fore.WHITE}: Asks the AI to write a summary of the adventure.")
        print(f"{Fore.YELLOW}restart      {Fore.WHITE}: Wipes all progress and restarts the adventure.")
        print(f"{Fore.YELLOW}test         {Fore.WHITE}: Engages Autopilot mode to auto-select the best choice.")
        print(f"{Fore.CYAN}--------------------\n")


    def novelize_history(self, silent=False):
        """
        Iterates through history to find turns missing a narrative bridge.
        Calls the LLM to generate surgical patches for seamless prose.
        """
        if not silent:
            print(f"\n{Fore.CYAN}--- NOVELIZER: SEAMLESS PROSE GENERATION ---")
            print(f"{Style.DIM}Checking history for narrative gaps...{Style.RESET_ALL}")
        
        processed_count = 0
        ui_commands = ["Start Chapter:", "Conclude the Story", "Restart", "Export", "Undo", "Quit", "Cheat Death"]

        for i in range(1, len(self.history)):
            current_turn = self.history[i]
            prev_turn = self.history[i-1]
            action = prev_turn.get("player_choice")
            
            if "narrative_bridge" in current_turn or not action or any(ui in str(action) for ui in ui_commands):
                continue
            
            if not silent:
                print(f"Novelizing Turn {current_turn['turn']}...", end="\r")
            
            bridge_data = generate_narrative_bridge(prev_turn, action, current_turn)
            
            if bridge_data == "OK":
                current_turn["narrative_bridge"] = {}
            elif isinstance(bridge_data, dict):
                current_turn["narrative_bridge"] = bridge_data
                processed_count += 1
            
            self.save_state()

        if not silent and processed_count > 0:
            print(f"\n{Fore.GREEN}Success: {processed_count} new bridges generated.{Style.RESET_ALL}")
            time.sleep(1)
        elif not silent:
            print(f"\n{Fore.YELLOW}All turns are already novelized.{Style.RESET_ALL}")
            time.sleep(1)


    # ---------------------------------------------------------
    # ABSTRACT ENGINE HOOKS (Implemented by Subclasses)
    # ---------------------------------------------------------

    def build_messages(self, target_turn):
        """
        Constructs the LLM prompt payload.
        Must be implemented by the specific child class (Sandbox or Campaign).
        """
        raise NotImplementedError("Must be implemented by child class")


    def post_generation_hook(self, turn_data):
        """
        Allows child classes to inject specific logic (like chapter transitions 
        or goal checking) immediately after the LLM generates a valid turn.
        """
        pass 


    def process_custom_command(self, ui_lower, user_input):
        """
        Allows child classes to intercept and handle mode-specific user commands 
        (e.g., the Chapter Wizard in Sandbox mode).
        """
        return False, None
        
        
    # ---------------------------------------------------------
    # GAME ENGINE CORE LOOP
    # ---------------------------------------------------------
        
    def play(self):
        """
        The core Game Loop of TomeWeaver.
        Handles state management, LLM generation, API error fallbacks, 
        user input, and the rendering of the Terminal User Interface (TUI).
        """
        from logger import log_event
        clear_screen()
        print(f"{Fore.CYAN}Loading Adventure: {self.setup_data.get('title', 'Unknown')}...")
        
        # Load the maximum number of times the engine will attempt to get valid JSON from the AI
        max_retries = ENGINE_CONFIG.get("max_retries", 10)

        while True:
            # ---------------------------------------------------------
            # 1. STATE RESOLUTION & BYPASS LOGIC
            # ---------------------------------------------------------
            # Check if we need to generate a new turn, or if we are resuming 
            # a saved game where the last turn is waiting for player input.
            resuming_turn = False
            if self.history and self.history[-1].get("player_choice") is None:
                turn_data = self.history[-1]
                resuming_turn = True
            else:
                turn_data = None
            
            if not resuming_turn:
                # --- NARRATIVE BYPASS LOGIC (PROLOGUE & EPILOGUE) ---
                # Determine where we are in the overall story arc
                is_first_turn = (len(self.history) == 0)
                is_concluding = (len(self.history) > 0 and self.history[-1].get("player_choice") == "Conclude the Story")
                
                # Retrieve narrative styles from the 'narrative' object (Defaults to 'expand')
                narr_cfg = self.setup_data.get("narrative", {})
                p_style = narr_cfg.get("prologue", "expand").lower()
                e_style = narr_cfg.get("epilogue", "expand").lower()

                # --- PROLOGUE AS-IS BYPASS ---
                # Only triggers if style is 'as_is' and the file actually exists.
                # If style is 'none', this block is skipped, and the code proceeds to Turn 1.
                if is_first_turn and p_style == "as_is" and self.prologue_content:
                    first_chap = self.chapters[0]
                    turn_data = {
                        "story_text": self.prologue_content,
                        "pov_character": self.setup_data.get("main_character", "Protagonist"),
                        "location": self.setup_data.get("setting", "The Beginning"),
                        "input_type": "choice",
                        "choices": [f"Start Chapter 1: {first_chap['title']}"],
                        "text_prompt": None,
                        "turn": self.get_next_turn_number(), # Safely assigns Turn 0
                        "player_choice": None
                    }
                    # Inject mandatory schema keys to satisfy the engine's internal logic
                    if self.is_campaign:
                        turn_data["goal_progress"] = "Setting the scene."
                        turn_data["chapter_goal_achieved"] = False
                    if self.track_inventory:
                        turn_data["inventory_and_state"] = self.setup_data.get("starting_inventory", "Health: Good. Items: Starting Gear.")
                    if self.can_die:
                        turn_data["is_game_over"] = False

                # --- EPILOGUE AS-IS BYPASS ---
                # Only triggers if style is 'as_is' and the file actually exists.
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
                        turn_data["inventory_and_state"] = "Final State."
                    turn_data["is_game_over"] = True

                # --- THE STORY SEED INTERCEPTOR (TURN 1) ---
                # If turn_data is still None, we check if there is a hand-crafted start_turn.json
                # to load instead of calling the AI.
                if not turn_data:
                    is_at_start = (len(self.history) == 0 or (len(self.history) == 1 and str(self.history[0].get("player_choice", "")).startswith("Start Chapter")))
                    seed_file = self.adv_dir / "start_turn.json"

                    if is_at_start and seed_file.exists():
                        from config import load_json_safely
                        seed_data = load_json_safely(seed_file, "start_turn.json")
                        
                        # Handle case where user renamed history.json (a list) to start_turn.json
                        if isinstance(seed_data, list):
                            turn_data = seed_data[-1] if seed_data else None
                        else:
                            turn_data = seed_data
                            
                        if turn_data:
                            turn_data["turn"] = self.get_next_turn_number()
                            turn_data["player_choice"] = None

            # ---------------------------------------------------------
            # 2. THE GENERATION LOOP (LLM API CALLS)
            # ---------------------------------------------------------
            # If turn_data was not created by bypasses or seed, we must ask the AI to generate it.
            if not turn_data and not resuming_turn:
                # Provide UI feedback on what the engine is currently doing
                status_str = "Applying fix..." if self.is_fix_mode else "Generating Prologue..." if is_first_turn else "Generating Epilogue..." if is_concluding else "Generating turn..."
                print(f"{Style.DIM}{status_str}{Style.RESET_ALL}", end="\r")
                
                # Construct the massive prompt (System Rules + World Setup + Recent History)
                base_messages = self.build_messages(len(self.history) + 1)
                prev_story = next((t["story_text"] for t in reversed(self.history) if t.get("story_text")), None)

                err = None
                for attempt in range(max_retries):
                
                    # --- THE FEEDBACK LOOP ---
                    # If this isn't the first try, we help the AI by telling it exactly what syntax it broke
                    active_messages = base_messages.copy()
                    if attempt > 0 and err:
                        # Determine if it's a syntax error or a logic error
                        feedback = f"Your previous JSON was invalid. Error: {err}."
                        if "Expecting" in str(err) or "control character" in str(err).lower():
                            feedback += " CRITICAL: You used unescaped double-quotes or raw line breaks inside a JSON string. Use \\\" for dialogue and \\n for new lines. DO NOT press Enter inside a value. You understand JSON, ensure it is a valid JSON format!"
                        
                        active_messages.append({
                            "role": "user",
                            "content": f"{feedback} Please provide the corrected JSON."
                        })

                    # Dispatch the API request to the local or cloud LLM
                    turn_data, err, raw = get_llm_response(
                        active_messages, attempt, self.adv_dir, prev_story, self.is_fix_mode, 
                        self.is_campaign, self.track_inventory, self.can_die, self.is_test_mode
                    )
                    
                    # If we received valid, schema-compliant JSON, break out of the retry loop
                    if turn_data:
                        # --- THE INDESTRUCTIBLE STAMP ---
                        # Overwrite whatever turn number the AI hallucinated with the true sequential Master Clock
                        turn_data["turn"] = self.get_next_turn_number()
                        break 
                        
                    # --- THE API ERROR SUITE ---
                    # If the request failed, handle rate limits and server overloads gracefully
                    print(" " * 70, end="\r") # Clear the loading line
                    print(f"{Fore.RED}[!] Attempt {attempt+1} Failed: {err}")
                    
                    err_str = str(err).lower()
                    
                    # 1. Handle Rate Limits / Quotas (HTTP 429) - Common in cloud APIs like OpenRouter
                    if any(x in err_str for x in ["429", "quota", "too many requests"]):
                        delay = 15.0 
                        delay_match = re.search(r'retry in ([\d\.]+)s', err_str) or re.search(r"'retrydelay':\s*'(\d+)s'", err_str)
                        if delay_match:
                            try: delay = float(delay_match.group(1)) + 1.0 
                            except ValueError: pass
                        print(f"{Style.DIM}[API Limit] Backing off for {delay:.1f}s to respect limits...{Style.RESET_ALL}")
                        time.sleep(delay)
                    
                    # 2. Handle Server Overloads (HTTP 502, 503, 504) - Common when local models are swapping from RAM to VRAM
                    elif any(x in err_str for x in ["503", "502", "504", "unavailable", "high demand"]):
                        print(f"{Style.DIM}[Server Overloaded] Backing off for 10s to await recovery...{Style.RESET_ALL}")
                        time.sleep(10)
                    
                    # 3. Standard short wait for general failures
                    elif attempt < max_retries - 1:
                        time.sleep(1)
                
                # If we exhausted all 10 retries, crash gracefully
                if not turn_data:
                    print(f"{Fore.RED}Critical Error: LLM failed to produce valid JSON after {max_retries} attempts.")
                    log_event(self.adv_dir, "SYSTEM FAILURE: Max retries exceeded.")
                    break

            # ---------------------------------------------------------
            # 3. POST-GENERATION STATE PROCESSING
            # ---------------------------------------------------------
            # This must run for any NEW turn (Bypass, Seed, or LLM), but NOT when resuming
            if not resuming_turn and turn_data:
                # Let the specific Engine (Campaign or Sandbox) process goals and transitions
                self.post_generation_hook(turn_data)

                # Sandbox Chapter Logic: Inject the "Start Chapter" choice if a manual transition was triggered
                if not self.is_campaign:
                    pending_chap = next((c for c in self.chapters if c.get("start_turn") is None), None)
                    if pending_chap and turn_data.get("player_choice") is None and not turn_data.get("is_game_over"):
                        turn_data["choices"] = [f"Start Chapter: {pending_chap['title']}"]

                # Mortality/Victory Interceptor: Check if the AI determined the game is over
                if self.can_die and not is_concluding:
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

                # Reset edit flags and append the new, validated turn to the ledger
                self.active_fix = None
                self.is_fix_mode = False
                turn_data["player_choice"] = None 
                self.history.append(turn_data)
                self.save_state()

                # --- INSTANT NOVELIZER ---
                if ENGINE_CONFIG.get("instant_novelizer", False) and len(self.history) > 1:
                    if "narrative_bridge" not in turn_data:
                        prev_turn = self.history[-2]
                        action = prev_turn.get("player_choice")
                        ui_cmds = ["Start Chapter:", "Conclude the Story", "Restart", "Export", "Undo", "Quit", "Cheat Death"]
                        
                        if action and not any(ui in str(action) for ui in ui_cmds):
                            print(f"{Style.DIM}Weaving narrative bridge...{Style.RESET_ALL}", end="\r")
                            # Explicitly import the newly added LLM bridge generator
                            from llm import generate_narrative_bridge
                            bridge_data = generate_narrative_bridge(prev_turn, action, turn_data)
                            
                            if bridge_data == "OK":
                                turn_data["narrative_bridge"] = {}
                            elif isinstance(bridge_data, dict):
                                turn_data["narrative_bridge"] = bridge_data
                            self.save_state()

            # ---------------------------------------------------------
            # 4. RENDER TERMINAL USER INTERFACE (TUI)
            # ---------------------------------------------------------
            clear_screen()
            
            # Find the chapter metadata for the current turn
            target_turn = turn_data.get('turn', len(self.history))
            active_chap = next((c for c in reversed(self.chapters) if c.get("start_turn") is not None and c["start_turn"] <= target_turn), self.chapters[0])
            
            # Print Header
            print(f"{Fore.CYAN}=== Chapter {active_chap['chapter_number']}: {active_chap['title']} === {Style.DIM}[Turn {target_turn}]")
            print(f"{Fore.CYAN}" + "="*50)
            
            # Print Inventory / Physical State
            if self.track_inventory or turn_data.get('inventory_and_state'):
                inv_state = turn_data.get('inventory_and_state', 'Unknown')
                print(f"{Fore.YELLOW}[Status] {inv_state}\n")
                
            # Print Location and POV metadata
            print(f"{Fore.MAGENTA}[{turn_data['location']} | POV: {turn_data['pov_character']}]")
            
            # Print the actual AI Story Prose (translating literal \n to actual line breaks)
            display_text = turn_data['story_text'].replace("\\n", "\n")
            print(f"{Fore.WHITE}{display_text}\n")

            player_choice = ""
            action_cmd = None
            
            # Render the Interactive Elements
            print(f"{Style.DIM}(Type '?' for special commands, or type any custom action directly.){Style.RESET_ALL}")
            
            if turn_data["input_type"] == "choice" and turn_data["choices"]:
                # Render multiple choice buttons
                for idx, choice in enumerate(turn_data["choices"], 1):
                    if "Undo (Cheat Death" in str(choice):
                        print(f"{Fore.RED}{idx}. {choice}")
                    elif str(choice).startswith("Start Chapter:") or str(choice) == "Conclude the Story":
                        print(f"{Fore.MAGENTA}{idx}. {choice}")
                    else:
                        print(f"{Fore.GREEN}{idx}. {choice}")
            else:
                # Render custom text input prompt (e.g. for naming things or solving riddles)
                print(f"{Fore.GREEN}{turn_data.get('text_prompt', 'Enter text: ')}")

            # ---------------------------------------------------------
            # 5. INPUT HANDLING (AUTOPILOT / TEST MODE)
            # ---------------------------------------------------------
            if self.is_test_mode:
                print(f"\n{Fore.CYAN}[TEST MODE] Autopilot engaged... (Close window to abort){Style.RESET_ALL}")
                
                # In test mode, reveal the hidden AI goal reasoning
                prog = turn_data.get("goal_progress")
                if prog: print(f"{Fore.YELLOW}[Goal Progress]\n{prog}{Style.RESET_ALL}")
                
                time.sleep(2) 
                
                # Check if we have reached a hard-stop condition
                is_endgame = False
                meta_choices = ["Quit", "Export Story", "Restart Game", "Undo (Cheat Death and try a different action)", "Export Tragic Ending", "Conclude the Story"]
                if turn_data.get("choices"):
                    is_endgame = any(c in meta_choices for c in turn_data["choices"])
                
                if is_endgame:
                    print(f"{Fore.MAGENTA}Story conclusion or Game Over detected. Disabling Autopilot.{Style.RESET_ALL}")
                    self.is_test_mode = False
                else:
                    # Select the optimal "Golden Path" choice to blitz through the chapter logic
                    if turn_data["input_type"] == "choice" and turn_data["choices"]:
                        player_choice = turn_data["choices"][0]
                    else:
                        player_choice = "I cautiously proceed forward." 
                    print(f"{Fore.YELLOW}>> Auto-selected: {player_choice}{Style.RESET_ALL}")
                    time.sleep(1)

            # ---------------------------------------------------------
            # 6. INPUT HANDLING (MANUAL USER COMMANDS)
            # ---------------------------------------------------------
            if not self.is_test_mode and not player_choice:
                while True:
                    if turn_data["input_type"] == "choice" and turn_data["choices"]:
                        user_input = input(f"\n{Fore.CYAN}What do you do? (1-{len(turn_data['choices'])}) {Style.RESET_ALL}> ")
                    else:
                        user_input = input(f"\n{Fore.CYAN}Your answer: {Style.RESET_ALL}> ")

                    ui_clean = user_input.strip()
                    if not ui_clean: continue

                    # Parse meta-commands (e.g., 'fix: make it raining')
                    if ":" in ui_clean:
                        cmd_parts = ui_clean.split(":", 1)
                        cmd_key = cmd_parts[0].strip().lower()
                        cmd_val = cmd_parts[1].strip()
                    else:
                        cmd_key = ui_clean.lower()
                        cmd_val = ""

                    # Map raw input to Engine Actions
                    if cmd_key in ['q', 'quit', 'exit']:
                        print(f"\n{Fore.YELLOW}State saved successfully. See you next time!")
                        sys.exit(0)
                    elif cmd_key in ['?', 'help']:
                        self.print_help_menu()
                        continue
                    elif cmd_key == 'clear':
                        action_cmd = 'clear'
                        break
                    elif cmd_key == 'test':
                        action_cmd = 'test'
                        break
                    elif cmd_key == 'restart':
                        log_event(self.adv_dir, "Command: RESTART ADVENTURE")
                        action_cmd = 'restart'
                        break
                    elif cmd_key in ['recap', 'summary']:
                        print(f"\n{Style.DIM}Generating recap, please wait...")
                        recap_text = generate_recap(self.setup_data, self.history)
                        print(f"\n{Fore.CYAN}=== THE STORY SO FAR ===\n{Fore.WHITE}{recap_text}\n{Fore.CYAN}========================\n")
                        continue
                    elif cmd_key == 'export':
                        action_cmd = 'export'
                        break
                    elif cmd_key == 'redo':
                        log_event(self.adv_dir, "Command: REDO (User rerolled turn)")
                        action_cmd = 'redo'
                        break
                    elif cmd_key == 'undo':
                        log_event(self.adv_dir, "Command: UNDO (User backtracked)")
                        action_cmd = 'undo'
                        break
                    elif cmd_key == 'novelize':
                        self.novelize_history()
                        continue
                    elif cmd_key == 'fix':
                        if not self.allow_fix_command:
                            print(f"\n{Fore.RED}[System] The 'fix' command is disabled!{Style.RESET_ALL}")
                            continue
                        log_event(self.adv_dir, f"Command: FIX (Instruction: {cmd_val})")
                        action_cmd = 'fix'
                        self.fix_instruction = cmd_val
                        break

                    # Allow child engines (like Sandbox) to intercept custom commands (e.g. Chapter transitions)
                    handled, p_choice = self.process_custom_command(cmd_key, user_input)
                    if handled:
                        if p_choice: player_choice = p_choice
                        break

                    # Handle standard choice selection by index
                    if turn_data["input_type"] == "choice" and turn_data["choices"]:
                        try:
                            choice_idx = int(ui_clean)
                            if 1 <= choice_idx <= len(turn_data["choices"]):
                                selected_str = turn_data["choices"][choice_idx - 1]
                                
                                # Catch meta-choices generated by Victory/Death interceptors
                                if selected_str == "Quit": sys.exit(0)
                                elif selected_str in ["Export Story", "Export Tragic Ending"]:
                                    action_cmd = 'export'; break
                                elif selected_str == "Restart Game":
                                    action_cmd = 'restart'; break
                                elif selected_str == "Undo (Cheat Death and try a different action)":
                                    action_cmd = 'undo'; break
                                else:
                                    player_choice = selected_str; break
                            else: continue
                        except ValueError:
                            # If they typed a string instead of a number, treat it as a custom action
                            player_choice = ui_clean; break
                    else:
                        player_choice = ui_clean; break

            # ---------------------------------------------------------
            # 7. ACTION EXECUTION & SAVE COMMITS
            # ---------------------------------------------------------
            if action_cmd == 'clear': continue
            elif action_cmd == 'test': self.is_test_mode = True; continue
            
            elif action_cmd == 'export':
                from exporter import export_story
                exp_choice = input(f"{Fore.YELLOW}1. TXT  2. MD  3. HTML\nChoose (1-3): {Style.RESET_ALL}").strip()
                if exp_choice in ['1', '2', '3']:
                    path = export_story(self.adv_dir, self.setup_data, self.history, self.chapters, int(exp_choice))
                    print(f"{Fore.GREEN}Exported to: {path}")
                    time.sleep(2)
                continue
                
            elif action_cmd == 'restart':
                print(f"\n{Fore.RED}=== RESTART WARNING ===")
                print(f"{Fore.RED}Are you sure you want to restart? All progress will be lost and there is NO undo.")
                print(f"{Fore.YELLOW}If you want to replay without losing progress, it is recommended to make a backup of the '{self.adv_dir.name}' folder before restarting.")
                
                if input(f"\n{Fore.CYAN}Type 'yes' to confirm restart (or anything else to cancel): {Style.RESET_ALL}").strip().lower() == 'yes':
                    # 1. Wipe the story ledger
                    self.history.clear()
                    
                    # 2. Reset Chapter bounds depending on Mode
                    if self.is_campaign:
                        for c in self.chapters:
                            c["start_turn"] = 1 if c["chapter_number"] == 1 else None
                            c["end_turn"] = None
                    else:
                        self.chapters = [self.chapters[0]]
                        self.chapters[0]["start_turn"] = 1
                        self.chapters[0]["end_turn"] = None
                    
                    # 3. Flush the session log file so debugging is clean for the new run
                    log_file = self.adv_dir / "session_log.txt"
                    if log_file.exists():
                        try:
                            log_file.unlink() 
                        except Exception as e:
                            print(f"{Fore.RED}Note: Could not clear session_log: {e}")

                    # 4. Save blank state and re-initialize loop
                    log_event(self.adv_dir, "--- RESTARTED: Session Log and History Cleared ---")
                    self.save_state()
                    print(f"{Fore.GREEN}Adventure reset. Generating the opening scene...")
                    time.sleep(1)
                continue
                
            elif action_cmd == 'redo':
                # Pop the current turn completely and re-query the LLM
                self.history.pop()
                self.save_state()
                continue 
                
            elif action_cmd == 'undo':
                if len(self.history) > 1:
                    # Pop the current turn and nullify the choice of the PREVIOUS turn
                    self.history.pop()
                    self.history[-1]["player_choice"] = None 
                    
                    # Handle rolling back Chapter markers if we undid a transition
                    t_turn = len(self.history) + 1
                    if self.chapters[-1].get("start_turn") == t_turn:
                        self.chapters[-1]["start_turn"] = None
                        if len(self.chapters) > 1: self.chapters[-2]["end_turn"] = None
                    elif self.chapters[-1].get("start_turn") is None and len(self.chapters) > 1:
                        self.chapters.pop()
                    
                    self.save_state()
                continue
                
            elif action_cmd == 'fix':
                # Set the engine into Fix Mode and append the original JSON for the LLM to edit
                self.active_fix = f"EDIT MODE: Apply this fix: '{self.fix_instruction}'. Original JSON:\n{json.dumps(turn_data, indent=2)}"
                self.history.pop()
                self.is_fix_mode = True
                self.save_state()
                continue 

            # Standard Turn Commit: Lock in the player's choice and save state
            if player_choice:
                log_event(self.adv_dir, f"Player Action [Turn {len(self.history)}]: {player_choice}")
                
                # If player selected a chapter transition, update the chapter markers
                if player_choice.startswith("Start Chapter:"):
                    pending = next((c for c in self.chapters if c.get("start_turn") is None), None)
                    if pending:
                        pending["start_turn"] = len(self.history) + 1
                        if len(self.chapters) > 1: 
                            self.chapters[-2]["end_turn"] = len(self.history)

            self.history[-1]["player_choice"] = player_choice
            self.save_state()