"""
TomeWeaver: Sandbox Engine Module (Headless API)
------------------------------------------------
Handles the open-ended, player-driven Sandbox Mode. Allows for 
persistent world simulation and manual scene/chapter transitions without 
enforcing a strict plot outline.
"""

import json

from colorama import Fore, Style
from base_engine import BaseEngine
from config import ENGINE_CONFIG, PROMPTS

class SandboxEngine(BaseEngine):

    def __init__(self, adv_dir, setup_data):
        super().__init__(adv_dir, setup_data)
        self.is_campaign = False
        self.allow_manual_chapters = True

    # ---------------------------------------------------------
    # PROMPT CONSTRUCTION
    # ---------------------------------------------------------
    
    def build_messages(self, target_turn):
        """
        Constructs the Prompt payload (Messages array) to be sent to the LLM.
        Operates similarly to the Campaign engine, but tailored for open-ended 
        Sandbox play by supporting manual Director overrides and removing goal constraints.
        """
        # Retrieve context window limit
        context_window = ENGINE_CONFIG.get("context_window", 6)
        
        # Identify the active chapter
        active_chapter = next((c for c in reversed(self.chapters) if c.get("start_turn") is not None and c["start_turn"] <= target_turn), self.chapters[0])
        
        # Clone setup data for destructive formatting
        active_setup = self.setup_data.copy()
        edit_idx = getattr(self, 'backup_turn_idx', -1)
        completed_history = [
            t for i, t in enumerate(self.history) 
            if t.get("player_choice") is not None and i != edit_idx
        ]
          
        # ==========================================
        # 0. MEMORY & TOKEN OPTIMIZATION
        # ==========================================
        # Strip static intro text after Turn 1 to prevent context bloat
        if len(completed_history) > 0:
            active_setup.pop("setting", None)
            active_setup.pop("introduction", None)
            active_setup.pop("starting_situation", None)
            
        # Strip backend engine flags
        active_setup.pop("plot_outline", None)         
        active_setup.pop("mode", None) 
        active_setup.pop("track_inventory", None)
        active_setup.pop("can_die", None)
        active_setup.pop("allow_cheats", None)
        active_setup.pop("inventory_dictionary", None)
        
        # ==========================================
        # 1. CONSTRUCT THE SYSTEM PROMPT
        # ==========================================
        
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
            
        # The Context Sandwich (Top Bread): Brief identity + World Lore
        system_content = "You are an expert Game Master running a text-based interactive campaign.\n\nCORE WORLD:\n" + json.dumps(active_setup, indent=2)
        
        # --- INJECT LONG-TERM MEMORY (RAG) ---
        memory_str = ""
        
        # 1. High-Level Chapter Summaries (Past)
        chapter_ledger = self.memory.get("chapter_ledger", [])
        if chapter_ledger:
            memory_str += "COMPLETED CHAPTERS (The Story So Far):\n"
            for c in chapter_ledger: 
                memory_str += f"- Chapter {c.get('chapter_number', '?')} ({c.get('chapter_title', '')}): {c.get('summary', '')}\n"
                
        # 2. Granular Part Summaries (Current/Active)
        plot_ledger = self.memory.get("plot_ledger", [])
        condensed_chap_nums = [c.get('chapter_number') for c in chapter_ledger]
        
        # Filter out parts that belong to older chapters which have already been condensed
        active_plot_ledger = [p for p in plot_ledger if p.get('chapter_number') not in condensed_chap_nums]
        
        if active_plot_ledger:
            # Failsafe: Hard cap to the last 15 parts to physically prevent context overflow if a single chapter goes on forever
            if len(active_plot_ledger) > 15: active_plot_ledger = active_plot_ledger[-15:]
            memory_str += "\nRECENT EVENTS (Granular):\n"
            for p in active_plot_ledger: 
                memory_str += f"- {p.get('summary', '')}\n"
                
        char_ledger = self.memory.get("character_ledger", {})
        if char_ledger:
            memory_str += "\nACTIVE CHARACTERS & LORE BIBLE:\n"
            for k, data in char_ledger.items():
                if isinstance(data, list): memory_str += f"- {k}: {' '.join(data)}\n"
                else:
                    if data.get("state", "active") == "archived": continue
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
                    if data.get("state", "active") == "archived": continue
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
                    if data.get("state", "active") == "archived": continue
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
                    if data.get("state", "active") == "archived": continue
                    traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                    events = " ".join(data.get("ledger", []))
                    notes = f" | Author Notes: {data.get('author_notes', '')}" if data.get("author_notes") else ""
                    memory_str += f"- {k} | Traits: [{traits}] | Recent Events: {events}{notes}\n"
                
        if memory_str:
            system_content += "\n\nLONG-TERM MEMORY:\n" + memory_str

        system_content += f"\n\nACTIVE CHAPTER (Chapter {active_chapter['chapter_number']}: {active_chapter['title']})\n"
        if active_chapter.get('setting'): system_content += f"Setting Override: {active_chapter['setting']}\n"
        if active_chapter.get('pov'): system_content += f"POV Override: {active_chapter['pov']}\n"

        # Inject the Master Rules & JSON Schema AFTER the memory so the AI doesn't forget it
        system_content += "\n\n" + active_prompt_text

        if self.track_inventory:
            # FIX: Force the rule fragment to use the CURRENT state, not the setup schema
            frag = PROMPTS.get("FRAG_INVENTORY", "").replace("{inv_format}", current_inv_state)
            system_content += "\n\n" + frag

        if self.can_die:
            system_content += "\n\n" + PROMPTS.get("FRAG_CAN_DIE", "")
        else:
            system_content += "\n\n" + PROMPTS.get("FRAG_NO_DIE", "")
        
        # ==========================================
        # 2. EVALUATE REQUIRED KEYS
        # ==========================================
        req_keys = []
        if self.track_inventory: req_keys.append("'inventory_and_state' (string)")
        if self.can_die: req_keys.append("'is_game_over' (boolean)")
        
        req_str = ""
        if req_keys:
            req_str = "\n" + PROMPTS.get("FRAG_REQ_KEYS", "").replace("{keys}", ", ".join(req_keys))
        
        test_rule = ""
        if getattr(self, 'is_test_mode', False):
            test_rule = "\n\n" + PROMPTS.get("FRAG_TEST_MODE", "")
        
        # ==========================================
        # 3. DEFINE THE INSTRUCTION BLOCK
        # ==========================================
        p_style = self.setup_data.get("narrative", {}).get("prologue", "expand").lower()
        is_prologue = (len(self.history) == 0) and (p_style != "none")

        if is_prologue:
            # --- PROLOGUE HANDLING ---
            first_chap_title = active_chapter.get('title', 'Chapter 1')
            system_content += f"\n\nINITIAL SETTING: {self.setup_data.get('setting', '')}\nSITUATION: {self.setup_data.get('starting_situation', '')}\n"
            messages = [{"role": "system", "content": system_content}]
            
            if getattr(self, 'prologue_content', ""):
                start_instruction = PROMPTS.get("FRAG_SANDBOX_PROLOGUE_EXPAND", "")
                start_instruction = start_instruction.replace("{prologue_content}", self.prologue_content)
                start_instruction = start_instruction.replace("{chapter_title}", first_chap_title)
            else:
                start_instruction = PROMPTS.get("FRAG_SANDBOX_PROLOGUE_GENERATE", "").replace("{chapter_title}", first_chap_title)
                
            messages.append({"role": "user", "content": self.active_fix if self.active_fix else start_instruction})

        else:
            # --- NORMAL TURN HANDLING ---
            last_action = completed_history[-1]['player_choice'] if completed_history else ""
            
            if last_action.startswith("EXPAND:"):
                # Expansion Tool (Director Override)
                expand_txt = last_action[7:].strip()
                base_instruction = PROMPTS.get("FRAG_SANDBOX_EXPAND", "")
                base_instruction = base_instruction.replace("{expand_txt}", expand_txt)
                base_instruction = base_instruction.replace("{test_rule}", test_rule)
                base_instruction = base_instruction.replace("{req_str}", req_str)
            else:
                # Standard Response
                base_instruction = PROMPTS.get("FRAG_SANDBOX_TURN", "")
                base_instruction = base_instruction.replace("{test_rule}", test_rule)
                base_instruction = base_instruction.replace("{req_str}", req_str)
            
            # --- MANUAL CHAPTER OVERRIDE ---
            # If the user triggered the "New Chapter" wizard in the UI, force the AI to do a cold open
            if active_chapter.get("start_turn") == target_turn and target_turn > 1:
                time_jump = f" Time jump: {active_chapter['time']}." if active_chapter.get('time') else ""
                base_instruction = PROMPTS.get("FRAG_SANDBOX_COLD_OPEN", "")
                base_instruction = base_instruction.replace("{chapter_number}", str(active_chapter['chapter_number']))
                base_instruction = base_instruction.replace("{chapter_title}", active_chapter['title'])
                base_instruction = base_instruction.replace("{test_rule}", test_rule)
                base_instruction = base_instruction.replace("{req_str}", req_str)
                base_instruction = base_instruction.replace("{time_jump}", time_jump)

            # ==========================================
            # 4. ASSEMBLE HISTORY & MESSAGES
            # ==========================================
            messages = [{"role": "system", "content": system_content}]
            
            if completed_history:
                history_text = "RECENT HISTORY:\n"
                for turn in completed_history[-context_window:]:
                    history_text += f"Turn {turn['turn']}:\n"
                    history_text += f"Location: {turn.get('location', 'Unknown')}\n"
                    
                    if self.track_inventory:
                        history_text += f"Inventory & State: {turn.get('inventory_and_state', '')}\n"
                    
                    bridge = turn.get('narrative_bridge', '')
                    bridge_text = f"Transition: {bridge}\n" if bridge and bridge not in ["[OK]", "[FAILED]"] else ""
                    
                    history_text += f"{bridge_text}Story: {turn['story_text']}\n"
                    
                    # Highlight manual UI overrides so the AI understands they are absolute commands,
                    # not just something the character 'said' or 'did'.
                    action = turn['player_choice']
                    if action.lower().startswith(("setting:", "pov:", "time:", "scene:", "director:", "jump:", "wrap up")):
                        history_text += f"DIRECTOR INSTRUCTION: {action}\n\n"
                    else:
                        history_text += f"Player Action: {action}\n\n"
                
                messages.append({"role": "user", "content": history_text + (self.active_fix if self.active_fix else base_instruction)})
            else:
                messages.append({"role": "user", "content": self.active_fix if self.active_fix else base_instruction})

        # ==========================================
        # 5. EXPLOIT RECENCY BIAS (The Director's Note)
        # ==========================================
        # Enforce strict JSON formatting directly above where the AI will begin writing.
        messages[-1]["content"] += "\n\n" + PROMPTS.get("FRAG_SANDBOX_DIRECTOR_NOTE", "")
        
        return messages

    # ---------------------------------------------------------
    # HEADLESS API ENDPOINT: MANUAL CHAPTER WIZARD
    # ---------------------------------------------------------
    
    def trigger_manual_chapter(self, title, setting=None, pov=None, time_jump=None):
        """
        API Endpoint: Replaces the old CLI wizard. The GUI calls this method 
        with the user's desired settings. Appends the pending chapter and 
        forces the LLM to wrap up the current scene.
        """
        pending = next((c for c in self.chapters if c.get("start_turn") is None), None)
        if pending:
            print(f"{Fore.RED}A chapter transition is already pending! Undo to cancel it.{Style.RESET_ALL}")
            return None # GUI can capture this as a failed trigger
            
        print(f"\n{Fore.CYAN}=== MANUAL CHAPTER TRANSITION INITIATED ==={Style.RESET_ALL}")
        
        new_chap = {
            "chapter_number": len(self.chapters) + 1,
            "title": title,
            "start_turn": None, 
            "setting": setting if setting else None,
            "pov": pov if pov else None,
            "time": time_jump if time_jump else None
        }
        self.chapters.append(new_chap)
        self.save_state()
        
        action_instruction = f"DIRECTOR INSTRUCTION: Wrap up this chapter with a satisfying conclusion or cliffhanger. Do NOT start '{title}' yet."
        
        # Route directly into the standard action pipeline
        return self.submit_action(action_instruction)