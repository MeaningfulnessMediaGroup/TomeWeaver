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
    def create_story(title, author, mode, create_shortcut=True):
        """Creates a new boilerplate adventure folder and an optional launcher shortcut."""
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
                with open(setup_file, "w", encoding="utf-8") as f:
                    json.dump(setup_data, f, indent=4)
                    
            if create_shortcut:
                bat_path = Path.cwd() / f"!Story - {safe_title}.bat"
                bat_content = f"""@echo off
setlocal EnableDelayedExpansion
set "ADVENTURE_FOLDER={safe_title}"
title TomeWeaver: %ADVENTURE_FOLDER%
echo ===================================================
echo   Loading Adventure: %ADVENTURE_FOLDER%
echo ===================================================
echo.
cd /d "%~dp0"
if exist "venv\\Scripts\\activate.bat" (
    call venv\\Scripts\\activate.bat
) else (
    echo [WARNING] Virtual environment not found. Attempting global Python...
)
python gui.py "adventures\\%ADVENTURE_FOLDER%"
if %errorlevel% neq 0 (
    echo.
    echo [SYSTEM] The engine exited with an error.
    pause
) else (
    timeout /t 2 >nul
)
exit /b 0
"""
                with open(bat_path, "w", encoding="utf-8") as f:
                    f.write(bat_content)
                    
            return True, safe_title
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
        source_dir = ADV_DIR / folder_name
        if not source_dir.exists(): return False, "Story not found."
        
        safe_new = sanitize_foldername(new_title)
        target_dir = ADV_DIR / safe_new
        
        try:
            if source_dir != target_dir:
                if target_dir.exists(): return False, "A story with that name already exists."
                source_dir.rename(target_dir)
            
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