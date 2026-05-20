"""
TomeWeaver: Campaign Engine Module (Headless API)
-------------------------------------------------
Handles the structured, plot-driven Campaign Mode. This engine enforces a predefined 
chapter outline, tracks specific goals, and manages automatic narrative transitions 
when objectives are met.
"""

import json
import sys

from colorama import Fore, Style
from base_engine import BaseEngine
from config import ENGINE_CONFIG, load_json_safely, PROMPTS

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
                print(f"{Fore.RED}Critical Error: Campaign mode requires a 'plot_outline' array in setup.json!{Style.RESET_ALL}")
                sys.exit(1)
            
            # Initialize the tracking ledger with the first chapter's data
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
        # Retrieve the context window limit (how many past turns the AI is allowed to remember)
        context_window = ENGINE_CONFIG.get("context_window", 6)
        
        # Identify the active chapter by searching backward through the chapters array.
        # We look for the most recent chapter that has actually started.
        active_chapter = next((c for c in reversed(self.chapters) if c["start_turn"] is not None and c["start_turn"] <= target_turn), self.chapters[0])
        
        # Clone the setup data so we can destructively modify it for the prompt without altering active memory
        active_setup = self.setup_data.copy()
        
        # Filter history to only include turns where the player took an action.
        # CRITICAL: Exclude the turn currently being edited so the LLM doesn't feed on its own unpolished text.
        edit_idx = getattr(self, 'backup_turn_idx', -1)
        completed_history = [
            t for i, t in enumerate(self.history) 
            if t.get("player_choice") is not None and i != edit_idx
        ]
          
        # ==========================================
        # 0. MEMORY & TOKEN OPTIMIZATION
        # ==========================================
        # Once the player has made their first choice (Turn 1 completed), we stop sending 
        # the raw introduction and setting blocks. The AI's context window will naturally 
        # retain the setting, and dropping these static strings saves hundreds of tokens per turn.
        if len(completed_history) > 0:
            active_setup.pop("setting", None)
            active_setup.pop("introduction", None)
            active_setup.pop("starting_situation", None)
            
        # Strip backend/mechanical keys from the world lore. The AI only needs narrative 
        # information, so we hide the engine's internal configuration flags from it.
        active_setup.pop("plot_outline", None)         
        active_setup.pop("mode", None) 
        active_setup.pop("track_inventory", None)
        active_setup.pop("can_die", None)
        active_setup.pop("allow_cheats", None)
        active_setup.pop("prologue_style", None)
        active_setup.pop("epilogue_style", None)
        active_setup.pop("inventory_dictionary", None)
        # Note: We keep "title", "tone", and "main_character" forever to maintain narrative consistency.
        
        # ==========================================
        # 1. CONSTRUCT THE SYSTEM PROMPT (The "God Rules")
        # ==========================================
        # This forms the absolute baseline instructions for the LLM.
        
        # --- FETCH CURRENT STATE ---
        current_inv_state = ""
        if self.track_inventory:
            if completed_history:
                current_inv_state = completed_history[-1].get("inventory_and_state", "")
            
            # Fallback to Turn 0 setup if history is empty or string is missing
            if not current_inv_state:
                inv_schema = self.setup_data.get("inventory_dictionary", {})
                if isinstance(inv_schema, dict) and inv_schema:
                    current_inv_state = " ".join([f"{k}: {v.get('val', '')}." for k, v in inv_schema.items()]).strip()
                else:
                    current_inv_state = str(inv_schema)

        # Dynamically inject the EXACT CURRENT STATE into the JSON template example
        active_prompt_text = self.system_prompt_text
        if self.track_inventory and current_inv_state:
            inv_template_str = f'"inventory_and_state": "{current_inv_state}",\n'
            active_prompt_text = active_prompt_text.replace("{inv_template}", inv_template_str)
        else:
            active_prompt_text = active_prompt_text.replace("{inv_template}", "")
            
        system_content = active_prompt_text + "\n\nCORE WORLD:\n" + json.dumps(active_setup, indent=2)
        
        # --- INJECT LONG-TERM MEMORY (RAG) ---
        memory_str = ""
        plot_ledger = self.memory.get("plot_ledger", [])
        if plot_ledger:
            memory_str += "THE STORY SO FAR:\n"
            for p in plot_ledger: memory_str += f"- {p.get('summary', '')}\n"
                
        char_ledger = self.memory.get("character_ledger", {})
        if char_ledger:
            memory_str += "\nACTIVE CHARACTERS & LORE BIBLE:\n"
            for k, data in char_ledger.items():
                if isinstance(data, list): memory_str += f"- {k}: {' '.join(data)}\n"
                else:
                    traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                    events = " ".join(data.get("ledger", []))
                    notes = f" | Author Notes: {data.get('author_notes', '')}" if data.get("author_notes") else ""
                    memory_str += f"- {k} | Traits: [{traits}] | Recent Events: {events}{notes}\n"
            
        loc_ledger = self.memory.get("location_ledger", {})
        if loc_ledger:
            memory_str += "\nACTIVE LOCATIONS & LORE BIBLE:\n"
            for k, data in loc_ledger.items(): 
                if isinstance(data, list): memory_str += f"- {k}: {' '.join(data)}\n"
                else:
                    traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                    events = " ".join(data.get("ledger", []))
                    notes = f" | Author Notes: {data.get('author_notes', '')}" if data.get("author_notes") else ""
                    memory_str += f"- {k} | Traits: [{traits}] | Recent Events: {events}{notes}\n"
                    
        art_ledger = self.memory.get("artifact_ledger", {})
        if art_ledger:
            memory_str += "\nACTIVE ARTIFACTS / KEY ITEMS:\n"
            for k, data in art_ledger.items(): 
                if isinstance(data, list): memory_str += f"- {k}: {' '.join(data)}\n"
                else:
                    traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                    events = " ".join(data.get("ledger", []))
                    notes = f" | Author Notes: {data.get('author_notes', '')}" if data.get("author_notes") else ""
                    memory_str += f"- {k} | Traits: [{traits}] | Recent Events: {events}{notes}\n"
                    
        fac_ledger = self.memory.get("faction_ledger", {})
        if self.setup_data.get("track_factions", False) and fac_ledger:
            memory_str += "\nACTIVE FACTIONS & ORGANIZATIONS:\n"
            for k, data in fac_ledger.items(): 
                if isinstance(data, list): memory_str += f"- {k}: {' '.join(data)}\n"
                else:
                    traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                    events = " ".join(data.get("ledger", []))
                    notes = f" | Author Notes: {data.get('author_notes', '')}" if data.get("author_notes") else ""
                    memory_str += f"- {k} | Traits: [{traits}] | Recent Events: {events}{notes}\n"
                
        if memory_str:
            system_content += "\n\nLONG-TERM MEMORY:\n" + memory_str
            
        # --- RESUME STANDARD INJECTION ---
        system_content += f"\n\nACTIVE CHAPTER (Chapter {active_chapter['chapter_number']}: {active_chapter['title']})\n"
        
        goal_text = active_chapter.get('goal', 'Survive')
        system_content += f"GOAL: {goal_text}\n"
        system_content += f"OBSTACLES: {active_chapter.get('obstacles', 'None')}\n"
        
        outline = self.setup_data.get("plot_outline", [])
        is_final_chapter = (active_chapter['chapter_number'] == len(outline))
        
        # Dynamically append rule fragments based on engine configurations
        if is_final_chapter:
            system_content += "\n\n" + PROMPTS.get("FRAG_FINAL_CHAPTER", "")

        system_content += "\n\n" + PROMPTS.get("FRAG_STATE_RULE", "")

        if self.track_inventory:
            # FIX: Force the rule fragment to use the CURRENT state, not the setup schema
            frag = PROMPTS.get("FRAG_INVENTORY", "").replace("{inv_format}", current_inv_state)
            system_content += "\n\n" + frag

        if self.can_die:
            system_content += "\n\n" + PROMPTS.get("FRAG_CAN_DIE", "")
        else:
            system_content += "\n\n" + PROMPTS.get("FRAG_NO_DIE", "")

        # ==========================================
        # 2. EVALUATE STATE & REQUIRED KEYS
        # ==========================================
        # Determine exactly which JSON keys the AI must output this turn to prevent engine crashes.
        is_epilogue = completed_history and completed_history[-1].get("player_choice") == "Conclude the Story"
        
        req_keys = ["'goal_progress' (string)"]
        # FIX: The AI does not need to output inventory on the Epilogue turn
        if self.track_inventory and not is_epilogue: 
            req_keys.append("'inventory_and_state' (string)")
            
        if self.can_die or is_epilogue: 
            req_keys.append("'is_game_over' (boolean)")
        
        req_str = ""
        if req_keys:
            req_str = "\n" + PROMPTS.get("FRAG_REQ_KEYS", "").replace("{keys}", ", ".join(req_keys))

        # Inject Golden Path logic if Developer Test Mode is active
        test_rule = ""
        if getattr(self, 'is_test_mode', False) and not is_epilogue:
            test_rule = "\n\n" + PROMPTS.get("FRAG_TEST_MODE", "")

        # ==========================================
        # 3. DEFINE THE INSTRUCTION BLOCK (The Immediate Task)
        # ==========================================
        # Here we determine what exactly we want the AI to do right now (Start, Play, Edit, or End).
        
        if is_epilogue:
            # --- EPILOGUE HANDLING ---
            system_content += "\n\n" + PROMPTS.get("FRAG_EPILOGUE_MODE", "")
            
            if getattr(self, 'epilogue_content', ''):
                # Epilogue Expansion Mode: Embellish author's notes into prose
                base_instruction = PROMPTS.get("FRAG_EPILOGUE_EXPAND", "")
                base_instruction = base_instruction.replace("{epilogue_content}", self.epilogue_content)
                base_instruction = base_instruction.replace("{req_str}", req_str)
            else:
                # Epilogue Pure Generation Mode: Let AI imagine the ending entirely
                base_instruction = PROMPTS.get("FRAG_EPILOGUE_GENERATE", "").replace("{req_str}", req_str)
        else:
            # --- NORMAL TURN HANDLING ---
            win_choice = "Conclude the Story" if is_final_chapter else "Complete the Chapter"
            last_action = completed_history[-1]['player_choice'] if completed_history else ""
            
            if last_action.startswith("EXPAND:"):
                # The user used the Director's Expand tool
                expand_txt = last_action[7:].strip()
                base_instruction = PROMPTS.get("FRAG_CAMPAIGN_EXPAND", "")
                base_instruction = base_instruction.replace("{expand_txt}", expand_txt)
                base_instruction = base_instruction.replace("{test_rule}", test_rule)
                base_instruction = base_instruction.replace("{req_str}", req_str)
                base_instruction = base_instruction.replace("{goal_text}", goal_text)
                base_instruction = base_instruction.replace("{win_choice}", win_choice)
            else:
                # Standard gameplay response
                base_instruction = PROMPTS.get("FRAG_CAMPAIGN_TURN", "")
                base_instruction = base_instruction.replace("{test_rule}", test_rule)
                base_instruction = base_instruction.replace("{req_str}", req_str)
                base_instruction = base_instruction.replace("{goal_text}", goal_text)
                base_instruction = base_instruction.replace("{win_choice}", win_choice)

            # --- COLD OPEN OVERRIDE (Chapter Transitions) ---
            # If the timeline target matches a new chapter's start, force the AI to write an establishing scene.
            p_style = self.setup_data.get("narrative", {}).get("prologue", "expand").lower()
            if active_chapter.get("start_turn") == target_turn and (target_turn > 1 or p_style == "none"):
                base_instruction = PROMPTS.get("FRAG_CAMPAIGN_COLD_OPEN", "")
                base_instruction = base_instruction.replace("{chapter_number}", str(active_chapter['chapter_number']))
                base_instruction = base_instruction.replace("{chapter_title}", active_chapter['title'])
                base_instruction = base_instruction.replace("{req_str}", req_str)

        # ==========================================
        # 4. ASSEMBLE HISTORY & MESSAGES
        # ==========================================
        p_style = self.setup_data.get("narrative", {}).get("prologue", "expand").lower()
        is_prologue = (len(self.history) == 0) and (p_style != "none")

        if is_prologue:
            # --- PROLOGUE HANDLING (Turn 0) ---
            first_chap_title = active_chapter.get('title', 'Chapter 1')
            if getattr(self, 'prologue_content', ''):
                start_instruction = PROMPTS.get("FRAG_PROLOGUE_EXPAND", "")
                start_instruction = start_instruction.replace("{prologue_content}", self.prologue_content)
                start_instruction = start_instruction.replace("{chapter_title}", first_chap_title)
            else:
                start_instruction = PROMPTS.get("FRAG_PROLOGUE_GENERATE", "").replace("{chapter_title}", first_chap_title)
            
            system_content += f"\n\nINITIAL SETTING: {active_chapter.get('setting', '')}\n"
            messages = [{"role": "system", "content": system_content}]
            
            # Use self.active_fix if the user triggered an Editor override (Polish/Fix)
            messages.append({"role": "user", "content": self.active_fix if self.active_fix else start_instruction})

        else:
            # --- NORMAL GAMEPLAY (Context Window Splicing) ---
            messages = [{"role": "system", "content": system_content}]
            if completed_history:
                history_text = "RECENT HISTORY:\n"
                for turn in completed_history[-context_window:]:
                    # Clearly separate state fields on their own lines to prevent hallucination bleeding
                    history_text += f"Turn {turn['turn']}:\n"
                    history_text += f"Location: {turn.get('location', 'Unknown')}\n"
                    
                    if self.track_inventory:
                        history_text += f"Inventory & State: {turn.get('inventory_and_state', '')}\n"
                        
                    goal_prog = turn.get('goal_progress', '')
                    if goal_prog:
                        # Replace newlines in the checklist with slashes to keep the prompt block tight
                        history_text += f"Goal Progress: {goal_prog.replace(chr(10), ' / ')}\n"
                    
                    bridge = turn.get('narrative_bridge', '')
                    bridge_text = f"Transition: {bridge}\n" if bridge and bridge not in ["[OK]", "[FAILED]"] else ""
                    
                    history_text += f"{bridge_text}Story: {turn['story_text']}\nPlayer Action: {turn['player_choice']}\n\n"
                
                messages.append({"role": "user", "content": history_text + (self.active_fix if self.active_fix else base_instruction)})
            else:
                messages.append({"role": "user", "content": self.active_fix if self.active_fix else base_instruction})

        # ==========================================
        # 5. EXPLOIT RECENCY BIAS (The Director's Note)
        # ==========================================
        # LLMs suffer heavily from "recency bias"—they pay the most attention to the very last sentences 
        # they read. By appending the strict JSON formatting rules to the absolute bottom of the user message,
        # we drastically reduce syntax hallucinations and missing choices.
        messages[-1]["content"] += "\n\n" + PROMPTS.get("FRAG_DIRECTOR_NOTE", "")
        
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
        
        # --- VICTORY EPILOGUE LOGIC ---
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
        
        # --- HARD SPEEDRUN BLOCK ---
        # Prevent the AI from accidentally completing the goal on the exact turn the chapter starts
        if active_chap.get("start_turn") == target_turn:
            goal_achieved = False
            
        turn_data["chapter_goal_achieved"] = goal_achieved

        # --- CHAPTER TRANSITION LOGIC ---
        if goal_achieved:
            outline = self.setup_data.get("plot_outline", [])
            current_num = active_chap["chapter_number"]
            
            if current_num < len(outline):
                # Prepare the next chapter
                if not any("Start Chapter:" in str(c) for c in turn_data.get("choices", [])):
                    print(f"\n{Fore.GREEN}[System: Chapter Goal Achieved! Preparing transition...]{Style.RESET_ALL}")
                
                next_chap_data = outline[current_num] 
                
                # Check if we already staged the pending chapter object
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
                
                # Force the choices to only offer the transition
                turn_data["input_type"] = "choice" 
                turn_data["choices"] = [f"Start Chapter: {pending_chap['title']}"]
            else:
                # This IS the last chapter; trigger the finale
                turn_data["input_type"] = "choice"
                turn_data["choices"] = ["Conclude the Story"]