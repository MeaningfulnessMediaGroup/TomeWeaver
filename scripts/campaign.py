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
            
            objs = []
            for i, o in enumerate(first_chap.get("objectives", [])):
                o_copy = o.copy()
                o_copy["status"] = "ACTIVE" if i == 0 else "LOCKED"
                objs.append(o_copy)
                
            initial_chapters = [{
                "chapter_number": 1,
                "title": first_chap.get("title", "Chapter 1"),
                "start_turn": 1, 
                "end_turn": None,
                "objectives": objs
            }]
                
            with open(chapters_file, "w", encoding="utf-8") as f:
                json.dump(initial_chapters, f, indent=4)
            return initial_chapters
            
        chaps = load_json_safely(chapters_file, "chapters.json")
        
        # --- LEGACY AUTO-MIGRATION ---
        # If chapters.json is corrupted or using the old format, heal it from setup.json
        changed = False
        outline = self.setup_data.get("plot_outline", [])
        for c in chaps:
            if "goal" in c and "objectives" not in c:
                idx = c.get("chapter_number", 1) - 1
                if 0 <= idx < len(outline) and "objectives" in outline[idx]:
                    # Pull the fresh objectives array directly from the setup file
                    c["objectives"] = [obj.copy() for obj in outline[idx]["objectives"]]
                    for i, o in enumerate(c["objectives"]):
                        o["status"] = "ACTIVE" if i == 0 else "LOCKED"
                else:
                    # Absolute fallback
                    c["objectives"] = [{
                        "goal": c.pop("goal", "Survive"),
                        "obstacles": c.pop("obstacles", "None"),
                        "setting": "", "pov": "", "status": "ACTIVE"
                    }]
                c.pop("goal", None)
                c.pop("obstacles", None)
                changed = True
                
        if changed:
            with open(chapters_file, "w", encoding="utf-8") as f:
                json.dump(chaps, f, indent=4)
                
        return chaps


    # ---------------------------------------------------------
    # PROMPT CONSTRUCTION
    # ---------------------------------------------------------

    def build_messages(self, target_turn):
        """
        Constructs the Prompt payload (Messages array) to be sent to the LLM.
        This function acts as the "Director", dynamically assembling the world state, 
        current chapter goals, recent history, and strict formatting rules.
        """
        context_window = ENGINE_CONFIG.get("context_window", 6)
        
        active_chapter = next((c for c in reversed(self.chapters) if c["start_turn"] is not None and c["start_turn"] <= target_turn), self.chapters[0])
        active_setup = self.setup_data.copy()
        
        edit_idx = getattr(self, 'backup_turn_idx', -1)
        completed_history = [
            t for i, t in enumerate(self.history) 
            if t.get("player_choice") is not None and i != edit_idx
        ]
          
        # ==========================================
        # 0. MEMORY & TOKEN OPTIMIZATION
        # ==========================================
        if len(completed_history) > 0:
            active_setup.pop("setting", None)
            active_setup.pop("introduction", None)
            active_setup.pop("starting_situation", None)
            
        # Hide internal mechanics and the Global Goal from the AI so it doesn't get distracted
        active_setup.pop("goal", None) 
        active_setup.pop("plot_outline", None)         
        active_setup.pop("mode", None) 
        active_setup.pop("track_inventory", None)
        active_setup.pop("can_die", None)
        active_setup.pop("allow_cheats", None)
        active_setup.pop("prologue_style", None)
        active_setup.pop("epilogue_style", None)
        active_setup.pop("inventory_dictionary", None)
        
        # ==========================================
        # 1. CONSTRUCT THE SYSTEM PROMPT
        # ==========================================
        current_inv_state = ""
        if self.track_inventory:
            if completed_history:
                current_inv_state = completed_history[-1].get("inventory_and_state", "")
            
            if not current_inv_state:
                inv_schema = self.setup_data.get("inventory_dictionary", {})
                if isinstance(inv_schema, dict) and inv_schema:
                    current_inv_state = " ".join([f"{k}: {v.get('val', '')}." for k, v in inv_schema.items()]).strip()
                else:
                    current_inv_state = str(inv_schema)

        active_prompt_text = self.system_prompt_text
        if self.track_inventory and current_inv_state:
            inv_template_str = f'"inventory_and_state": "{current_inv_state}",\n'
            active_prompt_text = active_prompt_text.replace("{inv_template}", inv_template_str)
        else:
            active_prompt_text = active_prompt_text.replace("{inv_template}", "")
            
        system_content = "You are an expert Game Master running a text-based interactive campaign.\n\nCORE WORLD:\n" + json.dumps(active_setup, indent=2)
        
        # --- INJECT LONG-TERM MEMORY (RAG) ---
        memory_str = ""
        
        chapter_ledger = self.memory.get("chapter_ledger", [])
        if chapter_ledger:
            memory_str += "COMPLETED CHAPTERS (The Story So Far):\n"
            for c in chapter_ledger: 
                memory_str += f"- Chapter {c.get('chapter_number', '?')} ({c.get('chapter_title', '')}): {c.get('summary', '')}\n"
                
        plot_ledger = self.memory.get("plot_ledger", [])
        condensed_chap_nums = [c.get('chapter_number') for c in chapter_ledger]
        active_plot_ledger = [p for p in plot_ledger if p.get('chapter_number') not in condensed_chap_nums]
        
        if active_plot_ledger:
            if len(active_plot_ledger) > 15: active_plot_ledger = active_plot_ledger[-15:]
            memory_str += "\nRECENT EVENTS (Granular):\n"
            for p in active_plot_ledger: 
                memory_str += f"- {p.get('summary', '')}\n"
                
        # Helper to format lore safely
        def append_lore(ledger_key, title):
            res = ""
            ledger = self.memory.get(ledger_key, {})
            if ledger:
                res += f"\nACTIVE {title}:\n"
                for k, data in ledger.items():
                    if isinstance(data, list): res += f"- {k}: {' '.join(data)}\n"
                    else:
                        if data.get("state", "active") == "archived": continue
                        traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                        events = " ".join(data.get("ledger", []))
                        notes = f" | Author Notes: {data.get('author_notes', '')}" if data.get("author_notes") else ""
                        res += f"- {k} | Traits: [{traits}] | Recent Events: {events}{notes}\n"
            return res

        memory_str += append_lore("character_ledger", "CHARACTERS & LORE BIBLE")
        memory_str += append_lore("location_ledger", "LOCATIONS")
        memory_str += append_lore("artifact_ledger", "ARTIFACTS / KEY ITEMS")
        if self.setup_data.get("track_factions", False):
            memory_str += append_lore("faction_ledger", "FACTIONS & ORGANIZATIONS")
                
        if memory_str:
            system_content += "\n\nLONG-TERM MEMORY:\n" + memory_str
            
        # --- THE QUEST TRACKER (Objectives Array Logic) ---
        system_content += f"\n\nACTIVE CHAPTER (Chapter {active_chapter['chapter_number']}: {active_chapter['title']})\n"
        
        objectives = active_chapter.get("objectives", [])
        completed_objs = []
        active_obj = None
        
        # Parse the array to find the current state (SILENTLY DROPPING 'LOCKED' OBJECTIVES)
        for obj in objectives:
            if obj.get("status") == "COMPLETED":
                completed_objs.append(obj.get("goal", ""))
            elif obj.get("status") == "ACTIVE" and not active_obj:
                active_obj = obj
                
        # Failsafe: If no active objective is found (e.g. legacy save), fall back to the first one
        if not active_obj and objectives:
            active_obj = objectives[0]
            
        # 1. Show past accomplishments so the AI knows what is already done
        if completed_objs:
            system_content += "\n--- PREVIOUSLY ACCOMPLISHED ---\n"
            for past_goal in completed_objs[-3:]: # Only show the last 3 to save tokens
                system_content += f"- [DONE] {past_goal}\n"
                
        # 2. Inject the single, isolated Active Objective
        goal_text = active_obj.get('goal', 'Survive') if active_obj else "Survive"
        system_content += f"\n--- CURRENT ACTIVE OBJECTIVE ---\n"
        system_content += f"GOAL: {goal_text}\n"
        system_content += f"OBSTACLES: {active_obj.get('obstacles', 'None') if active_obj else 'None'}\n"
        
        if active_obj and active_obj.get("setting"):
            system_content += f"SETTING SHIFT: {active_obj['setting']}\n"
            
        pov_raw = active_obj.get("pov") if active_obj and active_obj.get("pov") else active_chapter.get("pov", "Protagonist")
        if pov_raw:
            system_content += f"POV: {pov_raw}\n"
            system_content += f"CRITICAL POV RULE: You must write strictly from {pov_raw}'s perspective. Apply familial titles (Dad, Uncle, Aunt, etc.) ONLY as they relate to {pov_raw}. Never use another character's relationship title by mistake.\n"
            
        system_content += "CRITICAL CAMPAIGN RULES:\n"
        system_content += "1. Your SOLE PURPOSE right now is to guide the player to complete the CURRENT ACTIVE OBJECTIVE.\n"
        system_content += "2. You MUST NOT allow the player to advance the plot, leave the current main area, or find end-game artifacts until this specific objective is completed.\n"
        system_content += "3. If the player tries to wander off or do something unrelated, introduce obstacles to block them and circle the narrative back to the objective.\n"
        
        outline = self.setup_data.get("plot_outline", [])
        is_final_chapter = (active_chapter['chapter_number'] == len(outline))
        is_final_objective = True
        
        if objectives:
            # Check if there are any LOCKED objectives waiting after this one
            is_final_objective = not any(o.get("status") == "LOCKED" for o in objectives)
        
        if is_final_chapter and is_final_objective:
            system_content += "\n\n" + PROMPTS.get("FRAG_FINAL_CHAPTER", "")

        system_content += "\n\n" + PROMPTS.get("FRAG_STATE_RULE", "")

        if self.track_inventory:
            frag = PROMPTS.get("FRAG_INVENTORY", "").replace("{inv_format}", current_inv_state)
            system_content += "\n\n" + frag

        if self.can_die:
            system_content += "\n\n" + PROMPTS.get("FRAG_CAN_DIE", "")
            system_content += "\nCRITICAL RULE: 'is_game_over' is strictly a mortality flag. NEVER set it to true just because an objective or chapter is completed. ONLY set it to true if the player physically dies."
        else:
            system_content += "\n\n" + PROMPTS.get("FRAG_NO_DIE", "")

        # ==========================================
        # 2. EVALUATE STATE & REQUIRED KEYS
        # ==========================================
        is_epilogue = completed_history and completed_history[-1].get("player_choice") == "Conclude the Story"
        
        req_keys = []
        if self.track_inventory and not is_epilogue: 
            req_keys.append("'inventory_and_state' (string)")
            
        if self.can_die or is_epilogue: 
            req_keys.append("'is_game_over' (boolean)")
        
        req_str = ""
        if req_keys:
            req_str = "\n" + PROMPTS.get("FRAG_REQ_KEYS", "").replace("{keys}", ", ".join(req_keys))

        test_rule = ""
        if getattr(self, 'is_test_mode', False) and not is_epilogue:
            test_rule = "\n\n" + PROMPTS.get("FRAG_TEST_MODE", "")

        # ==========================================
        # 3. DEFINE THE INSTRUCTION BLOCK
        # ==========================================
        if is_epilogue:
            system_content += "\n\n" + PROMPTS.get("FRAG_EPILOGUE_MODE", "")
            if getattr(self, 'epilogue_content', ''):
                base_instruction = PROMPTS.get("FRAG_EPILOGUE_EXPAND", "")
                base_instruction = base_instruction.replace("{epilogue_content}", self.epilogue_content)
                base_instruction = base_instruction.replace("{req_str}", req_str)
            else:
                base_instruction = PROMPTS.get("FRAG_EPILOGUE_GENERATE", "").replace("{req_str}", req_str)
        else:
            last_action = completed_history[-1]['player_choice'] if completed_history else ""
            
            if last_action.startswith("EXPAND:"):
                expand_txt = last_action[7:].strip()
                base_instruction = PROMPTS.get("FRAG_CAMPAIGN_EXPAND", "")
                base_instruction = base_instruction.replace("{expand_txt}", expand_txt)
            else:
                base_instruction = PROMPTS.get("FRAG_CAMPAIGN_TURN", "")
                
            base_instruction = base_instruction.replace("{test_rule}", test_rule)
            base_instruction = base_instruction.replace("{req_str}", req_str)

            p_style = self.setup_data.get("narrative", {}).get("prologue", "expand").lower()
            
            # Cold Open hook for Chapters OR Mid-Chapter Scene Shifts
            if (active_chapter.get("start_turn") == target_turn and (target_turn > 1 or p_style == "none")) or last_action == "Proceed to the next objective":
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
            first_chap_title = active_chapter.get('title', 'Chapter 1')
            if getattr(self, 'prologue_content', ''):
                start_instruction = PROMPTS.get("FRAG_PROLOGUE_EXPAND", "")
                start_instruction = start_instruction.replace("{prologue_content}", self.prologue_content)
                start_instruction = start_instruction.replace("{chapter_title}", first_chap_title)
            else:
                start_instruction = PROMPTS.get("FRAG_PROLOGUE_GENERATE", "").replace("{chapter_title}", first_chap_title)
            
            # Use objective setting if available
            init_set = active_obj.get("setting") if active_obj and active_obj.get("setting") else active_chapter.get('setting', '')
            system_content += f"\n\nINITIAL SETTING: {init_set}\n"
            messages = [{"role": "system", "content": system_content}]
            messages.append({"role": "user", "content": self.active_fix if self.active_fix else start_instruction})

        else:
            messages = [{"role": "system", "content": system_content}]
            if completed_history:
                history_text = "RECENT HISTORY:\n"
                for turn in completed_history[-context_window:]:
                    history_text += f"Turn {turn['turn']}:\n"
                    history_text += f"Location: {turn.get('location', 'Unknown')}\n"
                    
                    if self.track_inventory:
                        history_text += f"Inventory & State: {turn.get('inventory_and_state', '')}\n"
                        
                    goal_prog = turn.get('goal_progress', '')
                    if goal_prog:
                        history_text += f"Goal Progress: {goal_prog.replace(chr(10), ' / ')}\n"
                    
                    bridge = turn.get('narrative_bridge', '')
                    bridge_text = f"Transition: {bridge}\n" if bridge and bridge not in ["[OK]", "[FAILED]"] else ""
                    
                    history_text += f"{bridge_text}Story: {turn['story_text']}\nPlayer Action: {turn['player_choice']}\n\n"
                
                messages.append({"role": "user", "content": history_text + (self.active_fix if self.active_fix else base_instruction)})
            else:
                messages.append({"role": "user", "content": self.active_fix if self.active_fix else base_instruction})

        # The Context Sandwich Fix
        messages[-1]["content"] += "\n\n" + ("=" * 40) + "\n\n" + active_prompt_text + "\n\n" + PROMPTS.get("FRAG_DIRECTOR_NOTE", "")
        
        return messages
        
        
    # ---------------------------------------------------------
    # STATE PROCESSING HOOKS
    # ---------------------------------------------------------
    
    def post_generation_hook(self, turn_data):
        """
        Intercepts the AI's response to check for objective completion.
        Manages the Quest Tracker array and orchestrates transitions.
        """
        target_turn = turn_data["turn"]
        active_chap = next((c for c in reversed(self.chapters) if c.get("start_turn") is not None and c["start_turn"] <= target_turn), self.chapters[0])
        
        # --- VICTORY EPILOGUE LOGIC ---
        is_epilogue = len(self.history) > 0 and self.history[-1].get("player_choice") == "Conclude the Story"
        if is_epilogue:
            turn_data["objective_achieved"] = True
            turn_data["chapter_goal_achieved"] = True
            turn_data["is_game_over"] = True
            turn_data["input_type"] = "choice"  
            turn_data["choices"] = ["Export Story", "Restart Game", "Quit"]
            if "*** THE END" not in turn_data.get("story_text", "").upper():
                turn_data["story_text"] += "\n\n*** THE END. ***"
            return 
        
        # --- PHASE 2: THE AUDITOR ---
        objectives = active_chap.get("objectives", [])
        active_obj = None
        active_idx = -1
        for i, obj in enumerate(objectives):
            if obj.get("status") == "ACTIVE":
                active_obj = obj
                active_idx = i
                break
                
        # Speedrun Block: Skip the Auditor if the player hasn't actually made a choice towards the goal yet.
        c_start = active_chap.get("start_turn")
        last_action = self.history[-1].get("player_choice", "") if self.history else ""
        
        is_prologue = (target_turn == 0)
        is_chapter_start = (c_start is not None and target_turn == c_start)
        is_objective_transition = (last_action == "Proceed to the next objective")
        
        is_setup_turn = is_prologue or is_chapter_start or is_objective_transition
        
        if active_obj and not turn_data.get("is_game_over", False) and not is_setup_turn:
            from llm import evaluate_campaign_objective
            context_turns = self.history[-2:] if len(self.history) >= 2 else self.history
            
            # Fetch the inventory from the PREVIOUS turn (Phase 1 might have hallucinated a mess, we want the truth)
            old_inv = self.history[-1].get("inventory_and_state", "") if self.history else ""
            
            # Auditor now processes both Goal and Inventory
            audit_res = evaluate_campaign_objective(context_turns, turn_data, active_obj, self.adv_dir, old_inv)
            
            turn_data["objective_achieved"] = audit_res["achieved"]
            turn_data["goal_progress"] = f"Target: {active_obj.get('goal', 'Survive')}\nStatus: {audit_res['reason']}"
            
            # Definitive overwrite: The Auditor's inventory is now the source of truth
            if self.track_inventory:
                turn_data["inventory_and_state"] = audit_res["inventory"]
        else:
            turn_data["objective_achieved"] = False
            if is_setup_turn:
                turn_data["goal_progress"] = "Establishing new setting and goal."
            else:
                turn_data["goal_progress"] = "Objective locked or game over."
                
        objective_achieved = turn_data["objective_achieved"]

        # 2. Advance the Quest Tracker
        if objective_achieved:
            if active_idx != -1:
                # Mark it done
                objectives[active_idx]["status"] = "COMPLETED"
                
                # Are there more objectives in this chapter?
                if active_idx + 1 < len(objectives):
                    # Yes! Unlock the next micro-objective
                    objectives[active_idx + 1]["status"] = "ACTIVE"
                    
                    print(f"\n{Fore.GREEN}[System: Objective Complete! Unlocking next stage...]{Style.RESET_ALL}")
                    turn_data["input_type"] = "choice" 
                    turn_data["choices"] = ["Proceed to the next objective"]
                    
                    # Do NOT end the chapter or the game
                    turn_data["chapter_goal_achieved"] = False
                    turn_data["is_game_over"] = False
                    
                else:
                    # No more objectives! The entire Chapter is complete.
                    turn_data["chapter_goal_achieved"] = True
                    
                    outline = self.setup_data.get("plot_outline", [])
                    current_num = active_chap["chapter_number"]
                    
                    if current_num < len(outline):
                        # Prepare the next chapter
                        print(f"\n{Fore.GREEN}[System: Chapter Complete! Preparing transition...]{Style.RESET_ALL}")
                        
                        next_chap_data = outline[current_num] 
                        pending_chap = next((c for c in self.chapters if c.get("start_turn") is None), None)
                        if not pending_chap:
                            
                            # Build the new locked array
                            new_objs = []
                            for i, o in enumerate(next_chap_data.get("objectives", [])):
                                o_copy = o.copy()
                                o_copy["status"] = "ACTIVE" if i == 0 else "LOCKED"
                                new_objs.append(o_copy)
                                
                            new_chap = {
                                "chapter_number": current_num + 1,
                                "title": next_chap_data.get("title", f"Chapter {current_num + 1}"),
                                "start_turn": None, "end_turn": None,
                                "objectives": new_objs
                            }
                            self.chapters.append(new_chap)
                            pending_chap = new_chap
                        
                        turn_data["input_type"] = "choice" 
                        turn_data["choices"] = [f"Start Chapter: {pending_chap['title']}"]
                        turn_data["is_game_over"] = False
                    else:
                        # This IS the last chapter; trigger the finale
                        turn_data["input_type"] = "choice"
                        turn_data["choices"] = ["Conclude the Story"]
                        turn_data["is_game_over"] = False

        else:
            # Objective not met. Proceed normally.
            turn_data["chapter_goal_achieved"] = False