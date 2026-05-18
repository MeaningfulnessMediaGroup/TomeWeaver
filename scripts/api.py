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
    def _extract_story_metadata(folder_path):
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
                    if history:
                        # Find the actual highest turn number recorded (handles Turn 0 correctly)
                        max_turn = max([int(t.get("turn", 0)) for t in history])
                        turns = max_turn
                        
                        last_turn = history[-1]
                        location = last_turn.get("location", location)
                        
                        if last_turn.get("is_game_over", False):
                            status = "Victory" if last_turn.get("chapter_goal_achieved", False) else "Game Over"
                        else:
                            if max_turn == 0:
                                status = "Not Started"
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
            "folder_name": folder_path.name,
            "title": data.get("title", folder_path.name),
            "author": data.get("author", "Unknown"),
            "version": data.get("version", "1.0"),
            "creation_date": data.get("creation_date", "Unknown"),
            "mode": data.get("mode", "unknown"),
            "turns": turns,
            "location": location,
            "status": status,
            "search_blob": search_blob, # New hidden field
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
        
        # 2. Scan OS Directory (Lightning fast os.stat checks)
        for folder in ADV_DIR.iterdir():
            if folder.is_dir():
                folder_name = folder.name
                current_folders.add(folder_name)
                
                setup_file = folder / "setup.json"
                if not setup_file.exists(): continue
                
                history_file = folder / "history.json"
                
                s_mtime = os.path.getmtime(setup_file)
                h_mtime = os.path.getmtime(history_file) if history_file.exists() else 0
                
                cached = index_data.get(folder_name)
                
                # If new folder OR files were modified since last scan, rebuild this entry
                if not cached or cached.get("s_mtime") != s_mtime or cached.get("h_mtime") != h_mtime:
                    index_data[folder_name] = {
                        "s_mtime": s_mtime,
                        "h_mtime": h_mtime,
                        "meta": TomeWeaverAPI._extract_story_metadata(folder)
                    }
                    needs_save = True

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
    def create_story(title, author, mode, rules_cfg=None):
        """Creates a new boilerplate adventure folder and applies mechanical rules."""
        safe_title = sanitize_foldername(title)
        if not safe_title: return False, "Invalid title. Contains illegal characters."
            
        target_dir = ADV_DIR / safe_title
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
                    
                with open(setup_file, "w", encoding="utf-8") as f:
                    json.dump(setup_data, f, indent=4)
                    
            return True, safe_title
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
                        initial = [{
                            "chapter_number": 1, "title": first.get("title", "Chapter 1"),
                            "start_turn": 1, "end_turn": None, "goal": first.get("goal"), 
                            "obstacles": first.get("obstacles"), "setting": first.get("setting"), "pov": first.get("pov")
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
        target_dir = ADV_DIR / safe_new
        
        try:
            if source_dir != target_dir:
                if target_dir.exists(): return False, "A story with that name already exists."
                
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
                    
            return True, safe_new
        except Exception as e:
            return False, str(e)
            
    @staticmethod
    def create_story_from_prompt(title, author, mode, prompt_text, gen_pro, gen_epi, rules_cfg=None):
        """
        AI World Generator. Contacts the LLM to dynamically generate the world data,
        extracts the title, safely creates the folder, and populates the schema files.
        """
        from config import ENGINE_CONFIG
        from llm import sanitize_json
        import requests, re, time
        
        # Hardened prompt to prevent the AI from nesting the requested keys inside a "world" object
        sys_prompt = "You are a master world-builder and interactive fiction designer. Output ONLY a flat JSON object matching the exact keys below. Do not nest them under a parent object."
        
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
            schema += '  "goal": "A loose overarching motivation for the character"\n'
        else:
            schema += '  "starting_inventory": "A string listing initial items and health state",\n'
            schema += '  "plot_outline": [\n    {"title": "Chapter 1", "setting": "Description", "pov": "Character Name", "goal": "Specific objective", "obstacles": "Specific threats"}\n  ],\n'
            
        if gen_pro: schema += '  "prologue_text": "Write 3 to 4 paragraphs of rich, cinematic opening prose setting the scene",\n'
        if gen_epi and mode == "campaign": schema += '  "epilogue_text": "Write 2 to 3 paragraphs of satisfying concluding prose"\n'
            
        schema = schema.rstrip(",\n") + "\n}"
        
        user_msg = f"MODE: {mode.upper()}\nUSER CONCEPT: '{prompt_text}'\n"
        if title: user_msg += f"TITLE: {title}\n"
        user_msg += f"\nTASK: Generate the game configuration using this EXACT JSON schema. Write highly detailed, creative content for the values:\n{schema}"
        
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
            
            while (ADV_DIR / sanitize_foldername(final_title)).exists():
                final_title = f"{base_title} {counter}"
                counter += 1
                
            # Pass the mechanical rules directly into the base builder so setup.json is perfectly formatted from the start
            success, folder_or_err = TomeWeaverAPI.create_story(final_title, author, mode, rules_cfg)
            if not success: return False, f"Could not create folder: {folder_or_err}"
            
            folder_name = folder_or_err
            target_dir = ADV_DIR / folder_name

            # 4. Apply to setup.json
            setup_file = target_dir / "setup.json"
            with open(setup_file, "r", encoding="utf-8") as f:
                setup_data = json.load(f)
                
            keys_to_merge = ["title", "tone", "main_character", "lore_and_rules", "setting", "starting_situation", "goal", "starting_inventory", "plot_outline"]
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
                initial_chapters = [{
                    "chapter_number": 1,
                    "title": first_chap.get("title", "Chapter 1"),
                    "start_turn": 1, "end_turn": None,
                    "setting": first_chap.get("setting"),
                    "pov": first_chap.get("pov"),
                    "goal": first_chap.get("goal"),
                    "obstacles": first_chap.get("obstacles")
                }]
                with open(chapters_file, "w", encoding="utf-8") as f:
                    json.dump(initial_chapters, f, indent=4)
                    
            return True, folder_name
            
        except Exception as e:
            # CRITICAL FIX: Ensure we use the exact folder_name variable to clean up the bad generation
            TomeWeaverAPI.delete_story(folder_name) 
            return False, f"File Generation Failed: {str(e)}"

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