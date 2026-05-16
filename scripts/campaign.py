"""
TomeWeaver: Campaign Engine Module
----------------------------------
Handles the structured, plot-driven Campaign Mode. This engine enforces a predefined 
chapter outline, tracks specific goals, and manages automatic narrative transitions 
when objectives are met.
"""

import json
import sys
from colorama import Fore, Style
from base_engine import BaseEngine
from config import ENGINE_CONFIG, load_json_safely

# ---------------------------------------------------------
# CAMPAIGN ENGINE CLASS
# ---------------------------------------------------------

class CampaignEngine(BaseEngine):
    def __init__(self, adv_dir, setup_data):
        """
        Initializes the Campaign Engine. Sets strict flags to enforce 
        automatic plot-progression and disable manual chapter transitions.
        """
        super().__init__(adv_dir, setup_data)
        self.is_campaign = True
        self.allow_manual_chapters = False 
        self.allow_fix_command = self.setup_data.get("allow_cheats", False)

    # ---------------------------------------------------------
    # CHAPTER MANAGEMENT
    # ---------------------------------------------------------

    def load_chapters(self):
        """
        Loads the chapters.json file. If it doesn't exist, it builds the initial
        file based on the `plot_outline` array provided in setup.json.
        """
        chapters_file = self.adv_dir / "chapters.json"
        
        if not chapters_file.exists():
            outline = self.setup_data.get("plot_outline", [])
            if not outline:
                print(f"{Fore.RED}Critical Error: Campaign mode requires a 'plot_outline' array in setup.json!")
                sys.exit(1)
            
            first_chap = outline[0]
            initial_chapters = [{
                "chapter_number": 1,
                "title": first_chap.get("title", "Chapter 1"),
                "start_turn": 1, 
                "end_turn": None,
                "setting": first_chap.get("setting"),
                "pov": first_chap.get("pov"),
                "time": first_chap.get("time"),
                "goal": first_chap.get("goal"),
                "obstacles": first_chap.get("obstacles")
            }]
                
            with open(chapters_file, "w", encoding="utf-8") as f:
                json.dump(initial_chapters, f, indent=4)
            return initial_chapters
            
        return load_json_safely(chapters_file, "chapters.json")

    # ---------------------------------------------------------
    # PROMPT CONSTRUCTION
    # ---------------------------------------------------------

    def build_messages(self, target_turn):
        """
        Constructs the Prompt payload (Messages array) to be sent to the LLM.
        This function acts as the "Director", dynamically assembling the world state, 
        current chapter goals, recent history, and strict formatting rules.
        """
        # Retrieve the context window limit (how many past turns the AI remembers)
        context_window = ENGINE_CONFIG.get("context_window", 6)
        
        # Identify which chapter the player is currently in based on the target turn
        active_chapter = next((c for c in reversed(self.chapters) if c["start_turn"] is not None and c["start_turn"] <= target_turn), self.chapters[0])
        
        # Clone the setup data so we can safely modify it for the prompt
        active_setup = self.setup_data.copy()
        
        # Identify the turns that actually contain player actions
        completed_history = [t for t in self.history if t.get("player_choice") is not None]
          
        # --- MEMORY OPTIMIZATION ---
        # Once the player has made their first choice (Turn 1 completed),
        # we stop sending the raw introduction/starting situations to save LLM tokens.
        if len(completed_history) > 0:
            active_setup.pop("setting", None)
            active_setup.pop("introduction", None)
            active_setup.pop("starting_situation", None)
            
        # Strip backend/mechanical keys from the world lore sent to the AI
        active_setup.pop("plot_outline", None)         
        active_setup.pop("mode", None) 
        active_setup.pop("track_inventory", None)
        active_setup.pop("can_die", None)
        active_setup.pop("allow_cheats", None)
        active_setup.pop("prologue_style", None)
        active_setup.pop("epilogue_style", None)
        # Note: We keep "title", "tone", and "main_character" forever to maintain consistency
        
        # ==========================================
        # 1. CONSTRUCT THE SYSTEM PROMPT
        # ==========================================
        system_content = self.system_prompt_text + "\n\nCORE WORLD:\n" + json.dumps(active_setup, indent=2)
        system_content += f"\n\nACTIVE CHAPTER (Chapter {active_chapter['chapter_number']}: {active_chapter['title']})\n"
        
        goal_text = active_chapter.get('goal', 'Survive')
        system_content += f"GOAL: {goal_text}\n"
        system_content += f"OBSTACLES: {active_chapter.get('obstacles', 'None')}\n"
        
        outline = self.setup_data.get("plot_outline", [])
        is_final_chapter = (active_chapter['chapter_number'] == len(outline))
        
        if is_final_chapter:
            system_content += "\nNOTE: This is the FINAL CHAPTER of the campaign. When the GOAL is met, you MUST apply Rule #8 (THE FINALE) to conclude the story."

        system_content += "\n\nCRITICAL STATE RULE:\nThe JSON keys 'location', 'inventory_and_state', and 'chapter_goal_achieved' MUST reflect the world state at the VERY END of your story text. If the story text ends with the player inside a new room, the 'location' MUST be that room. If the player just finished the task, 'chapter_goal_achieved' MUST be true.\n"

        if self.track_inventory:
            system_content += "\nINVENTORY & STATE TRACKING:\nYou must track the protagonist's items, physical health, and active statuses. CRITICAL: Your JSON output MUST include the 'inventory_and_state' key!\n"

        if self.can_die:
            system_content += "\nMORTALITY & GAME OVER:\nThe player is not invincible. If they make a fatal mistake, you MUST explicitly describe their gruesome and final death in the story_text. ONLY IF the character is explicitly dead and their story is over, set 'is_game_over': true. If they are still breathing, running, or it is a cliffhanger, it MUST be false. CRITICAL: Your JSON output MUST include the 'is_game_over' key!\n"
        else:
            system_content += "\nFAIL FORWARD (NO DEATH):\nThe protagonist CANNOT be killed. If the player makes a terrible mistake, they must survive, but you must inflict severe narrative consequences.\n"

        # ==========================================
        # 2. EVALUATE CURRENT STATE & REQUIRED KEYS
        # ==========================================
        is_epilogue = completed_history and completed_history[-1].get("player_choice") == "Conclude the Story"
        
        # Build the dynamic list of required JSON keys based on active settings
        req_keys = ["'goal_progress' (string)"]
        if self.track_inventory: req_keys.append("'inventory_and_state' (string)")
        if self.can_die or is_epilogue: req_keys.append("'is_game_over' (boolean)")
        req_str = f" CRITICAL: Your JSON MUST include the following keys: {', '.join(req_keys)}." if req_keys else ""

        # Inject Golden Path logic if Test Mode is active
        test_rule = ""
        if getattr(self, 'is_test_mode', False) and not is_epilogue:
            test_rule = "\n*** TEST MODE ACTIVE ***: The FIRST choice in your 'choices' array (Choice #1) MUST ALWAYS be the single most optimal, direct action that propels the player toward achieving the GOAL. You must still provide 3-6 choices, but ensure Choice #1 is the most direct path to the goal."

        # ==========================================
        # 3. DEFINE THE INSTRUCTION BLOCK
        # ==========================================
        if is_epilogue:
            # --- EPILOGUE HANDLING ---
            system_content += "\n\nEPILOGUE MODE:\nThe campaign is over. The protagonist has survived and won! You MUST set 'is_game_over': true in your JSON.\n"
            
            if getattr(self, 'epilogue_content', ''):
                # Epilogue Expansion Mode: Embellish author's notes
                base_instruction = f"Generate the next turn in JSON format.\nCRITICAL OVERRIDE: The campaign's final goal has been achieved! Expand the following brief epilogue into 5-8 paragraphs of satisfying, meaningful prose: '{self.epilogue_content}'\nYou MUST finish the 'story_text' paragraph with: *** THE END. ***\nCRITICAL: Set 'chapter_goal_achieved' to true and 'is_game_over' to true.{req_str} Provide meta-options in the choices array like 'Restart Game', 'Export Story', and 'Quit'."
            else:
                # Epilogue Pure Generation Mode: Let AI imagine the ending
                base_instruction = f"Generate the next turn in JSON format.\nCRITICAL OVERRIDE: The campaign's final goal has been achieved! Write a satisfying and meaningful epilogue. You MUST finish the 'story_text' paragraph with: *** THE END. ***\nCRITICAL: Set 'chapter_goal_achieved' to true and 'is_game_over' to true.{req_str} Provide meta-options in the choices array like 'Restart Game', 'Export Story', and 'Quit'."
        else:
            # --- NORMAL TURN HANDLING ---
            win_choice = "Conclude the Story" if is_final_chapter else "Complete the Chapter"
            
            last_action = completed_history[-1]['player_choice'] if completed_history else ""
            
            if last_action.startswith("EXPAND:"):
                expand_txt = last_action[7:].strip()
                base_instruction = (
                    f"CRITICAL OVERRIDE (EXPANSION MODE): Expand the following author notes into 3-5 paragraphs of cinematic, rich prose:\n"
                    f"'{expand_txt}'\n\n"
                    f"Provide 3 to 6 choices.{test_rule}{req_str}\n\n"
                    f"*** MANDATORY PROSE RULES ***:\n"
                    f"1. Write 3 to 5 LONG paragraphs. Do NOT be brief.\n"
                    f"2. Describe the smells, sounds, and the character's internal dread/excitement.\n"
                    f"3. Use evocative, literary language.\n\n"
                    f"*** MANDATORY CHOICE RULES ***:\n"
                    f"1. Provide EXACTLY 3 to 6 choices.\n"
                    f"2. Even if the goal is clear, add exploratory choices (e.g., 'Search the area', 'Check equipment').\n"
                    f"3. Choices MUST be SHORT (Max 15 words) and focus only on the ACTION, not the result.\n"
                    f"4. Use active verbs (e.g., 'Examine...', 'Run...', 'Attempt...').\n\n"
                    f"5. If achieved, choices MUST only be ['{win_choice}'].\n\n"
                    f"*** CRITICAL GOAL CHECK ***:\n"
                    f"1. In 'goal_progress', list every requirement of the GOAL ('{goal_text}') and mark it as [DONE] or [PENDING].\n"
                    f"2. If and ONLY IF every part of the goal is marked [DONE], set 'chapter_goal_achieved' to true. Otherwise, it MUST be false.\n"
                )
            else:
                base_instruction = (
                    f"Generate the next turn in JSON format. Write 1 to 3 paragraphs. Provide 3 to 6 choices.{test_rule}{req_str}\n\n"
                    f"*** MANDATORY PROSE RULES ***:\n"
                    f"1. Write 3 to 5 LONG paragraphs. Do NOT be brief.\n"
                    f"2. Describe the smells, sounds, and the character's internal dread/excitement.\n"
                    f"3. Use evocative, literary language.\n\n"
                    f"*** MANDATORY CHOICE RULES ***:\n"
                    f"1. Provide EXACTLY 3 to 6 choices.\n"
                    f"2. Even if the goal is clear, add exploratory choices (e.g., 'Search the area', 'Check equipment').\n"
                    f"3. Choices MUST be SHORT (Max 15 words) and focus only on the ACTION, not the result.\n"
                    f"4. Use active verbs (e.g., 'Examine...', 'Run...', 'Attempt...').\n\n"
                    f"5. If achieved, choices MUST only be ['{win_choice}'].\n\n"
                    f"*** CRITICAL GOAL CHECK ***:\n"
                    f"1. In 'goal_progress', list every requirement of the GOAL ('{goal_text}') and mark it as [DONE] or [PENDING].\n"
                    f"2. If and ONLY IF every part of the goal is marked [DONE], set 'chapter_goal_achieved' to true. Otherwise, it MUST be false.\n"
                )

            # --- COLD OPEN OVERRIDE (Chapter Transitions) ---
            # Check p_style here as well to trigger the cold open on Turn 1 if skipping prologue
            p_style = self.setup_data.get("narrative", {}).get("prologue", "expand").lower()
            if active_chapter.get("start_turn") == target_turn and (target_turn > 1 or p_style == "none"):
                base_instruction = f"CRITICAL OVERRIDE: Begin Chapter {active_chapter['chapter_number']}: {active_chapter['title']}. Write a smooth introductory scene establishing the new setting and goal. Provide 3 to 6 choices. CRITICAL: You MUST set 'chapter_goal_achieved' to false for this introductory turn!{req_str}"

        # ==========================================
        # 4. ASSEMBLE HISTORY & MESSAGES
        # ==========================================
        p_style = self.setup_data.get("narrative", {}).get("prologue", "expand").lower()
        is_prologue = (len(self.history) == 0) and (p_style != "none")

        if is_prologue:
            # --- PROLOGUE HANDLING (Turn 0) ---
            first_chap_title = active_chapter.get('title', 'Chapter 1')
            
            if getattr(self, 'prologue_content', ''):
                # Prologue Expansion Mode: Embellish author's notes
                start_instruction = (
                    f"PROLOGUE MODE: Expand the following brief prologue into 5-8 paragraphs of cinematic, rich prose: '{self.prologue_content}'\n"
                    f"Establishing the atmosphere and stakes. "
                    f"CRITICAL: Set 'input_type' to 'choice' and 'choices' to ONLY ['Start Chapter 1: {first_chap_title}']. "
                    f"Set 'chapter_goal_achieved' to false."
                )
            else:
                # Prologue Pure Generation Mode: Let AI imagine the beginning
                start_instruction = (
                    f"PROLOGUE MODE: Generate a sweeping, atmospheric introduction (5-8 paragraphs) for this campaign. "
                    f"Establish the character's current state and the looming threat. "
                    f"CRITICAL: Set 'input_type' to 'choice' and 'choices' to ONLY ['Start Chapter 1: {first_chap_title}']. "
                    f"Set 'chapter_goal_achieved' to false."
                )
            
            system_content += f"\n\nINITIAL SETTING: {active_chapter.get('setting', '')}\n"
            messages = [{"role": "system", "content": system_content}]
            messages.append({"role": "user", "content": self.active_fix if self.active_fix else start_instruction})

        else:
            # --- NORMAL GAMEPLAY OR SKIP-PROLOGUE ---
            messages = [{"role": "system", "content": system_content}]
            
            if completed_history:
                # If gameplay has occurred, assemble the rolling context window
                history_text = "RECENT HISTORY:\n"
                for turn in completed_history[-context_window:]:
                    loc = turn.get('location', 'Unknown')
                    inv_text = f" | Inv: {turn.get('inventory_and_state', '')}" if self.track_inventory else ""
                    goal_prog = turn.get('goal_progress', '')
                    prog_text = f" | Progress Checklist: {goal_prog}" if goal_prog else ""
                    
                    history_text += f"Turn {turn['turn']} [Loc: {loc}{inv_text}{prog_text}]:\nStory: {turn['story_text']}\nPlayer Action: {turn['player_choice']}\n\n"
                
                messages.append({"role": "user", "content": history_text + (self.active_fix if self.active_fix else base_instruction)})
            else:
                # Failsafe if history gets wiped but it isn't Prologue (or if prologue was 'none')
                messages.append({"role": "user", "content": self.active_fix if self.active_fix else base_instruction})

        # ==========================================
        # 5. INJECT DIRECTOR'S FINAL REMINDER
        # ==========================================
        # We append a final structural reminder to the very last message so the LLM 
        # doesn't forget formatting rules while focusing on narrative context.
        final_reminder = (
            "\n\n[DIRECTOR'S NOTE]: \n"
            "- Write 3-5 cinematic paragraphs in 'story_text'.\n"
            "- Provide 3-6 choices in the 'choices' array.\n"
            "- CRITICAL: Each choice MUST be a brief action (Max 15 words). No outcomes or dialogue.\n"
            "- JSON SAFETY: Use \\n for paragraph breaks. Use \\\" for dialogue quotes. "
            "NEVER use raw carriage returns inside the JSON object.\n"
            "- CRITICAL: Output the JSON object and NOTHING ELSE. No preamble, no post-turn chat, no backticks."
        )
        messages[-1]["content"] += final_reminder
        
        return messages
        
    # ---------------------------------------------------------
    # STATE PROCESSING HOOKS
    # ---------------------------------------------------------
    
    def post_generation_hook(self, turn_data):
        """
        Intercepts the AI's response to check for objective completion.
        If the goal is met, it orchestrates the transition to the next chapter.
        """
        target_turn = turn_data["turn"]
        
        active_chap = next((c for c in reversed(self.chapters) if c.get("start_turn") is not None and c["start_turn"] <= target_turn), self.chapters[0])
        
        # Victory Epilogue logic
        is_epilogue = len(self.history) > 0 and self.history[-1].get("player_choice") == "Conclude the Story"
        if is_epilogue:
            turn_data["chapter_goal_achieved"] = True
            turn_data["is_game_over"] = True
            turn_data["input_type"] = "choice"  
            turn_data["choices"] = ["Export Story", "Restart Game", "Quit"]
            if "*** THE END" not in turn_data.get("story_text", "").upper():
                turn_data["story_text"] += "\n\n*** THE END. ***"
            return 
        
        raw_goal = turn_data.get("chapter_goal_achieved", False)
        goal_achieved = str(raw_goal).strip().lower() == "true"
        
        # Hard speedrun block: Prevent completing the goal on the exact turn the chapter starts
        if active_chap.get("start_turn") == target_turn:
            goal_achieved = False
            
        turn_data["chapter_goal_achieved"] = goal_achieved

        if goal_achieved:
            outline = self.setup_data.get("plot_outline", [])
            current_num = active_chap["chapter_number"]
            
            # Use current_num to check if there are more chapters in the outline
            if current_num < len(outline):
                # Only print transition message if we haven't already set the transition choice
                if not any("Start Chapter:" in str(c) for c in turn_data.get("choices", [])):
                    print(f"\n{Fore.GREEN}[System: Chapter Goal Achieved! Preparing transition...]{Style.RESET_ALL}")
                
                next_chap_data = outline[current_num] # current_num is 1-based, so it's the index for the next chap
                
                # Check if we already created the next chapter object
                pending_chap = next((c for c in self.chapters if c.get("start_turn") is None), None)
                if not pending_chap:
                    new_chap = {
                        "chapter_number": current_num + 1,
                        "title": next_chap_data.get("title", f"Chapter {current_num + 1}"),
                        "start_turn": None, "end_turn": None,
                        "setting": next_chap_data.get("setting"), "pov": next_chap_data.get("pov"),
                        "time": next_chap_data.get("time"), "goal": next_chap_data.get("goal"),
                        "obstacles": next_chap_data.get("obstacles")
                    }
                    self.chapters.append(new_chap)
                    pending_chap = new_chap
                
                turn_data["input_type"] = "choice" 
                turn_data["choices"] = [f"Start Chapter: {pending_chap['title']}"]
            else:
                # This IS the last chapter
                turn_data["input_type"] = "choice"
                turn_data["choices"] = ["Conclude the Story"]
                
    # ---------------------------------------------------------
    # CUSTOM COMMAND HANDLER
    # ---------------------------------------------------------
    
    def process_custom_command(self, cmd_key, cmd_val):
        """
        Overrides the BaseEngine command handler to block manual chapter 
        transitions, enforcing strict plot-driven gameplay.
        """
        if cmd_key == 'chapter':
            print(f"{Fore.RED}You are in Campaign Mode. Chapters advance automatically based on plot goals!")
            return True, None
        return False, None