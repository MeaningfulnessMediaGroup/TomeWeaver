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
    """Open-world engine: manual chapters and player-driven pacing."""

    def __init__(self, adv_dir, setup_data):
        """Initialize sandbox mode flags after loading cartridge state.

        Args:
            adv_dir: Adventure folder path.
            setup_data: Parsed ``setup.json`` with ``mode`` typically ``sandbox``.
        """
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
        
        # --- UNIVERSE LORE MERGE ---
        # Dynamically prepend global universe rules to the local story rules
        if getattr(self, "is_universe_thread", False) and hasattr(self, "master_setup_data"):
            g_lore = self.master_setup_data.get("lore_and_rules", "").strip()
            l_lore = active_setup.get("lore_and_rules", "").strip()
            if g_lore:
                active_setup["lore_and_rules"] = f"[GLOBAL UNIVERSE LORE]:\n{g_lore}\n\n[LOCAL STORY LORE]:\n{l_lore}".strip()
                
            g_tone = self.master_setup_data.get("tone", "").strip()
            l_tone = active_setup.get("tone", "").strip()
            if g_tone:
                active_setup["tone"] = f"{g_tone}, {l_tone}".strip()
                
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
                
        # Helper to format lore safely
        # Helper to format lore safely
        def append_lore(ledger_key, title):
            res = ""
            ledger = self.memory.get(ledger_key, {})
            # Merge global and local, with local shadowing global
            combined = {**ledger.get("global", {}), **ledger.get("local", {})}
            
            if combined:
                res += f"\nACTIVE {title}:\n"
                for k, data in combined.items():
                    # Extreme defensive casting
                    if not isinstance(data, dict): 
                        if isinstance(data, list): res += f"- {k}: {' '.join(str(i) for i in data)}\n"
                        continue
                        
                    # --- SCOPE-AWARE STATE CHECK ---
                    # Determine if this entity is coming from the global bucket
                    # If it is, read its state from the thread-local override map!
                    is_global = k in ledger.get("global", {}) and k not in ledger.get("local", {})
                    
                    if is_global and getattr(self, "is_universe_thread", False):
                        state = self.memory.get("global_states", {}).get(k, {}).get("state", "archived")
                    else:
                        state = data.get("state", "active")
                        
                    if state == "archived": continue
                    
                    traits_dict = data.get("characteristics", {})
                    if not isinstance(traits_dict, dict): traits_dict = {}
                    
                    traits = ", ".join([f"{tk}: {tv}" for tk, tv in traits_dict.items()])
                    
                    ledger_list = data.get("ledger", [])
                    if not isinstance(ledger_list, list): ledger_list = []
                    events = " ".join(str(e) for e in ledger_list)
                    
                    notes = f" | Author Notes: {data.get('author_notes', '')}" if data.get("author_notes") else ""
                    res += f"- {k} | Traits: [{traits}] | Recent Events: {events}{notes}\n"
            return res

        memory_str += append_lore("character_ledger", "CHARACTERS & LORE BIBLE")
        memory_str += append_lore("location_ledger", "LOCATIONS & LORE BIBLE")
        memory_str += append_lore("artifact_ledger", "ARTIFACTS / KEY ITEMS")
        if self.setup_data.get("track_factions", False):
            memory_str += append_lore("faction_ledger", "FACTIONS & ORGANIZATIONS")
                
        if memory_str:
            system_content += "\n\nLONG-TERM MEMORY:\n" + memory_str
                

        system_content += f"\n\nACTIVE CHAPTER (Chapter {active_chapter['chapter_number']}: {active_chapter['title']})\n"
        if active_chapter.get('setting'): system_content += f"Setting Override: {active_chapter['setting']}\n"
        if active_chapter.get('pov'): 
            pov_val = active_chapter['pov']
            system_content += f"POV Override: {pov_val}\n"
            system_content += f"CRITICAL POV RULE: You must write strictly from {pov_val}'s perspective. Apply familial titles (Dad, Uncle, Aunt, etc.) ONLY as they relate to {pov_val}. Never use another character's relationship title by mistake.\n"

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
            # Deduplicate prefix
            if str(first_chap_title).lower().startswith("chapter 1"):
                import re
                first_chap_title = re.sub(r"^chapter 1[:\-\s]*", "", str(first_chap_title), flags=re.IGNORECASE).strip()

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
                expand_txt = last_action[7:].strip()
                base_instruction = PROMPTS.get("FRAG_SANDBOX_EXPAND", "")
                base_instruction = base_instruction.replace("{expand_txt}", expand_txt)
            elif "DIRECTOR INSTRUCTION: Wrap up the current scene" in last_action:
                # This explicitly handles the transition hook passed from the Force Chapter UI!
                base_instruction = "Wrap up the current scene and resolve the current action cleanly. Do not start a new chapter."
            else:
                # Standard Response
                base_instruction = PROMPTS.get("FRAG_SANDBOX_TURN", "")
            
            base_instruction = base_instruction.replace("{test_rule}", test_rule)
            base_instruction = base_instruction.replace("{req_str}", req_str)

            
            # --- MANUAL CHAPTER OVERRIDE ---
            # Trigger a cold open if this is explicitly the first turn of the new chapter
            if active_chapter.get("start_turn") == target_turn and target_turn > 1:
                time_jump = f" TIME JUMP: {active_chapter['time']}." if active_chapter.get('time') else ""
                
                # Heavily reinforce the new setting so the AI extracts POV and Location from it
                new_setting = f" \n\n*** NEW SCENE CONTEXT ***:\n{active_chapter['setting']}\n" if active_chapter.get('setting') else ""
                
                base_instruction = PROMPTS.get("FRAG_SANDBOX_COLD_OPEN", "")
                base_instruction = base_instruction.replace("{chapter_number}", str(active_chapter['chapter_number']))
                base_instruction = base_instruction.replace("{chapter_title}", active_chapter['title'])
                base_instruction = base_instruction.replace("{test_rule}", test_rule)
                base_instruction = base_instruction.replace("{req_str}", req_str)
                base_instruction = base_instruction.replace("{time_jump}", time_jump + new_setting)

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
    
    def trigger_manual_chapter(self, chapter_data):
        """
        RESTORED CINEMATIC TRANSITION:
        1. Takes structured chapter data from the Director's UI.
        2. Saves new chapter with explicit POV, Time, and Setting overrides.
        3. AI generates a Wrap-up for the OLD chapter with a single 'Start' choice.
        """
        # --- SELF-HEALING GHOST CHAPTERS ---
        # If the user previously forced a chapter but the AI failed to generate the transition,
        # there might be a "ghost" chapter stuck in the array with no start_turn.
        # We delete it so the Director's new command can proceed cleanly.
        self.chapters = [c for c in self.chapters if c.get("start_turn") is not None]
        
        c_num = len(self.chapters) + 1
        
        # Combine Location and Synopsis into a rich setting block for the AI to parse
        loc = chapter_data.get("location", "").strip()
        syn = chapter_data.get("synopsis", "").strip()
        full_setting = ""
        if loc: full_setting += f"LOCATION: {loc}\n"
        if syn: full_setting += f"SITUATION: {syn}"
        
        new_chap = {
            "chapter_number": c_num,
            "title": chapter_data.get("title", f"Chapter {c_num}").strip(),
            "start_turn": None, 
            "setting": full_setting.strip(),
            "pov": chapter_data.get("pov", "").strip(),
            "time": chapter_data.get("time", "").strip()
        }
        
        self.chapters.append(new_chap)
        self.save_state()
        
        # Step 3: Trigger the Wrap-up LLM Call for the CURRENT scene
        # Note: We use a specific delimiter (Chapter X: Title) so our deduplication logic catches it
        action_instruction = f"DIRECTOR INSTRUCTION: Wrap up the current scene. Provide exactly ONE choice in the 'choices' array: 'Start Chapter {c_num}: {new_chap['title']}'"
        
        return self.submit_action(action_instruction)