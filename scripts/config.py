"""
TomeWeaver: Configuration and Environment Module
------------------------------------------------
This module handles global path resolution, environment initialization, 
and cross-platform console utilities for the TomeWeaver engine.
"""

import re
import os
import json
import sys
import shutil
from pathlib import Path
from colorama import Fore, Style

# ---------------------------------------------------------
# GLOBAL PATHS
# ---------------------------------------------------------

# Resolve the absolute path to the project root directory
ROOT_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------
# CONSOLE UTILITIES
# ---------------------------------------------------------

def clear_screen():
    """
    Clears the terminal console in a cross-platform manner.
    Uses ANSI escape codes for modern terminals with a fallback to OS-level commands.
    """
    # ANSI escape: \033[2J clears the screen, \033[H resets the cursor to home
    print('\033[2J\033[H', end='')
    
    # Fallback to system-specific clear commands for legacy terminal compatibility
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')
        

# ---------------------------------------------------------
# JSON UTILITIES
# ---------------------------------------------------------

def load_json_safely(file_path, file_description):
    """
    Loads a JSON file with an added 'Pre-Parse Repair' layer. 
    This allows users to manually paste raw text (with literal newlines and 
    unescaped quotes) into story fields without breaking the engine.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # --- MANUAL PASTE REPAIR LAYER ---
        # We surgically target long-form text fields that users often edit manually.
        def fix_pasted_content(match):
            key_part = match.group(1)   # e.g., "story_text": "
            text_part = match.group(3)  # The actual raw text
            suffix = match.group(4)     # e.g., ", or "}
            
            # 1. Convert literal line breaks (Enter keys) to \n
            text_part = text_part.replace('\n', '\\n').replace('\r', '\\r')
            
            # 2. Escape unescaped double quotes (find " not preceded by \)
            # We use a negative lookbehind to ensure we don't double-escape.
            text_part = re.sub(r'(?<!\\)"', r'\"', text_part)
            
            return f'{key_part}{text_part}{suffix}'

        # List of keys likely to receive manual copy-pastes from external AIs
        targets = ["story_text", "introduction", "goal", "starting_situation", "inventory_and_state"]
        target_pattern = "|".join(targets)
        
        # Regex: Finds "key": " ... " followed by a comma or closing brace
        # Using re.DOTALL to allow the (.*?) to match across multiple lines
        repair_regex = rf'("({target_pattern})"\s*:\s*")(.*?)("\s*[,}}])'
        repaired_content = re.sub(repair_regex, fix_pasted_content, raw_content, flags=re.DOTALL)

        # Now parse the (potentially repaired) string
        return json.loads(repaired_content, strict=False)

    except json.JSONDecodeError as e:
        # --- (Existing Visual Error Reporter) ---
        print(f"\n{Fore.RED}=== JSON Syntax Error in {file_description} ===")
        print(f"{Fore.RED}File: {file_path}")
        print(f"{Fore.RED}Error: {e.msg} at line {e.lineno}, column {e.colno}")
        try:
            # We show the context from the raw file so the user can find their typo
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                error_line_idx = e.lineno - 1
                print(f"\n{Fore.YELLOW}Context (Actual file content):")
                if error_line_idx > 0:
                    print(f"{Style.DIM}{e.lineno - 1:4} | {lines[error_line_idx - 1].rstrip()}")
                if error_line_idx < len(lines):
                    print(f"{Fore.WHITE}{e.lineno:4} | {lines[error_line_idx].rstrip()}")
                    pointer = " " * (e.colno - 1 + 7) + "^" 
                    print(f"{Fore.RED}{pointer}")
        except Exception:
            pass 
        sys.exit(1)
    except Exception as e:
        print(f"{Fore.RED}Failed to read {file_description} ({file_path}): {str(e)}")
        sys.exit(1)


# ---------------------------------------------------------
# ENGINE CONFIGURATION
# ---------------------------------------------------------

def load_engine_config():
    """
    Loads the global engine settings from 'engine_config.json'.
    If the file is missing, it generates a default configuration.
    If the file exists but is missing new keys (from an update), it 
    merges the defaults into the existing file to prevent crashes.
    """
    config_path = ROOT_DIR / "engine_config.json"
    
    # Standard defaults for the TomeWeaver engine
    default_config = {
        "api_url": "http://localhost:1234/v1/chat/completions",
        "api_key": "",
        "model": "loaded-model",
        "temperature_base": 0.8,
        "max_retries": 5,
        "context_window": 6,
        "max_query_per_minute": 0,
        "max_tokens": 2000,
        "logging_enabled": True,
        "log_verbose": False,
        "log_raw_json_on_failure": False,
        "auto_polish": False
    }
    
    # 1. Create default config if it doesn't exist
    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    
    # 2. Load existing config (utilizing the repair layer in load_json_safely)
    config = load_json_safely(config_path, "engine_config.json")
    
    # 3. Migration Check: Ensure all default keys exist in the user's config
    needs_update = False
    for key, val in default_config.items():
        if key not in config:
            config[key] = val
            needs_update = True
            
    # Save the migrated config back to disk if keys were added
    if needs_update:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
            
    return config
    

# ---------------------------------------------------------
# DEFAULT FILE CREATION FOR NEW STORIES
# ---------------------------------------------------------

def create_boilerplate_files(adv_dir, mode):
    """
    Initializes a new adventure directory with the necessary JSON and TXT files.
    Attempts to copy 'default_setup' and 'default_prompt' files from the root.
    If those are missing, it generates a hardcoded fallback template.
    """
    setup_file = adv_dir / "setup.json"
    prompt_file = adv_dir / "system_prompt.txt"
    
    # Paths for source templates in the root directory
    default_setup = ROOT_DIR / f"default_setup_{mode}.json"
    default_prompt = ROOT_DIR / f"default_system_prompt_{mode}.txt"
    
    # --- SETUP.JSON INITIALIZATION ---
    if not setup_file.exists():
        if default_setup.exists():
            # Use the external template if available
            shutil.copy(default_setup, setup_file)
        else:
            # Fallback hardcoded template if default_setup file is missing
            template = {
                "mode": mode,
                "track_inventory": True if mode == "campaign" else False,
                "can_die": True if mode == "campaign" else False,
                "allow_cheats": False,  # Safety default for new campaigns
                "title": "The Default Adventure",
                "tone": "Mysterious, atmospheric, fast-paced",
                "goal": "Survive the night and find a way out.",
                "main_character": "Subject 84 (Amnesiac, agile, cautious)"
            }
            
            # Add mode-specific structure
            if mode == "campaign":
                template["plot_outline"] = [{"title": "Chapter 1", "goal": "Survive", "obstacles": "None"}]
            else:
                template["starting_situation"] = "Waking up in a cryo-pod with alarms blaring."
                
            with open(setup_file, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=4)
            
    # --- SYSTEM_PROMPT.TXT INITIALIZATION ---
    if not prompt_file.exists():
        if default_prompt.exists():
            shutil.copy(default_prompt, prompt_file)
        else:
            # Critical failure: The engine cannot run without instructions for the LLM
            print(f"{Fore.RED}Critical Error: Missing '{default_prompt.name}' in root directory.")
            sys.exit(1)
            
            

ENGINE_CONFIG = load_engine_config()