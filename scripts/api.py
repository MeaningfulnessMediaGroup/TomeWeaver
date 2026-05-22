"""
TomeWeaver: API Controller
--------------------------
The headless backend for the Desktop UI Dashboard. Handles story listing, 
creation, ZIP cartridge Import/Export, folder renaming, and engine instantiation.
Features an Autonomous Index for high-performance loading of 10,000+ stories.
"""
import os
import json
import shutil
import zipfile
import re
import datetime
from pathlib import Path

from sandbox import SandboxEngine
from campaign import CampaignEngine
from config import create_boilerplate_files

ADV_DIR = Path("adventures")
INDEX_FILE = ADV_DIR / "index.json"

def sanitize_foldername(name):
    """Strips illegal characters for safe OS directory creation."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean[:60].strip()

class TomeWeaverAPI:
    
    # ---------------------------------------------------------
    # AUTONOMOUS INDEXING SYSTEM
    # ---------------------------------------------------------

    @staticmethod
    def _extract_story_metadata(folder_path, rel_path):
        """Reads the raw JSON files for a single story and builds its metadata dictionary."""
        setup_file = folder_path / "setup.json"
        history_file = folder_path / "history.json"
        
        try:
            with open(setup_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {
                "folder_name": folder_path.name, 
                "title": "CORRUPTED JSON", 
                "mode": "error", "turns": 0, "location": "", "status": "Error",
                "path": str(folder_path.resolve())
            }
            
        turns = 0
        location = data.get("setting", "Unknown")
        status = "Not Started"
        
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as hf:
                    history = json.load(hf)
                    
                    # Fix: Make sure it's actually a populated list, not just an empty [] from a Restart
                    if isinstance(history, list) and len(history) > 0:
                        # Find the actual highest turn number recorded (handles Turn 0 correctly)
                        max_turn = max([int(t.get("turn", 0)) for t in history])
                        turns = max_turn
                        
                        last_turn = history[-1]
                        
                        # Only inherit the location if it actually exists, otherwise fallback to setup
                        location = last_turn.get("location", location)
                        if not location or not location.strip():
                            location = data.get("setting", "Unknown")
                        
                        # Safe boolean casting for game_over checks
                        is_over = str(last_turn.get("is_game_over", False)).lower() == "true"
                        is_victory = str(last_turn.get("chapter_goal_achieved", False)).lower() == "true"
                        
                        # FIX: High-Priority Override. If we are on Turn 0, it is NOT started, 
                        # even if history.json physically exists on disk.
                        if max_turn == 0:
                            status = "Not Started"
                        elif is_over:
                            status = "Victory" if is_victory else "Game Over"
                        else:
                            status = "In Progress"
                            
                    else:
                        status = "Not Started"
            except Exception:
                status = "Corrupted History"
        else:
            status = "Not Started"

        # Create a "Search Blob": a hidden field containing all metadata for fast searching
        search_parts = [
            data.get("title", ""),
            data.get("author", ""),
            data.get("tone", ""),
            data.get("goal", ""),
            data.get("lore_and_rules", ""),
            folder_path.name
        ]
        search_blob = " ".join(filter(None, search_parts)).lower()

        return {
            "folder_name": rel_path, # This guarantees deep paths like 'Fantasy/Epic/MyStory' are preserved
            "title": data.get("title", folder_path.name),
            "author": data.get("author", "Unknown"),
            "version": data.get("version", "1.0"),
            "creation_date": data.get("creation_date", "Unknown"),
            "mode": data.get("mode", "unknown"),
            "turns": turns,
            "location": location,
            "status": status,
            "search_blob": search_blob,
            "path": str(folder_path.resolve())
        }

    @staticmethod
    def get_available_stories():
        """
        High-Performance Loader: Uses OS file timestamps to selectively read 
        only updated JSON files, caching the rest in index.json.
        """
        ADV_DIR.mkdir(parents=True, exist_ok=True)
        
        # 1. Load the cache
        index_data = {}
        if INDEX_FILE.exists():
            try:
                with open(INDEX_FILE, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
            except json.JSONDecodeError:
                pass # If corrupted, we just rebuild it automatically
                
        needs_save = False
        current_folders = set()
        
        # 2. Deep Scan OS Directory
        for root, dirs, files in os.walk(ADV_DIR):
            if "setup.json" in files:
                # Convert absolute path to standard forward-slash relative path (e.g. 'Fantasy/MyStory')
                rel_path = Path(root).relative_to(ADV_DIR).as_posix()
                current_folders.add(rel_path)
                
                setup_file = Path(root) / "setup.json"
                history_file = Path(root) / "history.json"
                
                s_mtime = os.path.getmtime(setup_file)
                h_mtime = os.path.getmtime(history_file) if history_file.exists() else 0
                
                cached = index_data.get(rel_path)
                
                if not cached or cached.get("s_mtime") != s_mtime or cached.get("h_mtime") != h_mtime:
                    index_data[rel_path] = {
                        "s_mtime": s_mtime,
                        "h_mtime": h_mtime,
                        "meta": TomeWeaverAPI._extract_story_metadata(Path(root), rel_path)
                    }
                    needs_save = True
                
                # CRITICAL: Do not traverse deeper into an active story cartridge
                dirs.clear()

        # 3. Clean up deleted folders from the index
        keys_to_remove = [k for k in index_data.keys() if k not in current_folders]
        for k in keys_to_remove:
            del index_data[k]
            needs_save = True
            
        # 4. Save cache if changes occurred
        if needs_save:
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index_data, f, indent=4)
                
        # Extract metadata dictionaries and sort
        stories = [entry["meta"] for entry in index_data.values()]
        return sorted(stories, key=lambda x: x["title"].lower())

    # ---------------------------------------------------------
    # STORY MANAGEMENT ENDPOINTS
    # ---------------------------------------------------------

    @staticmethod
    def create_story(title, author, mode, rules_cfg=None, parent_dir="", extra_data=None):
        """Creates a new boilerplate adventure folder and applies mechanical rules."""
        safe_title = sanitize_foldername(title)
        if not safe_title: return False, "Invalid title. Contains illegal characters."
            
        target_dir = ADV_DIR / parent_dir / safe_title
        if target_dir.exists(): return False, f"A story folder named '{safe_title}' already exists."
            
        try:
            target_dir.mkdir(parents=True)
            create_boilerplate_files(target_dir, mode)
            
            setup_file = target_dir / "setup.json"
            if setup_file.exists():
                with open(setup_file, "r", encoding="utf-8") as f:
                    setup_data = json.load(f)
                setup_data["title"] = title
                setup_data["author"] = author.strip() if author.strip() else "Anonymous"
                setup_data["version"] = "1.0"
                setup_data["creation_date"] = datetime.datetime.now().strftime("%Y-%m-%d")
                
                if rules_cfg:
                    setup_data["track_inventory"] = rules_cfg.get("track_inventory", False)
                    setup_data["can_die"] = rules_cfg.get("can_die", False)
                    setup_data["allow_cheats"] = rules_cfg.get("allow_cheats", False)
                    
                # Inject the Wizard's narrative answers into the world file
                if extra_data:
                    for k, v in extra_data.items():
                        if v: # Only overwrite if the wizard actually provided content
                            setup_data[k] = v
                            
                with open(setup_file, "w", encoding="utf-8") as f:
                    json.dump(setup_data, f, indent=4)
                    
            return True, (Path(parent_dir) / safe_title).as_posix()
            
        except Exception as e:
            return False, str(e)

    # ---------------------------------------------------------
    # ZIP CARTRIDGE SYSTEM
    # ---------------------------------------------------------

    @staticmethod
    def export_to_zip(folder_name, target_zip_path):
        source_dir = ADV_DIR / folder_name
        if not source_dir.exists(): return False, "Story folder not found."
        try:
            with zipfile.ZipFile(target_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(source_dir):
                    for file in files:
                        if file == "index.json": continue # Never export the index
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        zipf.write(file_path, arcname)
            return True, "Export successful."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def import_from_zip(zip_path):
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                files = zipf.namelist()
                has_setup = any(f.endswith('setup.json') for f in files)
                has_prompt = any(f.endswith('system_prompt.txt') for f in files)
                if not (has_setup and has_prompt):
                    return False, "Invalid Cartridge: Missing setup.json or system_prompt.txt"
                    
                setup_path = next(f for f in files if f.endswith('setup.json'))
                nested_folder = os.path.dirname(setup_path)
                
                setup_data = json.loads(zipf.read(setup_path).decode('utf-8'))
                title = setup_data.get("title", "Imported Story")
                safe_title = sanitize_foldername(title)
                if not safe_title: safe_title = "Imported_Story"
                
                target_dir = ADV_DIR / safe_title
                counter = 1
                while target_dir.exists():
                    target_dir = ADV_DIR / f"{safe_title} ({counter})"
                    counter += 1
                    
                target_dir.mkdir(parents=True)
                
                for file in files:
                    if file.startswith(nested_folder) and not file.endswith('/'):
                        rel_name = os.path.relpath(file, nested_folder) if nested_folder else file
                        if rel_name == "index.json": continue # Don't import alien indexes
                        target_file = target_dir / rel_name
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        with zipf.open(file) as source, open(target_file, "wb") as target:
                            shutil.copyfileobj(source, target)
                            
            return True, target_dir.name
        except zipfile.BadZipFile: return False, "Invalid or corrupted zip file."
        except Exception as e: return False, str(e)

    @staticmethod
    def restart_story(folder_name):
        """Headless Reset: Wipes history and resets chapters without loading the full engine."""
        target_dir = ADV_DIR / folder_name
        history_file = target_dir / "history.json"
        chapters_file = target_dir / "chapters.json"
        setup_file = target_dir / "setup.json"
        log_file = target_dir / "session_log.txt"

        try:
            # 1. Wipe History
            if history_file.exists():
                with open(history_file, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=4)

            # 2. Reset Chapters
            if setup_file.exists():
                with open(setup_file, "r", encoding="utf-8") as f:
                    setup_data = json.load(f)
                
                mode = setup_data.get("mode", "sandbox").lower()
                if mode == "campaign":
                    outline = setup_data.get("plot_outline", [])
                    if outline:
                        first = outline[0]
                        
                        # Build initial objectives array with ACTIVE/LOCKED statuses
                        objs = []
                        for i, o in enumerate(first.get("objectives", [])):
                            o_copy = o.copy()
                            o_copy["status"] = "ACTIVE" if i == 0 else "LOCKED"
                            objs.append(o_copy)
                            
                        initial = [{
                            "chapter_number": 1, "title": first.get("title", "Chapter 1"),
                            "start_turn": 1, "end_turn": None, 
                            "objectives": objs
                        }]
                else:
                    initial = [{
                        "chapter_number": 1, "title": setup_data.get("title", "Chapter 1"),
                        "start_turn": 1, "end_turn": None
                    }]
                
                with open(chapters_file, "w", encoding="utf-8") as f:
                    json.dump(initial, f, indent=4)

            # 3. Flush Log
            # 3. Flush Log
            if log_file.exists(): log_file.unlink()

            return True, "Story reset to Turn 0."
        except Exception as e:
            return False, str(e)
            
    @staticmethod
    def delete_story(folder_name):
        """Permanently deletes an adventure directory."""
        target_dir = ADV_DIR / folder_name
        if target_dir.exists() and target_dir.is_dir():
            try:
                shutil.rmtree(target_dir)
                return True, "Story deleted."
            except Exception as e:
                return False, str(e)
        return False, "Story not found."
        
    @staticmethod
    def rename_story(folder_name, new_title):
        """Safely renames both the physical folder and the JSON title property."""
        import shutil
        source_dir = ADV_DIR / folder_name
        if not source_dir.exists(): return False, "Story not found."
        
        safe_new = sanitize_foldername(new_title)
        
        # FIX: Keep the story in its current sub-directory, do not move it to root
        target_dir = source_dir.parent / safe_new
        
        try:
            # Allow case-only renames (e.g. "test" -> "Test") without triggering a collision
            is_case_change = (source_dir.name.lower() == safe_new.lower())
            
            if not is_case_change and target_dir.exists():
                return False, f"A folder named '{safe_new}' already exists in this location."
                
            if source_dir.name != safe_new:
                # Robust Rename: Fallback to deep copy if OS denies the atomic rename
                try:
                    source_dir.rename(target_dir)
                except PermissionError:
                    import time
                    time.sleep(0.5) # Wait for OS handles to drop
                    try:
                        source_dir.rename(target_dir)
                    except PermissionError:
                        shutil.copytree(source_dir, target_dir)
                        shutil.rmtree(source_dir)
            
            setup_file = target_dir / "setup.json"
            if setup_file.exists():
                with open(setup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["title"] = new_title
                with open(setup_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                    
            # CRITICAL FIX: Return the full relative path so nested folders can be reopened by the UI
            return True, target_dir.relative_to(ADV_DIR).as_posix()
        except Exception as e:
            return False, str(e)
            
    @staticmethod
    def move_story(folder_name, new_parent_dir):
        """Moves a story folder to a new directory within the adventures root."""
        import shutil
        source_dir = ADV_DIR / folder_name
        if not source_dir.exists(): return False, "Story not found."
        
        target_parent = ADV_DIR / new_parent_dir
        if not target_parent.exists():
            target_parent.mkdir(parents=True, exist_ok=True)
            
        story_basename = os.path.basename(folder_name)
        target_dir = target_parent / story_basename
        
        if source_dir.resolve() == target_dir.resolve():
            return False, "The story is already in that folder."
            
        if target_dir.exists(): 
            return False, f"A folder named '{story_basename}' already exists in the destination."
        
        try:
            # Fallback to copy/delete if atomic rename fails
            try:
                source_dir.rename(target_dir)
            except PermissionError:
                import time
                time.sleep(0.5)
                shutil.copytree(source_dir, target_dir)
                shutil.rmtree(source_dir)
                
            return True, target_dir.relative_to(ADV_DIR).as_posix()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def create_story_from_prompt(title, author, mode, prompt_text, gen_pro, gen_epi, rules_cfg=None, parent_dir=""):
        """
        AI World Generator. Contacts the LLM to dynamically generate the world data,
        extracts the title, safely creates the folder, and populates the schema files.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json
        import requests, re, time
        
        sys_prompt = PROMPTS.get("SYS_WORLD_GEN", "")
        
        # 1. Build the strict JSON schema request dynamically based on user inputs
        schema = "{\n"
        if not title:
            schema += '  "title": "A catchy, compelling title for this adventure",\n'
            
        schema += '  "tone": "Brief description of the atmosphere and genre",\n'
        schema += '  "main_character": "Name, age, and brief personality traits",\n'
        schema += '  "lore_and_rules": "Key facts about the world, magic, or technology",\n'
        
        if mode == "sandbox":
            schema += '  "setting": "Detailed description of the starting location",\n'
            schema += '  "starting_situation": "The exact situation the player wakes up in",\n'
            schema += '  "goal": "A loose overarching motivation for the character",\n'
            
        if rules_cfg and rules_cfg.get("track_inventory"):
            schema += '  "inventory_dictionary": {"Health": {"val": "Good", "icon": "❤️", "color": "#B71C1C"}, "Items": {"val": "Rusty Dagger", "icon": "🎒", "color": "#1F6AA5"}},\n'
            
        if mode == "campaign":
            schema += '  "plot_outline": [\n    {\n      "title": "Chapter 1",\n      "setting": "Base chapter location",\n      "pov": "Main Character",\n      "objectives": [\n        {"goal": "Step 1 micro-objective", "obstacles": "Specific threats", "setting": "Specific location", "pov": "POV"},\n        {"goal": "Step 2 micro-objective", "obstacles": "Specific threats", "setting": "Next location", "pov": "POV"}\n      ]\n    }\n  ],\n'
            
        if gen_pro: schema += '  "prologue_text": "Write 3 to 4 paragraphs of rich, cinematic opening prose setting the scene",\n'
        if gen_epi and mode == "campaign": schema += '  "epilogue_text": "Write 2 to 3 paragraphs of satisfying concluding prose"\n'
            
        schema = schema.rstrip(",\n") + "\n}"
        
        # Safe String Replacement to avoid JSON brace conflicts
        title_str = f"TITLE: {title}\n" if title else ""
        user_msg = PROMPTS.get("USER_WORLD_GEN", "")
        user_msg = user_msg.replace("{mode}", mode.upper())
        user_msg = user_msg.replace("{prompt_text}", prompt_text)
        user_msg = user_msg.replace("{title}", title_str)
        user_msg = user_msg.replace("{schema}", schema)
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip():
            headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        max_retries = ENGINE_CONFIG.get("max_retries", 5)
        active_messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg}
        ]
        
        data = None
        err = None
        
        # 2. Call the API with the Fortress Retry Loop
        for attempt in range(max_retries):
            if attempt > 0 and err:
                active_messages.append({"role": "user", "content": f"Your previous JSON was invalid. Error: {err}. Please correct it and return ONLY valid JSON."})
                
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": active_messages,
                "temperature": max(0.2, 0.8 - (attempt * 0.15)),
                "max_tokens": 3000
            }
            
            try:
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=120)
                if resp.status_code != 200:
                    err = f"API Error {resp.status_code}"
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if not match:
                    err = "No JSON object found."
                    continue
                    
                clean_json = sanitize_json(match.group(0))
                data = json.loads(clean_json, strict=False)
                
                if mode == "campaign" and not isinstance(data.get("plot_outline"), list):
                    err = "'plot_outline' must be a JSON array."
                    data = None
                    continue
                    
                break # Success!
                
            except Exception as e:
                err = str(e)
                time.sleep(1)
                continue

        if not data:
            return False, f"Failed to generate world after {max_retries} attempts. Last error: {err}"
            
        try:
            # 3. Secure the Title & Create Folder
            raw_title = title.strip() if title and title.strip() else data.get("title", "Generated Adventure").strip()
            
            from api import sanitize_foldername
            if not sanitize_foldername(raw_title):
                raw_title = "AI Generated Adventure"
                
            final_title = raw_title
            base_title = raw_title
            counter = 1
            
            while (ADV_DIR / parent_dir / sanitize_foldername(final_title)).exists():
                final_title = f"{base_title} {counter}"
                counter += 1
                
            # Pass the mechanical rules directly into the base builder so setup.json is perfectly formatted from the start
            success, folder_or_err = TomeWeaverAPI.create_story(final_title, author, mode, rules_cfg, parent_dir)
            if not success: return False, f"Could not create folder: {folder_or_err}"
            
            folder_name = folder_or_err
            target_dir = ADV_DIR / folder_name

            # 4. Apply to setup.json
            setup_file = target_dir / "setup.json"
            with open(setup_file, "r", encoding="utf-8") as f:
                setup_data = json.load(f)
                
            keys_to_merge = ["title", "tone", "main_character", "lore_and_rules", "setting", "starting_situation", "goal", "inventory_and_state", "plot_outline"]
            for k in keys_to_merge:
                if k in data:
                    # Defensive cast: If the AI hallucinates a list/dict for a string field, flatten it so the UI doesn't crash
                    if isinstance(data[k], (dict, list)) and k != "plot_outline":
                        setup_data[k] = json.dumps(data[k])
                    else:
                        setup_data[k] = data[k]
                
            # 5. Handle Narrative Text Files (Robust string casting)
            if gen_pro and data.get("prologue_text"):
                pro_data = data["prologue_text"]
                pro_str = "\n\n".join([str(p) for p in pro_data]) if isinstance(pro_data, list) else str(pro_data)
                if pro_str.strip():
                    with open(target_dir / "prologue.txt", "w", encoding="utf-8") as f:
                        f.write(pro_str.strip())
                    setup_data.setdefault("narrative", {})["prologue"] = "as_is"
                
            if gen_epi and mode == "campaign" and data.get("epilogue_text"):
                epi_data = data["epilogue_text"]
                epi_str = "\n\n".join([str(e) for e in epi_data]) if isinstance(epi_data, list) else str(epi_data)
                if epi_str.strip():
                    with open(target_dir / "epilogue.txt", "w", encoding="utf-8") as f:
                        f.write(epi_str.strip())
                    setup_data.setdefault("narrative", {})["epilogue"] = "as_is"
                
            with open(setup_file, "w", encoding="utf-8") as f:
                json.dump(setup_data, f, indent=4)
                
            # 6. Initialize chapters.json if Campaign Mode
            if mode == "campaign" and "plot_outline" in data:
                chapters_file = target_dir / "chapters.json"
                first_chap = data["plot_outline"][0] if data["plot_outline"] else {}
                
                # Build initial objectives array with ACTIVE/LOCKED statuses
                objs = []
                for i, o in enumerate(first_chap.get("objectives", [])):
                    o_copy = o.copy()
                    o_copy["status"] = "ACTIVE" if i == 0 else "LOCKED"
                    objs.append(o_copy)
                
                initial_chapters = [{
                    "chapter_number": 1,
                    "title": first_chap.get("title", "Chapter 1"),
                    "start_turn": 1, "end_turn": None,
                    "objectives": objs
                }]
                with open(chapters_file, "w", encoding="utf-8") as f:
                    json.dump(initial_chapters, f, indent=4)
                    
            return True, folder_name
            
        except Exception as e:
            # CRITICAL FIX: Ensure we use the exact folder_name variable to clean up the bad generation
            TomeWeaverAPI.delete_story(folder_name) 
            return False, f"File Generation Failed: {str(e)}"


    @staticmethod
    def generate_field_data(setup_data, field_name, shorthand=None):
        """
        AI Field Generator for the World Builder UI.
        If 'shorthand' is provided, it acts as an "Inspire/Expand" tool.
        If 'shorthand' is None, it acts as a "Blank Slate Reroll" tool.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import enforce_rate_limit
        import requests, time
        
        # 1. Build World Context from existing setup data
        # We only feed the AI the most critical narrative fields so it understands the vibe.
        context_parts = []
        for key in ["title", "tone", "main_character", "setting", "goal", "lore_and_rules"]:
            val = setup_data.get(key)
            if val and isinstance(val, str) and val.strip():
                context_parts.append(f"{key.replace('_', ' ').title()}: {val.strip()}")
                
        context_str = "\n".join(context_parts) if context_parts else "A brand new, undefined world."
        
        # Determine the correct length constraint based on the UI field
        if field_name == "title":
            length_constraint = "Write ONLY a short, punchy title (Max 10 words). Do not use quotes"
        elif field_name == "tone":
            length_constraint = "Write a comma-separated list of atmospheric keywords or a single brief sentence"
        elif field_name == "goal":
            length_constraint = "Write exactly one concise sentence describing the main objective"
        else:
            length_constraint = "Write 1 to 3 rich, descriptive paragraphs"

        # 2. Select Prompt based on mode
        sys_prompt = PROMPTS.get("SYS_FIELD_GEN", "")
        
        if shorthand and shorthand.strip():
            user_prompt = PROMPTS.get("USER_FIELD_INSPIRE", "")
            user_prompt = user_prompt.replace("{context}", context_str)
            user_prompt = user_prompt.replace("{field_name}", field_name)
            user_prompt = user_prompt.replace("{shorthand}", shorthand.strip())
            user_prompt = user_prompt.replace("{length_constraint}", length_constraint)
        else:
            user_prompt = PROMPTS.get("USER_FIELD_REROLL", "")
            user_prompt = user_prompt.replace("{context}", context_str)
            user_prompt = user_prompt.replace("{field_name}", field_name)
            user_prompt = user_prompt.replace("{length_constraint}", length_constraint)
            
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip():
            headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        # 3. Call LLM
        max_retries = 3
        for attempt in range(max_retries):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 1000
            }
            
            try:
                from llm import enforce_rate_limit, translate_api_error
                enforce_rate_limit()
                
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=60)
                if resp.status_code != 200:
                    err = translate_api_error(response=resp)
                    time.sleep(2)
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                
                raw = raw.strip('"\'')
                if raw.lower().startswith("here is"): raw = raw.split("\n", 1)[-1].strip()
                
                import re
                raw = re.sub(r'^(Title|Tone|Goal|Setting|Main Character):\s*', '', raw, flags=re.IGNORECASE).strip('"\'')
                    
                return True, raw
                
            except Exception as e:
                from llm import translate_api_error
                err = translate_api_error(exception=e)
                time.sleep(2)
                continue
                
        return False, f"Generation failed.\nReason: {err}"
        
     
    @staticmethod
    def generate_schema_data(setup_data, schema_type, field_name="", shorthand=None):
        """
        AI Schema Generator. Returns complex JSON objects (Dicts, Lists) instead of raw strings.
        schema_type: "inventory", "list", or "dict"
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit
        import requests, time, json
        
        # 1. Build Context
        context_parts = []
        for key in ["title", "tone", "main_character", "setting", "goal", "lore_and_rules"]:
            val = setup_data.get(key)
            if val and isinstance(val, str) and val.strip():
                context_parts.append(f"{key.replace('_', ' ').title()}: {val.strip()}")
        context_str = "\n".join(context_parts) if context_parts else "A brand new, undefined world."
        
        # 2. Route Prompt
        sys_prompt = PROMPTS.get("SYS_SCHEMA_GEN", "")
        shorthand_str = shorthand.strip() if shorthand else "Invent something creative and fitting."
        
        if schema_type == "inventory":
            if shorthand:
                user_prompt = PROMPTS.get("USER_INV_INSPIRE", "")
            else:
                user_prompt = PROMPTS.get("USER_INV_REROLL", "")
        elif schema_type == "list":
            user_prompt = PROMPTS.get("USER_LIST_GEN", "")
        elif schema_type == "dict":
            user_prompt = PROMPTS.get("USER_DICT_GEN", "")
        else:
            return False, "Invalid schema type requested."
            
        user_prompt = user_prompt.replace("{context}", context_str)
        user_prompt = user_prompt.replace("{field_name}", field_name)
        user_prompt = user_prompt.replace("{shorthand}", shorthand_str)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip():
            headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        # 3. Call LLM with Fortress Parsing
        err = "Unknown error."
        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1500
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=60)
                if resp.status_code != 200:
                    from llm import translate_api_error
                    err = translate_api_error(response=resp)
                    time.sleep(2)
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                clean_json = sanitize_json(raw)
                data = json.loads(clean_json, strict=False)
                
                # Basic Validation
                if schema_type == "list" and isinstance(data, list): return True, data
                if schema_type in ["dict", "inventory"] and isinstance(data, dict): return True, data
                
                err = "The AI returned the wrong JSON data type."
                time.sleep(1)
                
            except Exception as e:
                from llm import translate_api_error
                err = translate_api_error(exception=e)
                time.sleep(2)
                continue
                
        return False, f"Failed to generate JSON schema.\nReason: {err}"


    @staticmethod
    def generate_chapter_data(setup_data, prev_chapter=None, shorthand=None):
        """
        AI Full Chapter Generator.
        Contextually aware of the previous chapter to maintain sequential plot pacing.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit
        import requests, time, json
        
        # 1. Build Global Context
        context_parts = []
        for key in ["title", "tone", "main_character", "setting", "goal", "lore_and_rules"]:
            val = setup_data.get(key)
            if val and isinstance(val, str) and val.strip():
                context_parts.append(f"{key.replace('_', ' ').title()}: {val.strip()}")
        context_str = "\n".join(context_parts) if context_parts else "A brand new, undefined world."
        
        # 2. Build Previous Chapter Context
        prev_str = ""
        if prev_chapter:
            prev_str = "PREVIOUS CHAPTER CONTEXT:\n"
            for k in ["title", "setting", "objectives"]:
                if prev_chapter.get(k): prev_str += f"{k.title()}: {prev_chapter[k]}\n"

        sys_prompt = PROMPTS.get("SYS_CHAP_GEN", "You are an expert campaign writer. Output ONLY a flat JSON Dictionary matching the chapter schema.")
        # Explicitly mandate the Sequential Array format so it generates 2 to 4 micro-objectives
        sys_prompt += '\n\nREQUIRED FORMAT:\n{\n  "title": "Chapter Title",\n  "setting": "Base Location",\n  "pov": "POV",\n  "time": "Time jump",\n  "objectives": [\n    {"goal": "Step 1 micro-objective", "obstacles": "Threats", "setting": "Location", "pov": "POV"},\n    {"goal": "Step 2 micro-objective", "obstacles": "Threats", "setting": "Location", "pov": "POV"}\n  ]\n}\nNOTE: You MUST provide 2 to 4 sequential micro-objectives.'
        
        shorthand_str = shorthand.strip() if shorthand else "Advance the plot naturally based on the previous chapter."
        
        user_prompt = PROMPTS.get("USER_CHAP_GEN", "")
        user_prompt = user_prompt.replace("{context}", context_str)
        user_prompt = user_prompt.replace("{prev_chap_context}", prev_str)
        user_prompt = user_prompt.replace("{shorthand}", shorthand_str)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"), 
                "messages": messages, 
                "temperature": 0.8, 
                "max_tokens": 1000
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=60)
                if resp.status_code != 200:
                    from llm import translate_api_error
                    err = translate_api_error(response=resp)
                    time.sleep(2)
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                clean_json = sanitize_json(raw)
                data = json.loads(clean_json, strict=False)
                
                if isinstance(data, dict): return True, data
                
                err = "The AI did not output a valid JSON Dictionary."
                time.sleep(1)
            except Exception as e:
                from llm import translate_api_error
                err = translate_api_error(exception=e)
                time.sleep(2)
                continue
                
        return False, f"Failed to generate chapter.\nReason: {err}"
        
    @staticmethod
    def overhaul_active_story(engine, prompt_text, gen_pro, gen_epi):
        """
        AI Overhaul Generator. Dynamically generates world data and safely injects 
        it directly into an already-loaded engine's setup_data without touching the physical folder.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json
        import requests, re, time
        
        sys_prompt = PROMPTS.get("SYS_WORLD_GEN", "")
        mode = engine.setup_data.get("mode", "sandbox")
        
        # 1. Build the strict JSON schema request dynamically
        schema = "{\n"
        schema += '  "tone": "Brief description of the atmosphere and genre",\n'
        schema += '  "main_character": "Name, age, and brief personality traits",\n'
        schema += '  "lore_and_rules": "Key facts about the world, magic, or technology",\n'
        
        if mode == "sandbox":
            schema += '  "setting": "Detailed description of the starting location",\n'
            schema += '  "starting_situation": "The exact situation the player wakes up in",\n'
            schema += '  "goal": "A loose overarching motivation for the character",\n'
            
        if engine.setup_data.get("track_inventory"):
            schema += '  "inventory_dictionary": {"Health": {"val": "Good", "icon": "❤️", "color": "#B71C1C"}, "Items": {"val": "Rusty Dagger", "icon": "🎒", "color": "#1F6AA5"}},\n'
            
        if mode == "campaign":
            schema += '  "plot_outline": [\n    {\n      "title": "Chapter 1",\n      "setting": "Base chapter location",\n      "pov": "Main Character",\n      "objectives": [\n        {"goal": "Step 1 micro-objective", "obstacles": "Specific threats", "setting": "Specific location", "pov": "POV"},\n        {"goal": "Step 2 micro-objective", "obstacles": "Specific threats", "setting": "Next location", "pov": "POV"}\n      ]\n    }\n  ],\n'
            
        if gen_pro: schema += '  "prologue_text": "Write 3 to 4 paragraphs of rich, cinematic opening prose setting the scene",\n'
        if gen_epi and mode == "campaign": schema += '  "epilogue_text": "Write 2 to 3 paragraphs of satisfying concluding prose"\n'
            
        schema = schema.rstrip(",\n") + "\n}"
        
        title_str = f"TITLE: {engine.setup_data.get('title', 'Adventure')}\n"
        user_msg = PROMPTS.get("USER_WORLD_GEN", "")
        user_msg = user_msg.replace("{mode}", mode.upper())
        user_msg = user_msg.replace("{prompt_text}", prompt_text)
        user_msg = user_msg.replace("{title}", title_str)
        user_msg = user_msg.replace("{schema}", schema)
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip():
            headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        active_messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}]
        
        data = None
        err = None
        
        for attempt in range(3):
            if attempt > 0 and err:
                active_messages.append({"role": "user", "content": f"Invalid JSON. Error: {err}. Please return valid JSON."})
                
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": active_messages,
                "temperature": 0.8,
                "max_tokens": 3000
            }
            
            try:
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=120)
                if resp.status_code != 200:
                    err = f"API Error {resp.status_code}"
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if not match:
                    err = "No JSON object found."
                    continue
                    
                clean_json = sanitize_json(match.group(0))
                data = json.loads(clean_json, strict=False)
                break 
                
            except Exception as e:
                err = str(e)
                time.sleep(1)
                continue

        if not data:
            return False, f"Failed to generate world overhaul. Last error: {err}"
            
        try:
            # 2. Inject directly into the engine's active memory
            keys_to_merge = ["tone", "main_character", "lore_and_rules", "setting", "starting_situation", "goal", "inventory_dictionary", "plot_outline"]
            for k in keys_to_merge:
                if k in data:
                    if isinstance(data[k], (dict, list)) and k not in ["plot_outline", "inventory_dictionary"]:
                        engine.setup_data[k] = json.dumps(data[k])
                    else:
                        engine.setup_data[k] = data[k]
                
            # 3. Handle Narrative Text Files
            if gen_pro and data.get("prologue_text"):
                pro_str = "\n\n".join([str(p) for p in data["prologue_text"]]) if isinstance(data["prologue_text"], list) else str(data["prologue_text"])
                if pro_str.strip():
                    with open(engine.adv_dir / "prologue.txt", "w", encoding="utf-8") as f:
                        f.write(pro_str.strip())
                    engine.setup_data.setdefault("narrative", {})["prologue"] = "as_is"
                    engine.prologue_content = pro_str.strip()
                
            if gen_epi and mode == "campaign" and data.get("epilogue_text"):
                epi_str = "\n\n".join([str(e) for e in data["epilogue_text"]]) if isinstance(data["epilogue_text"], list) else str(data["epilogue_text"])
                if epi_str.strip():
                    with open(engine.adv_dir / "epilogue.txt", "w", encoding="utf-8") as f:
                        f.write(epi_str.strip())
                    engine.setup_data.setdefault("narrative", {})["epilogue"] = "as_is"
                    engine.epilogue_content = epi_str.strip()
                
            from config import save_json_atomically
            
            # 4. Save setup_data
            setup_file = engine.adv_dir / "setup.json"
            save_json_atomically(engine.setup_data, setup_file)
                
            # 5. Overwrite chapters.json if Campaign Mode
            if mode == "campaign" and "plot_outline" in data:
                chapters_file = engine.adv_dir / "chapters.json"
                first_chap = data["plot_outline"][0] if data["plot_outline"] else {}
                
                # Build initial objectives array with ACTIVE/LOCKED statuses
                objs = []
                for i, o in enumerate(first_chap.get("objectives", [])):
                    o_copy = o.copy()
                    o_copy["status"] = "ACTIVE" if i == 0 else "LOCKED"
                    objs.append(o_copy)
                    
                engine.chapters = [{
                    "chapter_number": 1,
                    "title": first_chap.get("title", "Chapter 1"),
                    "start_turn": 1, "end_turn": None,
                    "objectives": objs
                }]
                save_json_atomically(engine.chapters, chapters_file)
                    
            return True, ""
            
        except Exception as e:
            return False, f"Failed to apply overhaul: {str(e)}"
            
    @staticmethod
    def autofill_inventory_styles(inventory_dict):
        """
        Scans an inventory dictionary for empty icons or colors and asks the AI to 
        intelligently guess fitting emojis and hex codes based on the keys and values.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit
        import requests, time, json
        
        sys_prompt = PROMPTS.get("SYS_SCHEMA_GEN", "You are an expert game designer. Output ONLY valid JSON.")
        user_prompt = PROMPTS.get("USER_AUTO_STYLE", "")
        user_prompt = user_prompt.replace("{inventory_json}", json.dumps(inventory_dict, indent=2))

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip():
            headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(2):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages,
                "temperature": 0.3, # Low temp so it just fixes the formatting reliably
                "max_tokens": 500
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    if isinstance(data, dict):
                        return True, data
            except Exception:
                time.sleep(1)
                
        return False, inventory_dict
        
    @staticmethod
    def browse_path(rel_path):
        """Opens the physical OS File Explorer at the target directory."""
        import platform, subprocess
        target = ADV_DIR / rel_path
        if not target.exists(): target = ADV_DIR # Fallback to root
        try:
            if platform.system() == "Windows": os.startfile(target)
            elif platform.system() == "Darwin": subprocess.Popen(["open", target])
            else: subprocess.Popen(["xdg-open", target])
            return True, ""
        except Exception as e:
            return False, str(e)

    @staticmethod
    def create_folder(parent_dir, folder_name):
        """Creates an empty physical directory."""
        safe_name = sanitize_foldername(folder_name)
        if not safe_name: return False, "Invalid folder name."
        target = ADV_DIR / parent_dir / safe_name
        if target.exists(): return False, "Folder already exists."
        try:
            target.mkdir(parents=True, exist_ok=True)
            return True, safe_name
        except Exception as e:
            return False, str(e)

    @staticmethod
    def rename_folder(rel_path, new_name):
        """Renames a physical directory and all contents inside it."""
        source_dir = ADV_DIR / rel_path
        if not source_dir.exists(): return False, "Folder not found."
        safe_new = sanitize_foldername(new_name)
        if not safe_new: return False, "Invalid name."
        target_dir = source_dir.parent / safe_new
        
        is_case_change = (source_dir.name.lower() == safe_new.lower())
        if not is_case_change and target_dir.exists(): 
            return False, f"A folder named '{safe_new}' already exists."
            
        try:
            source_dir.rename(target_dir)
            return True, target_dir.relative_to(ADV_DIR).as_posix()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_folder(rel_path):
        """Recursively deletes a folder and everything inside it."""
        source_dir = ADV_DIR / rel_path
        if not source_dir.exists(): return False, "Folder not found."
        try:
            shutil.rmtree(source_dir)
            return True, ""
        except Exception as e:
            return False, str(e)

    @staticmethod
    def move_folder(rel_path, new_parent_dir):
        """Moves a physical container folder to a new directory within the adventures root."""
        import shutil
        source_dir = ADV_DIR / rel_path
        if not source_dir.exists(): return False, "Folder not found."
        
        target_parent = ADV_DIR / new_parent_dir
        if not target_parent.exists():
            target_parent.mkdir(parents=True, exist_ok=True)
            
        folder_basename = os.path.basename(rel_path)
        target_dir = target_parent / folder_basename
        
        if source_dir.resolve() == target_dir.resolve():
            return False, "The folder is already in that location."
            
        if target_dir.exists(): 
            return False, f"A folder named '{folder_basename}' already exists in the destination."
        
        try:
            try:
                source_dir.rename(target_dir)
            except PermissionError:
                import time
                time.sleep(0.5)
                shutil.copytree(source_dir, target_dir)
                shutil.rmtree(source_dir)
                
            return True, target_dir.relative_to(ADV_DIR).as_posix()
        except Exception as e:
            return False, str(e)

    # ---------------------------------------------------------
    # ENGINE LAUNCHER
    # ---------------------------------------------------------

    @staticmethod
    def load_engine(folder_name):
        target_dir = ADV_DIR / folder_name
        setup_file = target_dir / "setup.json"
        if not setup_file.exists(): raise FileNotFoundError(f"setup.json missing from '{folder_name}'.")
            
        from config import load_json_safely
        setup_data = load_json_safely(setup_file, "setup.json")
        mode = setup_data.get("mode", "sandbox").lower()
        
        if mode == "campaign": return CampaignEngine(target_dir, setup_data)
        else: return SandboxEngine(target_dir, setup_data)
        
        
        
    @staticmethod
    def edit_narrative_bridge(engine, turn_idx, bridge_text, edit_type):
        """
        AI Bridge Editor.
        Specifically handles Polish, Condense, and Expand actions for transition sentences.
        Provides the LLM with massive Continuity Context (Prev Scene, Action, Next Scene, and RAG Lore).
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import enforce_rate_limit
        import requests, time
        
        sys_prompt = PROMPTS.get("SYS_BRIDGE_EDIT", "")
        
        turn_obj = engine.history[turn_idx]
        prev_obj = engine.history[turn_idx - 1] if turn_idx > 0 else None
        
        # --- ASSEMBLE THE MASSIVE CONTINUITY SANDWICH ---
        context = "--- CONTEXT FOR CONTINUITY (DO NOT REWRITE THESE) ---\n"
        context += f"POV CHARACTER: {turn_obj.get('pov_character', 'Unknown')}\n"
        context += f"LOCATION: {turn_obj.get('location', 'Unknown')}\n"
        context += f"MAIN CHARACTER LORE: {engine.setup_data.get('main_character', 'Unknown')}\n\n"
        
        # Inject RAG Characters so the AI knows genders, relationships, and physical states
        chars = engine.memory.get("character_ledger", {})
        if chars:
            context += "KNOWN CHARACTERS IN WORLD:\n"
            for k, data in chars.items():
                if isinstance(data, dict) and data.get("state") != "archived":
                    traits = ", ".join([f"{tk}: {tv}" for tk, tv in data.get("characteristics", {}).items()])
                    context += f"- {k} (Traits: {traits})\n"
            context += "\n"
            
        if prev_obj:
            context += f"PREVIOUS SCENE:\n{prev_obj.get('story_text', '')}\n\n"
            context += f"ACTION TAKEN BY PLAYER:\n{prev_obj.get('player_choice', '')}\n\n"
            
        context += f"NEXT SCENE (The result of the action):\n{turn_obj.get('story_text', '')}\n"
        context += "-----------------------------------------------------\n\n"
        
        if edit_type == "polish":
            user_prompt = PROMPTS.get("USER_BRIDGE_POLISH", "").replace("{bridge}", bridge_text)
        elif edit_type == "condense":
            user_prompt = PROMPTS.get("USER_BRIDGE_CONDENSE", "Concisely summarize and shorten this transition sentence:\n'{bridge}'").replace("{bridge}", bridge_text)
        else:
            user_prompt = PROMPTS.get("USER_BRIDGE_EXPAND", "").replace("{bridge}", bridge_text)

        # Prepend the context to the user instruction
        user_prompt = context + user_prompt

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip():
            headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        # Dynamically scale tokens based on the size of the input text
        # 1 word is roughly 1.3 tokens. We add a massive buffer so it never truncates.
        word_count = len(bridge_text.split())
        estimated_input_tokens = int(word_count * 1.5)
        
        if edit_type == "polish":
            # Polish shouldn't add much length, just fix grammar
            dynamic_tokens = max(150, estimated_input_tokens + 200)
        else:
            # Expand needs room to grow significantly
            dynamic_tokens = max(300, estimated_input_tokens + 400)
            
        # Hard cap to prevent runaway billing if using cloud APIs
        dynamic_tokens = min(2000, dynamic_tokens)

        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages,
                "temperature": 0.4 if edit_type == "polish" else 0.7, 
                "max_tokens": dynamic_tokens
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
                if resp.status_code != 200:
                    time.sleep(2)
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                
                # Clean up artifacts
                raw = raw.strip('"\'')
                if raw.lower().startswith("here is"): raw = raw.split("\n", 1)[-1].strip()
                
                return True, raw
                
            except Exception as e:
                time.sleep(2)
                continue
                
        return False, "Failed to edit bridge. Please check API connection."
        
        
    @staticmethod
    def generate_plot_summary(turns_text, start_turn, end_turn, adv_dir=None):
        """
        RAG Phase 1: Compresses a chunk of raw turns into a dense ledger.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import enforce_rate_limit, translate_api_error
        from logger import log_llm_interaction
        import requests, time, uuid
        
        # CACHE BUSTER: Force the local LLM to evaluate this chunk in a sterile vacuum
        sys_prompt = PROMPTS.get("SYS_MEMORY_PLOT", "") + f"\n[ISOLATION_KEY: {uuid.uuid4()}]"
        
        user_prompt = PROMPTS.get("USER_MEMORY_PLOT", "")
        user_prompt = user_prompt.replace("{chunk_text}", turns_text)
        user_prompt = user_prompt.replace("{start_turn}", str(start_turn))
        user_prompt = user_prompt.replace("{end_turn}", str(end_turn))

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        err = "Unknown Error"
        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.4, "max_tokens": ENGINE_CONFIG.get("max_tokens", 5000)
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=120)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    if adv_dir: log_llm_interaction(adv_dir, messages, raw, attempt=attempt+1)
                    raw = raw.strip('"\'')
                    if raw.lower().startswith("here is"): raw = raw.split("\n", 1)[-1].strip()
                    return True, raw
                else:
                    err = translate_api_error(response=resp)
                    if adv_dir: log_llm_interaction(adv_dir, messages, "FAILED", error=err, attempt=attempt+1)
            except Exception as e:
                err = translate_api_error(exception=e)
                if adv_dir: log_llm_interaction(adv_dir, messages, "FAILED", error=err, attempt=attempt+1)
                time.sleep(2)
        return False, f"Summary Generation Failed:\n{err}"



    @staticmethod
    def validate_plot_chunk(raw_text, summary_text, adv_dir=None):
        """
        RAG QA Phase: Audits a single Plot Ledger chunk against its raw turns.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit, translate_api_error
        from logger import log_llm_interaction
        import requests, time, json, uuid
        
        # CACHE BUSTER: Injects a unique ID to force the local LLM to dump its KV cache and evaluate in a sterile vacuum
        sys_prompt = PROMPTS.get("SYS_MEMORY_VALIDATE", "") + f"\n[ISOLATION_KEY: {uuid.uuid4()}]"
        
        user_prompt = PROMPTS.get("USER_MEMORY_VALIDATE", "")
        user_prompt = user_prompt.replace("{raw_text}", raw_text)
        user_prompt = user_prompt.replace("{summary_text}", summary_text)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(2):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.1, "max_tokens": ENGINE_CONFIG.get("max_tokens", 5000)
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    if adv_dir: log_llm_interaction(adv_dir, messages, raw, attempt=attempt+1)
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    if isinstance(data, dict):
                        score = data.get("score", "?/100")
                        report = data.get("report", "No report generated.")
                        return True, f"Fidelity Score: {score}\n\n{report}"
                else:
                    err = translate_api_error(response=resp)
                    if adv_dir: log_llm_interaction(adv_dir, messages, "FAILED", error=err, attempt=attempt+1)
            except Exception as e:
                err = translate_api_error(exception=e)
                if adv_dir: log_llm_interaction(adv_dir, messages, "FAILED", error=err, attempt=attempt+1)
                time.sleep(1)
        return False, "Failed to connect to AI for validation."
        
        
        
        
    @staticmethod
    def patch_plot_chunk(raw_text, summary_text, qa_report, adv_dir=None):
        """
        RAG QA Phase: Asks the LLM to fix a summary based on its own validation report.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import enforce_rate_limit, translate_api_error
        from logger import log_llm_interaction
        import requests, time, uuid
        
        # CACHE BUSTER: Injects a unique ID to force the local LLM to dump its KV cache and evaluate in a sterile vacuum
        sys_prompt = PROMPTS.get("SYS_MEMORY_PATCH", "") + f"\n[ISOLATION_KEY: {uuid.uuid4()}]"
        
        user_prompt = PROMPTS.get("USER_MEMORY_PATCH", "")
        user_prompt = user_prompt.replace("{raw_text}", raw_text)
        user_prompt = user_prompt.replace("{current_summary}", summary_text)
        user_prompt = user_prompt.replace("{qa_report}", qa_report)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        err = "Unknown Error"
        for attempt in range(2):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.2, "max_tokens": ENGINE_CONFIG.get("max_tokens", 5000)
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    if adv_dir: log_llm_interaction(adv_dir, messages, raw, attempt=attempt+1)
                    raw = raw.strip('"\'')
                    if raw.lower().startswith("here is"): raw = raw.split("\n", 1)[-1].strip()
                    return True, raw
                else:
                    err = translate_api_error(response=resp)
                    if adv_dir: log_llm_interaction(adv_dir, messages, "FAILED", error=err, attempt=attempt+1)
            except Exception as e:
                err = translate_api_error(exception=e)
                if adv_dir: log_llm_interaction(adv_dir, messages, "FAILED", error=err, attempt=attempt+1)
                time.sleep(2)
        return False, f"Patching Failed:\n{err}"

        
    @staticmethod
    def generate_chapter_summary(parts_text):
        """
        RAG Phase 1.5: Condenses multiple granular plot_ledger parts into a single Chapter Summary.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import enforce_rate_limit, translate_api_error
        import requests, time
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_CHAPTER", "")
        user_prompt = PROMPTS.get("USER_MEMORY_CHAPTER", "").replace("{parts_text}", parts_text)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        err = "Unknown Error"
        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.3,  "max_tokens": ENGINE_CONFIG.get("max_tokens", 2000)
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    raw = raw.strip('"\'')
                    if raw.lower().startswith("here is"): raw = raw.split("\n", 1)[-1].strip()
                    return True, raw
            except Exception as e:
                err = translate_api_error(exception=e)
                time.sleep(2)
        return False, f"Chapter Condensation Failed:\n{err}"
        
        
    @staticmethod
    def extract_entity_updates(turns_text, known_chars_str, known_locs_str, known_arts_str, known_facs_str="", track_factions=False):
        """
        RAG Phase 2: Extracts new state changes for entities.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit, translate_api_error
        import requests, time, json
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_ENTITY", "")
        if track_factions:
            user_prompt = PROMPTS.get("USER_MEMORY_ENTITY_FACTIONS", "")
            user_prompt = user_prompt.replace("{known_facs}", known_facs_str)
        else:
            user_prompt = PROMPTS.get("USER_MEMORY_ENTITY", "")
            
        user_prompt = user_prompt.replace("{chunk_text}", turns_text)
        user_prompt = user_prompt.replace("{known_chars}", known_chars_str)
        user_prompt = user_prompt.replace("{known_locs}", known_locs_str)
        user_prompt = user_prompt.replace("{known_arts}", known_arts_str)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        err = "Unknown Error"
        for attempt in range(3):
            input_tokens = int(len(turns_text.split()) * 1.5)
            dynamic_limit = min(ENGINE_CONFIG.get("max_tokens", 5000), max(500, input_tokens + 500))
            
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.3, "max_tokens": dynamic_limit
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=120)
                if resp.status_code != 200:
                    err = translate_api_error(response=resp)
                    time.sleep(2)
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                clean_json = sanitize_json(raw)
                data = json.loads(clean_json, strict=False)
                
                # Validation: Ensure it returned the expected root keys
                if isinstance(data, dict):
                    if "Characters" not in data: data["Characters"] = {}
                    if "Locations" not in data: data["Locations"] = {}
                    if "Artifacts" not in data: data["Artifacts"] = {}
                    if track_factions and "Factions" not in data: data["Factions"] = {}
                    return True, data
                    
                err = "AI did not return a valid JSON Dictionary."
                time.sleep(1)
            except Exception as e:
                err = translate_api_error(exception=e)
                time.sleep(2)
                continue
                
        return False, f"Entity Extraction Failed:\n{err}"        
        
        
    @staticmethod
    def reconcile_aliases(entities_context):
        """
        RAG Phase 3: Scans a ledger for obvious duplicates and returns a map of {Alias: Master}.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit
        import requests, time, json
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_RECONCILE", "")
        user_prompt = PROMPTS.get("USER_MEMORY_RECONCILE", "").replace("{entities_context}", entities_context)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(2):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.1, "max_tokens": 500
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    if isinstance(data, dict): return True, data
            except Exception:
                time.sleep(1)
        return False, {}

     
    @staticmethod
    def verify_memory_integrity(plot_context, lore_context):
        """
        RAG Phase 4: Continuity Checker. Reads summaries and lore to find contradictions.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit, translate_api_error
        import requests, time, json
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_VERIFY", "")
        user_prompt = PROMPTS.get("USER_MEMORY_VERIFY", "")
        user_prompt = user_prompt.replace("{plot_context}", plot_context)
        user_prompt = user_prompt.replace("{lore_context}", lore_context)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(2):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.2,  "max_tokens": ENGINE_CONFIG.get("max_tokens", 2000)
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    if isinstance(data, dict):
                        return True, data.get("report", "No report generated.")
            except Exception as e:
                time.sleep(1)
        return False, "Failed to connect to AI for verification."
        
        
    @staticmethod
    def seed_initial_memory(setup_data, track_factions=False):
        """
        RAG Phase 0: Scans the raw setup.json and extracts the baseline entities
        to pre-fill the memory.json file before Turn 1.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit, translate_api_error
        import requests, time, json
        
        # Create a deep copy so we can destructively modify it without harming the active game
        world_doc = json.loads(json.dumps(setup_data))
        
        # Strip all mechanical engine flags and PLOT SPOILERS. The AI only needs static background lore.
        keys_to_remove = ["mode", "track_inventory", "can_die", "tone", "allow_cheats", "narrative", "inventory_dictionary", "plot_outline"]
        for k in keys_to_remove:
            world_doc.pop(k, None)
            
        # Strip empty fields to save tokens
        empty_keys = [k for k, v in world_doc.items() if not v]
        for k in empty_keys:
            world_doc.pop(k, None)
            
        if not world_doc: return False, {}
            
        # Format the remaining dictionary cleanly for the AI to read
        doc_string = json.dumps(world_doc, indent=2)
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_SEED", "")
        if track_factions:
            user_prompt = PROMPTS.get("USER_MEMORY_SEED_FACTIONS", "").replace("{world_doc}", doc_string)
        else:
            user_prompt = PROMPTS.get("USER_MEMORY_SEED", "").replace("{world_doc}", doc_string)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        err = "Unknown Error"
        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.2,  "max_tokens": ENGINE_CONFIG.get("max_tokens", 2000)
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=120)
                if resp.status_code != 200:
                    err = translate_api_error(response=resp)
                    time.sleep(2)
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                clean_json = sanitize_json(raw)
                data = json.loads(clean_json, strict=False)
                
                if isinstance(data, dict):
                    if "Characters" not in data: data["Characters"] = {}
                    if "Locations" not in data: data["Locations"] = {}
                    if "Artifacts" not in data: data["Artifacts"] = {}
                    if track_factions and "Factions" not in data: data["Factions"] = {}
                    return True, data
                    
                err = "AI did not return a valid JSON Dictionary."
                time.sleep(1)
            except Exception as e:
                err = translate_api_error(exception=e)
                time.sleep(2)
                continue
                
        return False, f"Seeding Failed: {err}"