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
from config import create_boilerplate_files, get_adventures_dir
from llm import apply_json_response_format

def get_adv_dir():
    """Resolved adventures library root (see ``config.get_adventures_dir``)."""
    return get_adventures_dir()

def get_index_file():
    """Path to ``index.json`` inside the active adventures library root."""
    return get_adv_dir() / "index.json"

def sanitize_foldername(name):
    """Strip characters illegal on common filesystems from a folder name.

    Args:
        name: Raw title or label from the user or import flow.

    Returns:
        str: Sanitized name truncated to 60 characters.
    """
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean[:60].strip()

class TomeWeaverAPI:
    """Static facade for the desktop UI: stories, cartridges, and engine boot.

    Handles adventure indexing, ZIP import/export, universe management, and
    delegates gameplay to :class:`SandboxEngine` or :class:`CampaignEngine`.
    """

    # ---------------------------------------------------------
    # AUTONOMOUS INDEXING SYSTEM
    # ---------------------------------------------------------

    @staticmethod
    def _extract_universe_metadata(folder_path, rel_path):
        """Reads master_setup.json to build metadata for a Shared Universe container."""
        setup_file = folder_path / "master_setup.json"
        try:
            with open(setup_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {
                "folder_name": folder_path.name, "title": "CORRUPTED UNIVERSE", 
                "mode": "universe", "type": "universe", "path": str(folder_path.resolve())
            }
            
        search_blob = f"{data.get('universe_title', '')} {data.get('tone', '')} {data.get('lore_and_rules', '')} {folder_path.name}".lower()
        
        return {
            "folder_name": rel_path,
            "title": data.get("universe_title", folder_path.name),
            "author": data.get("author", "Unknown"),
            "mode": "universe",
            "type": "universe", # UI Dashboard Identifier
            "search_blob": search_blob,
            "path": str(folder_path.resolve()),
            "status": "Universe",
            "turns": 0
        }

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
                "mode": "error", "type": "story", "turns": 0, "location": "", "status": "Error",
                "path": str(folder_path.resolve())
            }
            
        turns = 0
        location = data.get("setting", "Unknown")
        status = "Not Started"
        
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as hf:
                    history = json.load(hf)
                    
                    if isinstance(history, list) and len(history) > 0:
                        max_turn = max([int(t.get("turn", 0)) for t in history])
                        turns = max_turn
                        
                        last_turn = history[-1]
                        
                        location = last_turn.get("location", location)
                        if not location or not location.strip():
                            location = data.get("setting", "Unknown")
                        
                        is_over = str(last_turn.get("is_game_over", False)).lower() == "true"
                        is_victory = str(last_turn.get("chapter_goal_achieved", False)).lower() == "true"
                        
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
            "folder_name": rel_path, 
            "title": data.get("title", folder_path.name),
            "author": data.get("author", "Unknown"),
            "version": data.get("version", "1.0"),
            "creation_date": data.get("creation_date", "Unknown"),
            "mode": data.get("mode", "unknown"),
            "type": "story", # UI Dashboard Identifier
            "turns": turns,
            "location": location,
            "status": status,
            "search_blob": search_blob,
            "path": str(folder_path.resolve())
        }
        
        
    @staticmethod
    def slice_thread(source_folder_name, selected_chapters, new_title, new_author):
        """
        Extracts specific chapters from a source story, deeply re-indexes them (including RAG memory strings), 
        and moves them into a brand new standalone story or Universe Thread.
        Removes the extracted chapters from the source story and safely heals the boundaries.
        """
        from config import load_json_safely, save_json_atomically
        import re
        import shutil
        
        source_dir = get_adv_dir() / source_folder_name
        if not source_dir.exists(): return False, "Source folder not found."
            
        safe_title = sanitize_foldername(new_title)
        if not safe_title: return False, "Invalid new title."
            
        target_dir = source_dir.parent / safe_title
        if target_dir.exists(): return False, f"A folder named '{safe_title}' already exists."
        
        try:
            target_dir.mkdir(parents=True)
            
            # 1. Load Source Files
            source_setup = load_json_safely(source_dir / "setup.json", "setup.json")
            source_history = load_json_safely(source_dir / "history.json", "history.json") if (source_dir / "history.json").exists() else []
            source_chapters = load_json_safely(source_dir / "chapters.json", "chapters.json") if (source_dir / "chapters.json").exists() else []
            source_memory = load_json_safely(source_dir / "memory.json", "memory.json") if (source_dir / "memory.json").exists() else {}

            new_history = []
            new_chapters = []
            new_plot_ledger = []
            new_chapter_ledger = []
            
            turn_map = {} 
            extracted_turns_set = set()
            new_master_turn = 1
            
            # 2. Slice and Re-Index the Target Data
            for chap_num in sorted(selected_chapters):
                orig_c = next((c for c in source_chapters if c.get("chapter_number") == chap_num), None)
                if not orig_c or orig_c.get("start_turn") is None: continue
                    
                orig_start = orig_c["start_turn"]
                orig_end = orig_c.get("end_turn") if orig_c.get("end_turn") is not None else len(source_history)
                
                # Clone Chapter Metadata
                new_c = orig_c.copy()
                new_chap_num = len(new_chapters) + 1
                new_c["chapter_number"] = new_chap_num 
                new_c["start_turn"] = new_master_turn
                
                # Clone and Re-Index History Turns
                turns_in_chap = 0
                for t in source_history:
                    old_turn_val = t.get("turn", 0)
                    if orig_start <= old_turn_val <= orig_end:
                        extracted_turns_set.add(old_turn_val)
                        
                        new_t = t.copy()
                        turn_map[old_turn_val] = new_master_turn 
                        new_t["turn"] = new_master_turn
                        new_history.append(new_t)
                        new_master_turn += 1
                        turns_in_chap += 1
                        
                new_c["end_turn"] = new_c["start_turn"] + turns_in_chap - 1 if orig_c.get("end_turn") is not None else None
                new_chapters.append(new_c)
                
                # Extract and Deep-Patch the Target Plot Ledger Strings
                for p in source_memory.get("plot_ledger", []):
                    if p.get("chapter_number") == chap_num:
                        new_p = p.copy()
                        new_p["chapter_number"] = new_chap_num
                        new_p["start_turn"] = turn_map.get(p.get("start_turn"), new_c["start_turn"])
                        new_p["end_turn"] = turn_map.get(p.get("end_turn"), new_c["end_turn"])
                        
                        raw_summary = str(p.get("summary", ""))
                        def replace_turn_string(match):
                            try:
                                old_t_int = int(match.group(1))
                                if old_t_int in turn_map:
                                    return f"Turn {turn_map[old_t_int]}"
                            except ValueError: pass
                            return match.group(0)
                            
                        new_p["summary"] = re.sub(r'Turn\s+(\d+)', replace_turn_string, raw_summary, flags=re.IGNORECASE)
                        new_plot_ledger.append(new_p)
                        
                # Extract Chapter Ledger
                for cl in source_memory.get("chapter_ledger", []):
                    if cl.get("chapter_number") == chap_num:
                        new_cl = cl.copy()
                        new_cl["chapter_number"] = new_chap_num
                        new_chapter_ledger.append(new_cl)
                        
            # 3. Clean, Heal, and Re-Index the Source Data
            all_old_turns = [t.get("turn", 0) for t in source_history]
            cleaned_source_history_raw = []
            
            for t in source_history:
                old_turn = t.get("turn", 0)
                if old_turn not in extracted_turns_set:
                    new_t = t.copy()
                    
                    # --- BOUNDARY HEALING ---
                    # If the NEXT turn in the original history was extracted, this turn is right before a gap.
                    if (old_turn + 1) in extracted_turns_set:
                        # Does the cleaned history have any turns after this one?
                        has_future = any((ft > old_turn and ft not in extracted_turns_set) for ft in all_old_turns)
                        
                        if not has_future:
                            # It became the last turn. Reset choice so player can act.
                            new_t["player_choice"] = None
                        else:
                            # It's a gap in the middle of the timeline. Mark it.
                            new_t["player_choice"] = "[Timeline Sliced]"
                            
                        new_t.pop("narrative_bridge", None)
                        
                    cleaned_source_history_raw.append(new_t)
                    
            # Re-Index the Source Master Clock to collapse the gap perfectly
            cleaned_source_history = []
            source_turn_map = {}
            source_turn_counter = 1
            
            for t in cleaned_source_history_raw:
                old_turn_val = t.get("turn", 0)
                source_turn_map[old_turn_val] = source_turn_counter
                t["turn"] = source_turn_counter
                cleaned_source_history.append(t)
                source_turn_counter += 1
                
            # Re-Index Source Chapters using the map
            cleaned_source_chapters = [c for c in source_chapters if c.get("chapter_number") not in selected_chapters]
            source_chap_counter = 1
            for c in cleaned_source_chapters:
                c["chapter_number"] = source_chap_counter
                
                old_s = c.get("start_turn")
                if old_s in source_turn_map: c["start_turn"] = source_turn_map[old_s]
                else: c["start_turn"] = next((nt for ot, nt in source_turn_map.items() if ot >= old_s), None)
                    
                old_e = c.get("end_turn")
                if old_e is not None:
                    if old_e in source_turn_map: c["end_turn"] = source_turn_map[old_e]
                    else: c["end_turn"] = next((nt for ot, nt in reversed(source_turn_map.items()) if ot <= old_e), None)
                source_chap_counter += 1
                
            # Re-Index and Patch the Source Plot Ledger
            cleaned_source_plot = [p for p in source_memory.get("plot_ledger", []) if p.get("chapter_number") not in selected_chapters]
            for p in cleaned_source_plot:
                old_s = p.get("start_turn")
                old_e = p.get("end_turn")
                if old_s in source_turn_map: p["start_turn"] = source_turn_map[old_s]
                if old_e in source_turn_map: p["end_turn"] = source_turn_map[old_e]
                
                raw_summary = str(p.get("summary", ""))
                def replace_source_turn_string(match):
                    try:
                        old_t_int = int(match.group(1))
                        if old_t_int in source_turn_map: return f"Turn {source_turn_map[old_t_int]}"
                    except ValueError: pass
                    return match.group(0)
                    
                p["summary"] = re.sub(r'Turn\s+(\d+)', replace_source_turn_string, raw_summary, flags=re.IGNORECASE)

            cleaned_source_cl = [cl for cl in source_memory.get("chapter_ledger", []) if cl.get("chapter_number") not in selected_chapters]
                        
            # 4. Clone Setup & Write Target to Disk
            new_setup = source_setup.copy()
            new_setup["title"] = new_title
            new_setup["author"] = new_author
            new_setup["plot_outline"] = [c for c in new_setup.get("plot_outline", []) if c.get("title") in [ch["title"] for ch in new_chapters]]
            
            new_memory = source_memory.copy() 
            new_memory["plot_ledger"] = new_plot_ledger
            new_memory["chapter_ledger"] = new_chapter_ledger
            
            save_json_atomically(new_setup, target_dir / "setup.json")
            save_json_atomically(new_history, target_dir / "history.json")
            save_json_atomically(new_chapters, target_dir / "chapters.json")
            save_json_atomically(new_memory, target_dir / "memory.json")
            
            if (source_dir / "prologue.txt").exists(): shutil.copy(source_dir / "prologue.txt", target_dir / "prologue.txt")
            if (source_dir / "epilogue.txt").exists(): shutil.copy(source_dir / "epilogue.txt", target_dir / "epilogue.txt")
            if (source_dir / "icon.jpg").exists(): shutil.copy(source_dir / "icon.jpg", target_dir / "icon.jpg")
            if (source_dir / "system_prompt.txt").exists(): shutil.copy(source_dir / "system_prompt.txt", target_dir / "system_prompt.txt")

            # 5. Overwrite Source on Disk
            source_setup["plot_outline"] = [c for c in source_setup.get("plot_outline", []) if c.get("title") in [ch["title"] for ch in cleaned_source_chapters]]
            save_json_atomically(source_setup, source_dir / "setup.json")
            save_json_atomically(cleaned_source_history, source_dir / "history.json")
            save_json_atomically(cleaned_source_chapters, source_dir / "chapters.json")
            
            source_memory["plot_ledger"] = cleaned_source_plot
            source_memory["chapter_ledger"] = cleaned_source_cl
            save_json_atomically(source_memory, source_dir / "memory.json")

            return True, target_dir.relative_to(get_adv_dir()).as_posix()
        except Exception as e:
            return False, str(e)
            
    @staticmethod
    def get_available_stories():
        """
        High-Performance Loader: Uses OS file timestamps to selectively read 
        only updated JSON files, caching the rest in index.json.
        """
        get_adv_dir().mkdir(parents=True, exist_ok=True)
        
        # 1. Load the cache
        index_data = {}
        if get_index_file().exists():
            try:
                with open(get_index_file(), "r", encoding="utf-8") as f:
                    index_data = json.load(f)
            except json.JSONDecodeError:
                pass # If corrupted, we just rebuild it automatically
                
        needs_save = False
        current_folders = set()
        
        # 2. Deep Scan OS Directory
        for root, dirs, files in os.walk(get_adv_dir()):
            rel_path = Path(root).relative_to(get_adv_dir()).as_posix()
            if rel_path == ".": rel_path = ""
            
            is_universe_root = False
            
            # Check for Universe Root first
            if "master_setup.json" in files:
                current_folders.add(rel_path)
                s_mtime = os.path.getmtime(Path(root) / "master_setup.json")
                cached = index_data.get(rel_path)
                
                # Check cache for Universe updates
                if not cached or cached.get("s_mtime") != s_mtime or cached.get("type") != "universe":
                    index_data[rel_path] = {
                        "s_mtime": s_mtime,
                        "h_mtime": 0,
                        "type": "universe",
                        "meta": TomeWeaverAPI._extract_universe_metadata(Path(root), rel_path)
                    }
                    needs_save = True
                
                is_universe_root = True
                    
            # Check for Story only if this directory isn't ALREADY a Universe Root
            if "setup.json" in files and not is_universe_root:
                current_folders.add(rel_path)
                setup_file = Path(root) / "setup.json"
                history_file = Path(root) / "history.json"
                
                s_mtime = os.path.getmtime(setup_file)
                h_mtime = os.path.getmtime(history_file) if history_file.exists() else 0
                
                cached = index_data.get(rel_path)
                
                # Check cache for Story updates
                if not cached or cached.get("s_mtime") != s_mtime or cached.get("h_mtime") != h_mtime or cached.get("type") != "story":
                    index_data[rel_path] = {
                        "s_mtime": s_mtime,
                        "h_mtime": h_mtime,
                        "type": "story",
                        "meta": TomeWeaverAPI._extract_story_metadata(Path(root), rel_path)
                    }
                    needs_save = True
                
                # CRITICAL FIX: Only stop traversing if we are inside a sub-directory.
                # If a loose setup.json is in the root /adventures folder, do NOT abort the scan!
                if rel_path != "":
                    dirs.clear()

        # 3. Clean up deleted folders from the index
        keys_to_remove = [k for k in index_data.keys() if k not in current_folders]
        for k in keys_to_remove:
            del index_data[k]
            needs_save = True
            
        # 4. Save cache if changes occurred
        if needs_save:
            with open(get_index_file(), "w", encoding="utf-8") as f:
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
            
        target_dir = get_adv_dir() / parent_dir / safe_title
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
                    
                # Inject Universe Flag if this story is being born inside a Universe
                from config import find_universe_root
                if find_universe_root(target_dir):
                    setup_data["is_universe_thread"] = True
                    
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

    @staticmethod
    def create_universe(title, author, tone, lore, parent_dir=""):
        """Creates a new Shared Universe container."""
        safe_title = sanitize_foldername(title)
        if not safe_title: return False, "Invalid title. Contains illegal characters."
            
        target_dir = get_adv_dir() / parent_dir / safe_title
        if target_dir.exists(): return False, f"A folder named '{safe_title}' already exists."
            
        try:
            target_dir.mkdir(parents=True)
            master_setup = {
                "universe_title": title,
                "author": author.strip() if author.strip() else "Anonymous",
                "tone": tone.strip(),
                "lore_and_rules": lore.strip(),
                "creation_date": datetime.datetime.now().strftime("%Y-%m-%d")
            }
            with open(target_dir / "master_setup.json", "w", encoding="utf-8") as f:
                json.dump(master_setup, f, indent=4)
                
            # Initialize the empty World Bible
            shared_mem = {
                "character_ledger": {}, "location_ledger": {}, 
                "artifact_ledger": {}, "faction_ledger": {}, 
                "aliases": {"character_ledger": {}, "location_ledger": {}, "artifact_ledger": {}, "faction_ledger": {}}
            }
            with open(target_dir / "shared_memory.json", "w", encoding="utf-8") as f:
                json.dump(shared_mem, f, indent=4)
                
            return True, (Path(parent_dir) / safe_title).as_posix()
        except Exception as e:
            return False, str(e)
            

    @staticmethod
    def analyze_migration(folder_name):
        """Scans a newly dropped story to see if it needs Universe integration."""
        from config import find_universe_root, load_json_safely

        target_dir = get_adv_dir() / folder_name
        univ_root = find_universe_root(target_dir)
        
        if not univ_root:
            return False, None, []
            
        setup_file = target_dir / "setup.json"
        setup_data = load_json_safely(setup_file, "setup.json")
        if setup_data.get("is_universe_thread", False):
            return False, None, [] # Already integrated
            
        # It needs migration. Scan for name collisions.
        local_mem = load_json_safely(target_dir / "memory.json", "memory.json") if (target_dir / "memory.json").exists() else {}
        shared_mem = load_json_safely(univ_root / "shared_memory.json", "shared_memory.json") if (univ_root / "shared_memory.json").exists() else {}
        
        conflicts = []
        ledgers = ["character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"]
        for l in ledgers:
            for entity in local_mem.get(l, {}).keys():
                if entity in shared_mem.get(l, {}):
                    conflicts.append({"ledger": l, "entity": entity})
                    
        return True, univ_root, conflicts


    @staticmethod
    def commit_migration(folder_name, univ_root, lore_strategy, resolutions):
        """Transactionally splices the local memory into the Shared World Bible."""
        from config import load_json_safely, save_json_atomically

        target_dir = get_adv_dir() / folder_name
        setup_file = target_dir / "setup.json"
        local_mem_file = target_dir / "memory.json"
        shared_mem_file = univ_root / "shared_memory.json"
        master_setup_file = univ_root / "master_setup.json"
        
        setup_data = load_json_safely(setup_file, "setup.json")
        local_mem = load_json_safely(local_mem_file, "memory.json") if local_mem_file.exists() else {}
        shared_mem = load_json_safely(shared_mem_file, "shared_memory.json") if shared_mem_file.exists() else {}
        master_setup = load_json_safely(master_setup_file, "master_setup.json")
        
        # 1. Handle Global Lore Strategy
        master_lore = master_setup.get("lore_and_rules", "").strip()
        local_lore = setup_data.get("lore_and_rules", "").strip()
        
        if lore_strategy == "overwrite":
            setup_data["lore_and_rules"] = master_lore
        elif lore_strategy == "prepend":
            setup_data["lore_and_rules"] = f"{master_lore}\n\n{local_lore}".strip()
        elif lore_strategy == "append":
            setup_data["lore_and_rules"] = f"{local_lore}\n\n{master_lore}".strip()
        elif lore_strategy == "genesis":
            master_setup["lore_and_rules"] = local_lore
            setup_data["lore_and_rules"] = ""
            save_json_atomically(master_setup, master_setup_file)
            
        setup_data["tone"] = master_setup.get("tone", setup_data.get("tone", ""))
        
        # 2. Splice Main Ledgers
        ledgers = ["character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"]
        for l_type in ledgers:
            if l_type not in local_mem: continue
            if l_type not in shared_mem: shared_mem[l_type] = {}
            
            for entity_name, local_data in list(local_mem[l_type].items()):
                if isinstance(local_data, list):
                    local_data = {"characteristics": {}, "ledger": local_data, "author_notes": "", "state": "active"}
                    
                target_name = entity_name
                res_key = f"{l_type}::{entity_name}"
                
                # Check if this specific entity had a collision resolution
                if res_key in resolutions:
                    res = resolutions[res_key]
                    if res["action"] == "rename":
                        target_name = res["new_name"]
                        shared_mem[l_type][target_name] = local_data
                    elif res["action"] == "merge":
                        master = shared_mem[l_type][entity_name]
                        if isinstance(master, list):
                            master = {"characteristics": {}, "ledger": master, "author_notes": "", "state": "active"}
                            shared_mem[l_type][entity_name] = master
                            
                        # Append traits and events with zero data loss
                        for tk, tv in local_data.get("characteristics", {}).items():
                            if tk not in master["characteristics"]:
                                master["characteristics"][tk] = tv
                            else:
                                if str(tv).lower() not in str(master["characteristics"][tk]).lower():
                                    master["characteristics"][tk] = f"{master['characteristics'][tk]}, {tv}"
                        
                        master["ledger"].extend(local_data.get("ledger", []))
                        
                        m_notes = master.get("author_notes", "").strip()
                        s_notes = local_data.get("author_notes", "").strip()
                        if s_notes and s_notes not in m_notes:
                            master["author_notes"] = f"{m_notes}\n\n{s_notes}".strip()
                else:
                    shared_mem[l_type][target_name] = local_data
                    
                # Permanently delete the entity from the local memory
                del local_mem[l_type][entity_name]
                
        # 2.5 Splice Aliases (With Smart Target Routing)
        local_aliases = local_mem.get("aliases", {})
        shared_aliases = shared_mem.setdefault("aliases", {"character_ledger": {}, "location_ledger": {}, "artifact_ledger": {}, "faction_ledger": {}})
        
        for l_type, alias_map in local_aliases.items():
            if not isinstance(alias_map, dict): continue
            if l_type not in shared_aliases: shared_aliases[l_type] = {}
            
            for alias, master in alias_map.items():
                # If the master entity was renamed during collision resolution, point the alias to the new name!
                res_key = f"{l_type}::{master}"
                target_master = master
                if res_key in resolutions and resolutions[res_key]["action"] == "rename":
                    target_master = resolutions[res_key]["new_name"]
                
                shared_aliases[l_type][alias] = target_master
                
        if "aliases" in local_mem: 
            del local_mem["aliases"]
                
        # 3. Commit Atomic Writes
        setup_data["is_universe_thread"] = True
        save_json_atomically(setup_data, setup_file)
        if local_mem: save_json_atomically(local_mem, local_mem_file)
        save_json_atomically(shared_mem, shared_mem_file)
        
        return True, ""    
        
    # ---------------------------------------------------------
    # ZIP CARTRIDGE SYSTEM
    # ---------------------------------------------------------

    @staticmethod
    def export_to_zip(folder_name, target_zip_path):
        """Package an adventure folder as a portable ZIP cartridge.

        Args:
            folder_name: Story folder name under ``adventures/``.
            target_zip_path: Destination ``.zip`` path on disk.

        Returns:
            tuple[bool, str]: ``(success, message)``.
        """
        source_dir = get_adv_dir() / folder_name
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
    def inspect_zip(zip_path):
        """Detect ``full`` cartridge vs ``branch_pack`` vs ``invalid``."""
        from branch_pack import inspect_zip_cartridge

        return inspect_zip_cartridge(zip_path)

    @staticmethod
    def export_branch_pack(folder_name, run_ids, target_zip_path, shared_by=""):
        """Export selected run-tree timelines as a portable branch pack."""
        from branch_pack import export_branch_pack as _export_branch_pack

        target_dir = get_adv_dir() / folder_name
        if not target_dir.exists():
            return False, "Story folder not found."
        return _export_branch_pack(target_dir, list(run_ids), target_zip_path, shared_by=shared_by)

    @staticmethod
    def import_branch_pack(folder_name, zip_path, export_ids=None, label_prefix=""):
        """Merge branch-pack timelines into an existing story."""
        from branch_pack import import_branch_pack as _import_branch_pack

        target_dir = get_adv_dir() / folder_name
        if not target_dir.exists():
            return False, "Story folder not found."
        return _import_branch_pack(target_dir, zip_path, export_ids, label_prefix=label_prefix)

    @staticmethod
    def import_from_zip(zip_path):
        """Import a ZIP cartridge into ``adventures/`` with collision-safe naming.

        Args:
            zip_path: Path to a cartridge containing ``setup.json`` and
                ``system_prompt.txt``.

        Returns:
            tuple[bool, str]: ``(success, message_or_folder_name)``.
        """
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
                
                target_dir = get_adv_dir() / safe_title
                counter = 1
                while target_dir.exists():
                    target_dir = get_adv_dir() / f"{safe_title} ({counter})"
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

                from cartridge_format import load_cartridge_setup

                load_cartridge_setup(target_dir / "setup.json")
                            
            return True, target_dir.name
        except zipfile.BadZipFile: return False, "Invalid or corrupted zip file."
        except Exception as e: return False, str(e)

    @staticmethod
    def list_runs(folder_name):
        """Return archived runs and active_run_id for a story cartridge."""
        from run_tree import list_runs as _list_runs

        target_dir = get_adv_dir() / folder_name
        if not target_dir.exists():
            return False, "Story folder not found."
        runs, active_id = _list_runs(target_dir)
        return True, {"runs": runs, "active_run_id": active_id}

    @staticmethod
    def archive_current_run(folder_name, label=None):
        """Snapshot the live cartridge root into the run tree."""
        from run_tree import archive_current_run

        target_dir = get_adv_dir() / folder_name
        if not target_dir.exists():
            return False, "Story folder not found."
        run_id, msg = archive_current_run(target_dir, label=label)
        if run_id is None:
            return False, msg
        return True, msg

    @staticmethod
    def rename_run(folder_name, run_id, new_label):
        from run_tree import rename_run as _rename_run

        target_dir = get_adv_dir() / folder_name
        return _rename_run(target_dir, run_id, new_label)

    @staticmethod
    def delete_run(folder_name, run_id):
        from run_tree import delete_run as _delete_run

        target_dir = get_adv_dir() / folder_name
        return _delete_run(target_dir, run_id)

    @staticmethod
    def switch_run(folder_name, run_id):
        """Persist the active timeline, then load an archived run to the cartridge root."""
        from run_tree import switch_run as _switch_run

        target_dir = get_adv_dir() / folder_name
        if not target_dir.exists():
            return False, "Story folder not found."
        return _switch_run(target_dir, run_id)

    @staticmethod
    def fork_at_turn(folder_name, fork_turn_number, archive_label=None):
        """Archive the timeline and truncate after turn N (fork @ N)."""
        try:
            engine = TomeWeaverAPI.load_engine(folder_name)
            ok, msg, _run_id = engine.fork_at_turn(int(fork_turn_number), archive_label=archive_label)
            return ok, msg
        except Exception as e:
            return False, str(e)

    @staticmethod
    def list_run_fork_points(folder_name, run_id):
        """Valid fork-at-turn numbers inside an archived run snapshot."""
        from run_tree import list_fork_points_for_run

        target_dir = get_adv_dir() / folder_name
        if not target_dir.exists():
            return False, "Story folder not found."
        return list_fork_points_for_run(target_dir, run_id)

    @staticmethod
    def restore_and_fork(folder_name, run_id, fork_turn_number):
        """Load an archived run and fork @ turn N in one step."""
        from run_tree import restore_and_fork as _restore_and_fork

        target_dir = get_adv_dir() / folder_name
        if not target_dir.exists():
            return False, "Story folder not found."
        return _restore_and_fork(target_dir, run_id, int(fork_turn_number))

    @staticmethod
    def restart_story(folder_name, save_before=True):
        """Headless reset: optionally archive, then wipe history/chapters at cartridge root."""
        from run_tree import headless_restart_wipe, prepare_restart

        target_dir = get_adv_dir() / folder_name
        setup_file = target_dir / "setup.json"

        try:
            if not setup_file.exists():
                return False, "setup.json not found."

            ok, msg = prepare_restart(target_dir, save_run=bool(save_before))
            if not ok:
                return False, msg

            with open(setup_file, "r", encoding="utf-8") as f:
                setup_data = json.load(f)

            headless_restart_wipe(target_dir, setup_data)
            return True, "Story reset to Turn 0."
        except Exception as e:
            return False, str(e)
            
    @staticmethod
    def delete_story(folder_name):
        """Permanently deletes an adventure directory."""
        target_dir = get_adv_dir() / folder_name
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
        source_dir = get_adv_dir() / folder_name
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
            return True, target_dir.relative_to(get_adv_dir()).as_posix()
        except Exception as e:
            return False, str(e)
            
    @staticmethod
    def move_story(folder_name, new_parent_dir):
        """Moves a story folder to a new directory within the adventures root."""
        import shutil
        source_dir = get_adv_dir() / folder_name
        if not source_dir.exists(): return False, "Story not found."
        
        target_parent = get_adv_dir() / new_parent_dir
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
                
            return True, target_dir.relative_to(get_adv_dir()).as_posix()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def create_story_from_prompt(title, author, mode, prompt_text, gen_pro, gen_epi, rules_cfg=None, parent_dir="", extra_data=None, universe_lore=""):
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
        
        # Combine the user's prompt with the Universe Lore (if provided)
        final_prompt_text = prompt_text
        if universe_lore:
            final_prompt_text = f"{universe_lore}\n\nUSER CONCEPT:\n{prompt_text}"
            
        user_msg = PROMPTS.get("USER_WORLD_GEN", "")
        user_msg = user_msg.replace("{mode}", mode.upper())
        user_msg = user_msg.replace("{prompt_text}", final_prompt_text) # Use the combined text!
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
                apply_json_response_format(payload)
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
            
            while (get_adv_dir() / parent_dir / sanitize_foldername(final_title)).exists():
                final_title = f"{base_title} {counter}"
                counter += 1
                
            # Pass the mechanical rules directly into the base builder so setup.json is perfectly formatted from the start
            success, folder_or_err = TomeWeaverAPI.create_story(final_title, author, mode, rules_cfg, parent_dir)
            if not success: return False, f"Could not create folder: {folder_or_err}"
            
            folder_name = folder_or_err
            target_dir = get_adv_dir() / folder_name

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
    def evaluate_import_integration(engine, raw_text, insert_after_idx):
        """Score how well pasted import text fits the active story's local and universe RAG."""
        from config import ENGINE_CONFIG, PROMPTS
        from llm import enforce_rate_limit, sanitize_json, translate_api_error
        import json
        import requests
        import time

        raw_text = (raw_text or "").strip()
        if not raw_text:
            return False, "Paste some story text to evaluate."

        story_context = engine.build_import_evaluation_context(insert_after_idx)
        preview = raw_text[:12000]
        if len(raw_text) > 12000:
            preview += "\n\n[... pasted text truncated for evaluation ...]"

        splice_turn = 0
        if insert_after_idx >= 0 and engine.history:
            splice_turn = engine.history[insert_after_idx].get("turn", insert_after_idx + 1)

        sys_prompt = PROMPTS.get("SYS_IMPORT_EVAL", "")
        user_prompt = PROMPTS.get("USER_IMPORT_EVAL", "")
        user_prompt = user_prompt.replace("{story_context}", story_context)
        user_prompt = user_prompt.replace("{import_text}", preview)
        user_prompt = user_prompt.replace("{splice_turn}", str(splice_turn))

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]

        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip():
            headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"

        err = "Unknown error"
        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 1200,
            }
            try:
                enforce_rate_limit()
                apply_json_response_format(payload)
                resp = requests.post(
                    ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=90
                )
                if resp.status_code != 200:
                    err = translate_api_error(response=resp)
                    time.sleep(2)
                    continue

                raw = resp.json()["choices"][0]["message"]["content"].strip()
                data = json.loads(sanitize_json(raw), strict=False)
                if not isinstance(data, dict):
                    return False, "Evaluation returned invalid data."

                score = data.get("integration_score", 0)
                try:
                    score = max(0, min(100, int(score)))
                except (TypeError, ValueError):
                    score = 0
                data["integration_score"] = score

                for key in ("fitting_reasons", "misfit_reasons"):
                    val = data.get(key, [])
                    if not isinstance(val, list):
                        data[key] = [str(val)] if val else []
                    else:
                        data[key] = [str(v) for v in val if str(v).strip()]

                for key in ("summary", "character_analysis", "recommendation", "verdict"):
                    if key not in data:
                        data[key] = ""

                return True, data
            except Exception as e:
                err = translate_api_error(exception=e)
                time.sleep(2)

        return False, f"Integration evaluation failed.\nReason: {err}"
        
     
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
                apply_json_response_format(payload)
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

        sys_prompt = PROMPTS.get("SYS_CHAP_GEN", "")
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
                apply_json_response_format(payload)
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
    def overhaul_active_story(engine, prompt_text, gen_pro, gen_epi, universe_lore=""):
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
        
        # Combine the user's prompt with the Universe Lore (if provided)
        final_prompt_text = prompt_text
        if universe_lore:
            final_prompt_text = f"{universe_lore}\n\nUSER CONCEPT:\n{prompt_text}"
            
        user_msg = PROMPTS.get("USER_WORLD_GEN", "")
        user_msg = user_msg.replace("{mode}", mode.upper())
        user_msg = user_msg.replace("{prompt_text}", final_prompt_text)
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
                apply_json_response_format(payload)
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
    def overhaul_active_universe(engine, prompt_text):
        """
        AI Overhaul Generator (Universe Edition). 
        Dynamically generates global world data and safely injects it into master_setup_data.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json
        import requests, re, time
        
        # USE THE NEW UNIVERSE-SPECIFIC PROMPTS
        sys_prompt = PROMPTS.get("SYS_UNIVERSE_GEN", "")
        
        schema = "{\n"
        schema += '  "universe_title": "A catchy, compelling name for this entire universe",\n'
        schema += '  "tone": "Brief description of the atmosphere and genre",\n'
        schema += '  "lore_and_rules": "Key facts about the world, magic, or technology"\n'
        schema += "}"
        
        title_str = f"TITLE: {engine.master_setup_data.get('universe_title', 'Universe')}\n"
        
        user_msg = PROMPTS.get("USER_UNIVERSE_GEN", "")
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
                "max_tokens": 1500
            }
            
            try:
                apply_json_response_format(payload)
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
            return False, f"Failed to generate universe overhaul. Last error: {err}"
            
        try:
            # Inject directly into the engine's active memory
            keys_to_merge = ["universe_title", "tone", "lore_and_rules"]
            for k in keys_to_merge:
                if k in data:
                    if isinstance(data[k], (dict, list)):
                        engine.master_setup_data[k] = json.dumps(data[k])
                    else:
                        engine.master_setup_data[k] = data[k]
                
            from config import save_json_atomically
            save_json_atomically(engine.master_setup_data, engine.master_setup_file)
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
        
        sys_prompt = PROMPTS.get("SYS_SCHEMA_GEN", "")
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
                apply_json_response_format(payload)
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
        target = get_adv_dir() / rel_path
        if not target.exists(): target = get_adv_dir() # Fallback to root
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
        target = get_adv_dir() / parent_dir / safe_name
        if target.exists(): return False, "Folder already exists."
        try:
            target.mkdir(parents=True, exist_ok=True)
            return True, safe_name
        except Exception as e:
            return False, str(e)

    @staticmethod
    def rename_folder(rel_path, new_name):
        """Renames a physical directory. If it is a Universe, safely updates its JSON title."""
        import shutil
        source_dir = get_adv_dir() / rel_path
        if not source_dir.exists(): return False, "Folder not found."
        
        safe_new = sanitize_foldername(new_name)
        if not safe_new: return False, "Invalid name."
        
        # Target path remains in the same parent directory
        target_dir = source_dir.parent / safe_new
        
        # Validation: Allow case-only renames (e.g. "my universe" -> "My Universe")
        is_case_change = (source_dir.name.lower() == safe_new.lower())
        if not is_case_change and target_dir.exists(): 
            return False, f"A folder named '{safe_new}' already exists in this location."
            
        try:
            # 1. Physical Rename (With fallback for stubborn OS file-locks)
            if source_dir.name != safe_new:
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
            
            # 2. JSON Title Update (If it's a Universe)
            master_file = target_dir / "master_setup.json"
            if master_file.exists():
                with open(master_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                data["universe_title"] = new_name # Preserve the user's exact capitalization/spacing
                
                with open(master_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                    
            return True, target_dir.relative_to(get_adv_dir()).as_posix()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_folder(rel_path):
        """Recursively deletes a folder and everything inside it."""
        source_dir = get_adv_dir() / rel_path
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
        source_dir = get_adv_dir() / rel_path
        if not source_dir.exists(): return False, "Folder not found."
        
        target_parent = get_adv_dir() / new_parent_dir
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
                
            return True, target_dir.relative_to(get_adv_dir()).as_posix()
        except Exception as e:
            return False, str(e)
            
    @staticmethod
    @staticmethod
    def set_custom_icon(rel_path, source_image_path):
        """Loads an image, crops it to a square, resizes to 64x64, and saves as icon.jpg."""
        try:
            from PIL import Image
        except ImportError:
            return False, "Python 'Pillow' library is missing. Please run: pip install pillow"
            
        target_dir = get_adv_dir() / rel_path
        if not target_dir.exists(): 
            return False, "Target folder not found."
            
        try:
            with Image.open(source_image_path) as img:
                # 1. Crop to a perfect square based on the shortest edge (Center crop)
                width, height = img.size
                new_size = min(width, height)
                left = (width - new_size) / 2
                top = (height - new_size) / 2
                right = (width + new_size) / 2
                bottom = (height + new_size) / 2
                img = img.crop((left, top, right, bottom))
                
                # 2. Resize to exactly 64x64 (Using LANCZOS for high-quality downsampling)
                img = img.resize((64, 64), Image.Resampling.LANCZOS)
                
                # 3. Convert to RGB (Strips alpha channel for safe JPEG compression)
                img = img.convert("RGB")
                
                # 4. Save directly into the cartridge folder
                icon_path = target_dir / "icon.jpg"
                img.save(icon_path, "JPEG", quality=90)
                
            # 5. CACHE INVALIDATION: Artificially "touch" the setup JSON so the Dashboard Indexer
            # knows this folder changed and forces a complete UI redraw of the image.
            setup_file = target_dir / "setup.json"
            master_file = target_dir / "master_setup.json"
            import os, time
            current_time = time.time()
            if setup_file.exists(): os.utime(setup_file, (current_time, current_time))
            if master_file.exists(): os.utime(master_file, (current_time, current_time))
                
            return True, ""
        except Exception as e:
            return False, f"Image processing failed: {str(e)}"
            
    # ---------------------------------------------------------
    # ENGINE LAUNCHER
    # ---------------------------------------------------------

    @staticmethod
    def load_engine(folder_name):
        """Instantiate the correct engine for a story folder.

        Args:
            folder_name: Adventure directory name under ``adventures/``.

        Returns:
            SandboxEngine | CampaignEngine: Configured headless engine.

        Raises:
            FileNotFoundError: If ``setup.json`` is missing.
        """
        target_dir = get_adv_dir() / folder_name
        setup_file = target_dir / "setup.json"
        if not setup_file.exists(): raise FileNotFoundError(f"setup.json missing from '{folder_name}'.")
            
        from config import load_json_safely
        from cartridge_format import load_cartridge_setup

        setup_data = load_cartridge_setup(setup_file)
        mode = setup_data.get("mode", "sandbox").lower()
        
        if mode == "campaign": return CampaignEngine(target_dir, setup_data)
        else: return SandboxEngine(target_dir, setup_data)
        
        
    @staticmethod
    def infer_location(scene_text, previous_location=None):
        """
        Reads a block of prose and asks the AI to deduce the protagonist's current location.
        Uses previous_location as a geographic anchor if provided.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import enforce_rate_limit
        import requests, time
        
        sys_prompt = PROMPTS.get("SYS_LOCATION_INFER", "")
        user_prompt = PROMPTS.get("USER_LOCATION_INFER", "")
        
        loc_str = ""
        if previous_location:
            loc_str = f"GEOGRAPHIC ANCHOR: The previous scene took place at '{previous_location}'. If the protagonist moved, use this anchor to provide a hierarchical location (e.g., if they moved to a kitchen, output '{previous_location} - Kitchen')."
            
        user_prompt = user_prompt.replace("{scene_text}", scene_text)
        user_prompt = user_prompt.replace("{prev_loc_context}", loc_str)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(2):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages,
                "temperature": 0.2, 
                "max_tokens": 50
            }
            try:
                enforce_rate_limit()
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    raw = raw.strip('"\'')
                    if raw.lower().startswith("here is"): raw = raw.split("\n", 1)[-1].strip()
                    return True, raw
            except Exception:
                time.sleep(1)
                
        return False, "Failed to infer location."

        
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
            user_prompt = PROMPTS.get("USER_BRIDGE_CONDENSE", "").replace("{bridge}", bridge_text)
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
                apply_json_response_format(payload)
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
                apply_json_response_format(payload)
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
    def generate_chapter_summary(parts_text, setup_data):
        """
        RAG Phase 1.5: Condenses multiple granular plot_ledger parts into a single Chapter Summary JSON with tags.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit, translate_api_error
        import requests, time, json
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_CHAPTER", "")
        
        # --- DYNAMIC TAG LIST INJECTION ---
        custom_tags_raw = setup_data.get("chapter_tags", "")
        if custom_tags_raw and str(custom_tags_raw).strip():
            tag_str = f"When extracting tags, prioritize using these standard categories if they apply:\n[{str(custom_tags_raw).strip()}]\n"
        else:
            tag_str = "When extracting tags, prioritize using standard literary categories (e.g., Combat, Romance, Puzzle, Lore).\n"
            
        user_prompt = PROMPTS.get("USER_MEMORY_CHAPTER", "")
        user_prompt = user_prompt.replace("{parts_text}", parts_text)
        user_prompt = user_prompt.replace("{tag_list}", tag_str)

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
                apply_json_response_format(payload)
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    
                    # CRITICAL FIX: Route through the Fortress Sanitizer to guarantee clean JSON extraction!
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    
                    if isinstance(data, dict): return True, data
            except Exception as e:
                err = translate_api_error(exception=e)
                time.sleep(2)
        return False, f"Chapter Condensation Failed:\n{err}"
        
        
    @staticmethod
    def generate_chapter_tags(summary_text, setup_data):
        """
        Targeted RAG Phase: Extracts only tags from an existing chapter summary.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit
        import requests, time, json
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_CHAPTER_TAGS", "")
        
        custom_tags_raw = setup_data.get("chapter_tags", "")
        if custom_tags_raw and str(custom_tags_raw).strip():
            tag_str = f"When extracting tags, prioritize using these standard categories if they apply:\n[{str(custom_tags_raw).strip()}]\n"
        else:
            tag_str = "When extracting tags, prioritize using standard literary categories (e.g., Combat, Romance, Puzzle, Lore).\n"
            
        user_prompt = PROMPTS.get("USER_MEMORY_CHAPTER_TAGS", "")
        user_prompt = user_prompt.replace("{summary_text}", summary_text)
        user_prompt = user_prompt.replace("{tag_list}", tag_str)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(3):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.4,  "max_tokens": 300
            }
            try:
                enforce_rate_limit()
                apply_json_response_format(payload)
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    if isinstance(data, list): return True, data
            except Exception: time.sleep(1)
        return False, "Failed to generate tags."
        
        
    @staticmethod
    def validate_chapter_chunk(raw_text, summary_text):
        """QA a chapter memory summary against raw history text (RAG phase).

        Args:
            raw_text: Source turns prose for the chapter chunk.
            summary_text: Existing condensed summary to validate.

        Returns:
            tuple[bool, dict | str]: ``(success, qa_report_or_error)``.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit, translate_api_error
        import requests, time, json, uuid
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_VALIDATE", "") + f"\n[ISOLATION_KEY: {uuid.uuid4()}]"
        user_prompt = PROMPTS.get("USER_MEMORY_CHAPTER_VALIDATE", "")
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
                apply_json_response_format(payload)
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    if isinstance(data, dict):
                        return True, f"Fidelity Score: {data.get('score', '?/100')}\n\n{data.get('report', 'No report generated.')}"
            except Exception: time.sleep(1)
        return False, "Failed to connect to AI for validation."

    @staticmethod
    def patch_chapter_chunk(raw_text, current_summary, qa_report):
        """Rewrite a chapter summary using QA feedback (RAG repair pass).

        Args:
            raw_text: Source turns prose for the chapter chunk.
            current_summary: Summary text to revise.
            qa_report: Validation output from :meth:`validate_chapter_chunk`.

        Returns:
            tuple[bool, dict | str]: ``(success, patched_summary_or_error)``.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit
        import requests, time, json, uuid
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_CHAPTER", "") + f"\n[ISOLATION_KEY: {uuid.uuid4()}]"
        user_prompt = PROMPTS.get("USER_MEMORY_CHAPTER_PATCH", "")
        user_prompt = user_prompt.replace("{raw_text}", raw_text)
        user_prompt = user_prompt.replace("{current_summary}", current_summary)
        user_prompt = user_prompt.replace("{qa_report}", qa_report)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        for attempt in range(2):
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.2, "max_tokens": ENGINE_CONFIG.get("max_tokens", 5000)
            }
            try:
                enforce_rate_limit()
                apply_json_response_format(payload)
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    raw = resp.json()['choices'][0]['message']['content'].strip()
                    clean_json = sanitize_json(raw)
                    data = json.loads(clean_json, strict=False)
                    if isinstance(data, dict): return True, data
            except Exception: time.sleep(2)
        return False, "Patching Failed."
        
        
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
                apply_json_response_format(payload)
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
    def deep_scan_entity(entity_name, current_profile_str, turns_text):
        """
        Surgical RAG: Extracts updates for one specific entity from a block of text.
        """
        from config import ENGINE_CONFIG, PROMPTS
        from llm import sanitize_json, enforce_rate_limit, translate_api_error
        import requests, time, json
        
        sys_prompt = PROMPTS.get("SYS_MEMORY_DEEP_SCAN", "")
        user_prompt = PROMPTS.get("USER_MEMORY_DEEP_SCAN", "")
        
        user_prompt = user_prompt.replace("{entity_name}", entity_name)
        user_prompt = user_prompt.replace("{current_profile}", current_profile_str)
        user_prompt = user_prompt.replace("{chunk_text}", turns_text)

        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
        headers = {"Content-Type": "application/json"}
        if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
            
        err = "Unknown Error"
        for attempt in range(3):
            input_tokens = int(len(turns_text.split()) * 1.5)
            dynamic_limit = min(ENGINE_CONFIG.get("max_tokens", 5000), max(500, input_tokens + 500))
            
            payload = {
                "model": ENGINE_CONFIG.get("model", "loaded-model"),
                "messages": messages, "temperature": 0.2, "max_tokens": dynamic_limit
            }
            try:
                enforce_rate_limit()
                apply_json_response_format(payload)
                resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=120)
                if resp.status_code != 200:
                    err = translate_api_error(response=resp)
                    time.sleep(2)
                    continue
                    
                raw = resp.json()['choices'][0]['message']['content'].strip()
                clean_json = sanitize_json(raw)
                data = json.loads(clean_json, strict=False)
                
                # Validation
                if isinstance(data, dict):
                    if "event" not in data: data["event"] = None
                    if "traits" not in data: data["traits"] = {}
                    return True, data
                    
                err = "AI did not return a valid JSON Dictionary."
                time.sleep(1)
            except Exception as e:
                err = translate_api_error(exception=e)
                time.sleep(2)
                continue
                
        return False, f"Deep Scan Failed:\n{err}"
        
        
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
                apply_json_response_format(payload)
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
                apply_json_response_format(payload)
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
                apply_json_response_format(payload)
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
        
        
    @staticmethod
    def download_samples(callback=None):
        """Downloads a samples.zip from GitHub and extracts it into /adventures/."""
        import requests, zipfile, io
        
        # CRITICAL: This URL must match your GitHub file name exactly (Case-Sensitive!)
        URL = "https://github.com/MeaningfulnessMediaGroup/TomeWeaver/raw/main/samples/Samples_v1.zip"
        
        try:
            if callback: callback("Connecting to GitHub...")
            # Use allow_redirects=True to handle GitHub's internal routing
            response = requests.get(URL, timeout=20, allow_redirects=True)
            response.raise_for_status()
            
            # --- ZIP HEADER VALIDATION ---
            # Every valid .zip file MUST start with the bytes 'PK' (0x50 0x4B)
            content = response.content
            if not content.startswith(b'PK'):
                # It's probably an HTML error page from GitHub.
                snippet = content[:100].decode('utf-8', errors='ignore')
                if "<!DOCTYPE" in snippet or "<html" in snippet:
                    return False, "Download failed: The link returned a webpage instead of a file. Check if the file name matches exactly (Case Sensitive!) and is Public."
                return False, "Download failed: Server did not return a valid ZIP archive."

            if callback: callback("Extracting archives...")
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                z.extractall(get_adv_dir())
                
            return True, "Samples downloaded successfully!"
        except Exception as e:
            return False, f"Network Error: {str(e)}"
