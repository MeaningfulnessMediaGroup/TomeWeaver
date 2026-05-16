"""
TomeWeaver: Sandbox Engine Module
---------------------------------
Handles the open-ended, player-driven Sandbox Mode. This engine allows for 
persistent world simulation and manual scene/chapter transitions without 
enforcing a strict plot outline.
"""

import json
from colorama import Fore, Style
from base_engine import BaseEngine
from config import ENGINE_CONFIG

# ---------------------------------------------------------
# SANDBOX ENGINE CLASS
# ---------------------------------------------------------

class SandboxEngine(BaseEngine):
    def __init__(self, adv_dir, setup_data):
        """
        Initializes the Sandbox Engine. Overrides base flags to disable 
        campaign logic and enable the manual Chapter Wizard.
        """
        super().__init__(adv_dir, setup_data)
        self.is_campaign = False
        self.allow_manual_chapters = True

    # ---------------------------------------------------------
    # PROMPT CONSTRUCTION
    # ---------------------------------------------------------
    
    def build_messages(self, target_turn):
        """
        Constructs the context window and system prompt for the LLM.
        Handles Sandbox-specific logic like dynamic overrides and manual chapters.
        """
        # --- 1. CONTEXT PREPARATION ---
        context_window = ENGINE_CONFIG.get("context_window", 6)
        active_chapter = next((c for c in reversed(self.chapters) if c.get("start_turn") is not None and c["start_turn"] <= target_turn), self.chapters[0])
        
        active_setup = self.setup_data.copy()
        
        # We only want the Introduction lore for the very beginning
        # Once the player has made their first choice (Turn 1 completed),
        # we stop sending the raw introduction field to save space.
        completed_history = [t for t in self.history if t.get("player_choice") is not None]
          
        # Remove these after the game is started to free up tokens
        if len(completed_history) > 0:
            active_setup.pop("setting", None)
            active_setup.pop("introduction", None)
            active_setup.pop("starting_situation", None)
            
        active_setup.pop("plot_outline", None)         
        active_setup.pop("mode", None) 
        active_setup.pop("track_inventory", None)
        active_setup.pop("can_die", None)
        active_setup.pop("allow_cheats", None)
        # Note: We keep "title", "tone", and "main_character" forever
        
        # --- 2. SYSTEM PROMPT ASSEMBLY ---
        system_content = self.system_prompt_text + "\n\nCORE WORLD:\n" + json.dumps(active_setup, indent=2)
        system_content += f"\n\nACTIVE CHAPTER (Chapter {active_chapter['chapter_number']}: {active_chapter['title']})\n"
        if active_chapter.get('setting'): system_content += f"Setting Override: {active_chapter['setting']}\n"
        if active_chapter.get('pov'): system_content += f"POV Override: {active_chapter['pov']}\n"

        if self.track_inventory:
            system_content += "\n\nINVENTORY & STATE TRACKING:\nYou must track the protagonist's items, physical health, and active statuses. CRITICAL: Your JSON output MUST include the 'inventory_and_state' key!\n"

        if self.can_die:
            system_content += "\n\nMORTALITY & GAME OVER:\nThe player is not invincible. If they make a fatal mistake, you MUST explicitly describe their gruesome and final death in the story_text. ONLY IF the character is explicitly dead and their story is over, set 'is_game_over': true. If they are still breathing, running, or it is a cliffhanger, it MUST be false. CRITICAL: Your JSON output MUST include the 'is_game_over' key!\n"
        else:
            system_content += "\n\nFAIL FORWARD (NO DEATH):\nThe protagonist CANNOT be killed. If the player makes a terrible mistake, they must survive, but you must inflict severe narrative consequences.\n"
        
        req_keys =[]
        if self.track_inventory: req_keys.append("'inventory_and_state' (string)")
        if self.can_die: req_keys.append("'is_game_over' (boolean)")
        req_str = f" CRITICAL: Your JSON MUST include the following keys: {', '.join(req_keys)}." if req_keys else ""
        
        # --- THE FIX: Inject Golden Path rule for Test Mode ---
        test_rule = ""
        if getattr(self, 'is_test_mode', False):
            test_rule = "\n*** TEST MODE ACTIVE ***: The FIRST choice in your 'choices' array (Choice #1) MUST ALWAYS be the single most optimal, direct action that propels the plot forward the fastest."
        
        # --- 3. NARRATIVE BRANCHING (PROLOGUE VS NORMAL PLAY) ---
        # The FIX: Check if prologue is set to 'none'. If so, skip prologue generation.
        p_style = self.setup_data.get("narrative", {}).get("prologue", "expand").lower()
        is_prologue = (len(self.history) == 0) and (p_style != "none")

        # --- BRANCH: PROLOGUE ---
        if is_prologue:
            first_chap_title = active_chapter.get('title', 'Chapter 1')
            system_content += f"\n\nINITIAL SETTING: {self.setup_data.get('setting', '')}\nSITUATION: {self.setup_data.get('starting_situation', '')}\n"
            messages = [{"role": "system", "content": system_content}]
            
            if getattr(self, 'prologue_content', ""):
                # Expansion Mode
                start_instruction = (
                    f"PROLOGUE OVERRIDE: Expand the following author notes into 5-8 paragraphs of rich, descriptive prose:\n'{self.prologue_content}'\n"
                    f"Establishing the scene. "
                    f"CRITICAL: Set 'input_type' to 'choice' and 'choices' to ONLY ['Start Chapter 1: {first_chap_title}']."
                )
            else:
                # Pure Generation Mode
                start_instruction = (
                    f"PROLOGUE OVERRIDE: Generate an atmospheric opening narrative (5-8 paragraphs) based on the INITIAL SETTING and SITUATION. "
                    f"CRITICAL: Set 'input_type' to 'choice' and 'choices' to ONLY ['Start Chapter 1: {first_chap_title}']."
                )
            messages.append({"role": "user", "content": self.active_fix if self.active_fix else start_instruction})

        # --- BRANCH: NORMAL GAMEPLAY ---
        else:
            base_instruction = (
                f"Based on the latest action, generate the next turn in JSON format.\n"
                f"*** MANDATORY RULES ***:\n"
                f"1. Write 3 to 5 detailed paragraphs.\n"
                f"2. Provide 3 to 6 choices.\n"
                f"3. Each choice MUST be BRIEF (Max 15 words) and describe only the ACTION, not the result.{test_rule}{req_str}"
            )
            
            if active_chapter.get("start_turn") == target_turn and target_turn > 1:
                base_instruction = f"CRITICAL OVERRIDE: Begin Chapter {active_chapter['chapter_number']}: {active_chapter['title']}. Write a smooth introductory scene establishing the setting. Do not conclude anything. Provide 3 to 6 choices.{test_rule}{req_str}"
                if active_chapter.get('time'): base_instruction += f" Time jump: {active_chapter['time']}."

            messages = [{"role": "system", "content": system_content}]
            
            if completed_history:
                history_text = "RECENT HISTORY:\n"
                for turn in completed_history[-context_window:]:
                    loc = turn.get('location', 'Unknown')
                    inv_text = f" | Inv: {turn.get('inventory_and_state', '')}" if self.track_inventory else ""
                    history_text += f"Turn {turn['turn']}[Loc: {loc}{inv_text}]:\nStory: {turn['story_text']}\n"
                    
                    action = turn['player_choice']
                    if action.lower().startswith(("setting:", "pov:", "time:", "scene:", "director:", "jump:", "wrap up")):
                        history_text += f"DIRECTOR INSTRUCTION: {action}\n\n"
                    else:
                        history_text += f"Player Action: {action}\n\n"
                
                messages.append({"role": "user", "content": history_text + (self.active_fix if self.active_fix else base_instruction)})
            else:
                # Failsafe if history gets wiped but it isn't Prologue (or if prologue was 'none')
                messages.append({"role": "user", "content": self.active_fix if self.active_fix else base_instruction})

        # --- 4. THE CHOICE & PROSE BOOSTER ---
        final_reminder = (
            "\n\n[DIRECTOR'S NOTE]: \n"
            "- Layer Sensory and Internal details in 'story_text' (3-5 paragraphs).\n"
            "- Provide 3-6 varied choices (Max 15 words each).\n"
            "- Focus choices on player INTENT (e.g., 'Search for...', 'Attempt to...').\n"
            "- JSON SAFETY: Use \\n for paragraph breaks. Use \\\" for dialogue quotes. "
            "NEVER use raw carriage returns inside the JSON object.\n"
            "- CRITICAL: Output the JSON object and NOTHING ELSE. No preamble, no post-turn chat, no backticks."
        )
        messages[-1]["content"] += final_reminder
        # ----------------------------------

        return messages
        
    # ---------------------------------------------------------
    # CUSTOM COMMAND HANDLER
    # ---------------------------------------------------------
    
    def process_custom_command(self, ui_lower, user_input):
        """
        Intercepts Sandbox-specific commands (like the Chapter Wizard) 
        from the user input before it hits the standard action parser.
        """
        if ui_lower == 'chapter' or ui_lower.startswith('chapter:'):
            pending = next((c for c in self.chapters if c.get("start_turn") is None), None)
            if pending:
                print(f"{Fore.RED}A chapter transition is already pending! Undo to cancel it.")
                return True, None
                
            print(f"\n{Fore.CYAN}=== NEW CHAPTER WIZARD ===")
            preset_title = user_input[8:].strip() if ui_lower.startswith('chapter:') else ""
            c_title = preset_title if preset_title else input(f"{Fore.YELLOW}Chapter Title: {Style.RESET_ALL}").strip()
            
            if not c_title:
                print(f"{Fore.RED}Title cannot be empty.")
                return True, None
                
            new_chap = {
                "chapter_number": len(self.chapters) + 1,
                "title": c_title,
                "start_turn": None, 
                "setting": input(f"{Fore.YELLOW}New Setting (Leave blank to keep): {Style.RESET_ALL}").strip() or None,
                "pov": input(f"{Fore.YELLOW}New POV (Leave blank to keep): {Style.RESET_ALL}").strip() or None,
                "time": input(f"{Fore.YELLOW}Time Jump (Leave blank to skip): {Style.RESET_ALL}").strip() or None
            }
            self.chapters.append(new_chap)
            self.save_state()
            
            return True, f"DIRECTOR INSTRUCTION: Wrap up this chapter with a satisfying conclusion or cliffhanger. Do NOT start '{c_title}' yet."
            
        return False, None