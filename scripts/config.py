"""
TomeWeaver: Configuration and Environment Module
------------------------------------------------
This module handles global path resolution, environment initialization, 
prompt parsing, and cross-platform console utilities for the engine.
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
# INTERNAL_ROOT: bundled assets (PyInstaller _MEIPASS when frozen).
# USER_ROOT: writable data directory beside the executable or repo root.

# Internal Root: Where the code and bundled prompts live (Temp folder if EXE)
if getattr(sys, 'frozen', False):
    INTERNAL_ROOT = Path(sys._MEIPASS)
else:
    INTERNAL_ROOT = Path(__file__).resolve().parent.parent

# External Root: Where the EXE sits (User's folder for saves/configs)
if getattr(sys, 'frozen', False):
    USER_ROOT = Path(sys.executable).parent
else:
    USER_ROOT = Path(__file__).resolve().parent.parent

# 1. Prompts are BUNDLED (Internal)
PROMPTS_FILE = INTERNAL_ROOT / "configs" / "system_prompts.txt"

# 2. Configs and Adventures are PERSISTENT (External)
API_CONFIGS_DIR = USER_ROOT / "configs" / "API_configs"
# Note: ROOT_DIR is used by some loaders, we should point it to USER_ROOT for safety
ROOT_DIR = USER_ROOT


def _read_adventures_dir_from_disk():
    """Read ``adventures_dir`` from engine_config before ENGINE_CONFIG is loaded."""
    config_path = USER_ROOT / "configs" / "engine_config.json"
    if not config_path.exists():
        return ""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("adventures_dir", "") if isinstance(data, dict) else ""
    except Exception:
        return ""


def get_adventures_dir():
    """Return the resolved adventures library root (configurable via engine_config).

    When ``adventures_dir`` is empty or unset, defaults to ``USER_ROOT / adventures``.
    Relative paths are resolved against ``USER_ROOT``. The directory is created if missing.
    """
    custom = ""
    if "ENGINE_CONFIG" in globals():
        custom = ENGINE_CONFIG.get("adventures_dir", "")
    else:
        custom = _read_adventures_dir_from_disk()

    if isinstance(custom, str) and custom.strip():
        p = Path(custom.strip()).expanduser()
        p = (USER_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    else:
        p = (USER_ROOT / "adventures").resolve()

    p.mkdir(parents=True, exist_ok=True)
    return p


def get_default_adventures_dir():
    """Return the built-in default adventures path (``USER_ROOT / adventures``)."""
    return (USER_ROOT / "adventures").resolve()


def find_universe_root(start_path):
    """Walk upward from a story path to find a universe ``master_setup.json``.

    Args:
        start_path: File or directory inside ``adventures/``.

    Returns:
        Path | None: Universe root directory, or ``None`` if not in a universe.
    """
    curr = Path(start_path).resolve()
    limit = get_adventures_dir().resolve()
    
    # Climb up until we hit the adventures folder or the system root
    while curr != limit and curr.parent != curr:
        if (curr / "master_setup.json").exists():
            return curr
        curr = curr.parent
    return None


def hydrate_user_directory():
    """Copy bundled ``configs/`` to the user data dir on first run (frozen builds).

    Also ensures the adventures library folder exists (default or configured path).
    """
    internal_configs = INTERNAL_ROOT / "configs"
    external_configs = USER_ROOT / "configs"
    
    get_adventures_dir()
    
    if not external_configs.exists():
        print(f"First run detected. Hydrating configs from bundle...")
        try:
            # Copy all default json/txt files so the user has a starting point
            shutil.copytree(internal_configs, external_configs, dirs_exist_ok=True)
        except Exception as e:
            print(f"Hydration failed: {e}")

# Run the bootstrapper immediately on import
hydrate_user_directory()


# ---------------------------------------------------------
# SYSTEM PROMPTS PARSER
# ---------------------------------------------------------

def load_system_prompts():
    """
    Parses the custom system_prompts.txt configuration file.
    It completely ignores anything wrapped in ''' or \"\"\" to allow
    for multi-line Python-style developer comments without breaking the prompts.
    """
    if not PROMPTS_FILE.exists():
        raise FileNotFoundError(f"Critical Error: Missing '{PROMPTS_FILE.name}' in configs folder. Cannot load engine prompts.")
        
    prompts = {}
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    current_key = None
    current_text = []
    in_comment_block = False
    comment_marker = None
    
    # Regex to catch the exact header pattern [PROMPT:KEY_NAME]
    header_pattern = re.compile(r'^\[PROMPT:([A-Z0-9_]+)\]\s*$')

    for line in lines:
        stripped = line.strip()
        
        # Check for start/end of comment blocks
        if stripped in ["'''", '"""']:
            if not in_comment_block:
                in_comment_block = True
                comment_marker = stripped
            elif in_comment_block and stripped == comment_marker:
                in_comment_block = False
                comment_marker = None
            continue
            
        # If we are inside a block comment, ignore the line completely
        if in_comment_block:
            continue
            
        # Check if the line is a new Prompt Header
        match = header_pattern.match(stripped)
        if match:
            # Save the previous prompt (if any) before starting a new one
            if current_key is not None:
                prompts[current_key] = "".join(current_text).strip()
                
            current_key = match.group(1)
            current_text = []
            continue
            
        # Otherwise, append the line to the current prompt (preserving internal newlines)
        if current_key is not None:
            # We don't strip() here to preserve intentional line breaks and formatting
            current_text.append(line)
            
    # Save the very last prompt in the file
    if current_key is not None:
        prompts[current_key] = "".join(current_text).strip()
        
    return prompts
        
        
# Initialize the global dictionary so it's ready on boot
PROMPTS = load_system_prompts()

# ---------------------------------------------------------
# FIELD GUIDES (HELP & EXAMPLES) PARSER
# ---------------------------------------------------------

def load_field_guides():
    """
    Parses the configs/field_guides.txt file to populate the 💡 Help modals.
    Returns: { "UID": {"help": "string", "examples": [ {"mode": "ALL", "text": "..."} ] } }
    """
    guide_file = ROOT_DIR / "configs" / "field_guides.txt"
    if not guide_file.exists():
        return {}
        
    guides = {}
    with open(guide_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    current_key = None
    current_type = None # "help" or "example"
    current_text = []
    
    header_pattern = re.compile(r'^\[(HELP|EXAMPLE):([A-Z0-9_]+)\]\s*$')

    def save_block():
        if current_key and current_type:
            if current_key not in guides:
                guides[current_key] = {"help": "", "examples": []}
                
            text_block = "\n".join(current_text).strip()
            if current_type == "HELP":
                guides[current_key]["help"] = text_block
            elif current_type == "EXAMPLE":
                # Parse lines like: "SANDBOX: Bob the builder"
                for line in text_block.split('\n'):
                    if ':' in line:
                        mode_part, ex_text = line.split(':', 1)
                        guides[current_key]["examples"].append({
                            "mode": mode_part.strip().upper(),
                            "text": ex_text.strip()
                        })

    for line in lines:
        stripped = line.strip()
        # Ignore comments
        if stripped.startswith('#') or stripped in ["'''", '"""']:
            continue
            
        match = header_pattern.match(stripped)
        if match:
            save_block()
            current_type = match.group(1)
            current_key = match.group(2)
            current_text = []
            continue
            
        if current_key is not None and stripped:
            current_text.append(line.strip())
            
    save_block()
    return guides

FIELD_GUIDES = load_field_guides()


# ---------------------------------------------------------
# API PROFILE UTILITIES
# ---------------------------------------------------------

def init_api_profiles():
    """Ensures the API_configs folder exists and populates default templates."""
    API_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    defaults = {
        "LM_Studio": {"api_url": "http://localhost:1234/v1/chat/completions", "api_key": "", "model": "loaded-model", "max_query_per_minute": 0, "max_tokens": 2000},
        "OpenRouter": {"api_url": "https://openrouter.ai/api/v1/chat/completions", "api_key": "", "model": "anthropic/claude-3.5-sonnet", "max_query_per_minute": 0, "max_tokens": 2000},
        "OpenAI": {"api_url": "https://api.openai.com/v1/chat/completions", "api_key": "", "model": "gpt-4o", "max_query_per_minute": 0, "max_tokens": 2000},
        "Gemini": {"api_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent", "api_key": "", "model": "gemini-1.5-flash-latest", "max_query_per_minute": 15, "max_tokens": 2000}
    }
    for name, data in defaults.items():
        fpath = API_CONFIGS_DIR / f"{name}.json"
        if not fpath.exists():
            import json
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

def get_api_profiles():
    """Returns a sorted list of available API profile names."""
    if not API_CONFIGS_DIR.exists(): return []
    return sorted([f.stem for f in API_CONFIGS_DIR.glob("*.json")])

def load_api_profile(name):
    """Loads a specific API profile dictionary."""
    fpath = API_CONFIGS_DIR / f"{name}.json"
    if fpath.exists():
        import json
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------
# JSON UTILITIES
# ---------------------------------------------------------

def load_json_safely(file_path, file_description):
    """Load JSON with a regex repair pass for hand-edited adventure files.

    Args:
        file_path: Path to the ``.json`` file.
        file_description: Human label shown in syntax error reports.

    Returns:
        dict | list: Parsed JSON root object.

    Raises:
        ValueError: If repair and strict parse both fail.
        RuntimeError: If the file cannot be read.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # --- PHASE 1: FAST PATH ---
        try:
            return json.loads(raw_content, strict=False)
        except json.JSONDecodeError:
            # Standard load failed. Proceed to the Slow-Repair fallback.
            pass

        # --- PHASE 2: REPAIR FALLBACK (Slow Path) ---
        def fix_pasted_content(match):
            key_part, target_key, text_part, suffix = match.groups()
            # 1. Escape literal newlines
            text_part = text_part.replace('\n', '\\n').replace('\r', '\\r')
            # 2. Escape unescaped double quotes
            text_part = re.sub(r'(?<!\\)"', r'\"', text_part)
            return f'{key_part}{text_part}{suffix}'

        targets = ["story_text", "introduction", "goal", "starting_situation", "inventory_and_state"]
        target_pattern = "|".join(targets)
        repair_regex = rf'("({target_pattern})"\s*:\s*")(.*?)("\s*[,}}])'
        
        repaired_content = re.sub(repair_regex, fix_pasted_content, raw_content, flags=re.DOTALL)

        # Final attempt with repaired content
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
        raise ValueError(f"Critical Syntax Error in {file_description}. Please fix formatting before continuing.")
    except Exception as e:
        raise RuntimeError(f"Failed to read {file_description} ({file_path}): {str(e)}")

def save_json_atomically(data, file_path):
    """Write JSON via a temp file and atomic rename to prevent corruption.

    Args:
        data: JSON-serializable object to persist.
        file_path: Destination path (``.tmp`` sibling used during write).
    """
    import os
    path_obj = Path(file_path)
    temp_path = path_obj.with_suffix('.tmp')
    
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno()) # Force the OS to write buffers to the physical disk
            
        os.replace(temp_path, path_obj) # Atomic overwrite (safe on Windows/Mac/Linux)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink() # Clean up the temp file if the write failed
        raise e
        
# ---------------------------------------------------------
# ENGINE CONFIGURATION
# ---------------------------------------------------------

def load_engine_config():
    """
    Loads the global engine settings from 'configs/engine_config.json'.
    If the file is missing, it generates a default configuration.
    If the file exists but is missing new keys (from an update), it 
    merges the defaults into the existing file to prevent crashes.
    """
    configs_dir = ROOT_DIR / "configs"
    configs_dir.mkdir(exist_ok=True)
    config_path = configs_dir / "engine_config.json"
    
    # Ensure API connection profiles are built
    init_api_profiles()
    
    # Standard defaults for the TomeWeaver engine
    # Standard defaults for the TomeWeaver engine
    default_config = {
        "active_api_profile": "LM_Studio",
        "api_url": "http://localhost:1234/v1/chat/completions",
        "api_key": "",
        "model": "loaded-model",
        "temperature_base": 0.8,
        "max_retries": 5,
        "context_window": 15,
        "memory_decay_threshold": 40,
        "max_query_per_minute": 0,
        "max_tokens": 2000,
        "logging_enabled": True,
        "log_verbose": False,
        "log_raw_json_on_failure": False,
        "auto_polish": False,
        "auto_narrative_bridge": False,
        "ui_scaling": 1.0,
        "ui_wrap_margin": 150,
        "prose_font_family": "Georgia",
        "prose_font_size": 15,
        "max_inventory_keys": 8,
        "adventures_dir": "",
        "global_theme_name": "Default Dark"
    }
    
    if not config_path.exists():
        save_json_atomically(default_config, config_path)
        return default_config
    
    try:
        config = load_json_safely(config_path, "engine_config.json")
        if not isinstance(config, dict): raise ValueError("Config is not a JSON object")
    except Exception:
        print(f"{Fore.YELLOW}Warning: engine_config.json was corrupted. Rebuilding to defaults.{Style.RESET_ALL}")
        save_json_atomically(default_config, config_path)
        return default_config
    
    needs_update = False
    for key, val in default_config.items():
        if key not in config:
            config[key] = val
            needs_update = True
            
    # Clean up legacy volatile keys from engine_config
    for legacy_key in ["window_geometry", "window_state", "last_active_story", "memory_chunk_size", "use_local_theme_override"]:
        if legacy_key in config:
            del config[legacy_key]
            needs_update = True
            
    if needs_update:
        save_json_atomically(config, config_path)
            
    return config


# ---------------------------------------------------------
# VISUAL THEMES (Atmospheric Skinning)
# ---------------------------------------------------------

DEFAULT_THEME_PRESET = "Default Dark"

DEFAULT_THEME = {
    "outer": "#121212",
    "mid": "#1e1e1e",
    "inner": "#2a2a2a",
    "chapter_title": "#00ACC1",
    "player_action": "#4CAF50",
    "border_w": 1,
    "rounding": 10,
}

BUILTIN_THEME_PRESETS = {
    DEFAULT_THEME_PRESET: dict(DEFAULT_THEME),
    "Default Light": {
        "outer": "#e6e6e6",
        "mid": "#d9d9d9",
        "inner": "#cccccc",
        "chapter_title": "#00838F",
        "player_action": "#2E7D32",
        "border_w": 1,
        "rounding": 10,
    },
    "Parchment": {
        "outer": "#d2b48c",
        "mid": "#e5d3b3",
        "inner": "#f5f5dc",
        "chapter_title": "#00695C",
        "player_action": "#558B2F",
        "border_w": 2,
        "rounding": 2,
    },
    "Horror": {
        "outer": "#0a0000",
        "mid": "#1a0505",
        "inner": "#2d0a0a",
        "chapter_title": "#E57373",
        "player_action": "#7CB342",
        "border_w": 2,
        "rounding": 4,
    },
    "Cyberpunk": {
        "outer": "#0a0e14",
        "mid": "#0f1a2e",
        "inner": "#152238",
        "chapter_title": "#00E5FF",
        "player_action": "#69F0AE",
        "border_w": 1,
        "rounding": 16,
    },
    "Forest": {
        "outer": "#0d1810",
        "mid": "#152318",
        "inner": "#1e3024",
        "chapter_title": "#4DD0E1",
        "player_action": "#81C784",
        "border_w": 1,
        "rounding": 8,
    },
    "Ocean Deep": {
        "outer": "#0a1520",
        "mid": "#0f1f2e",
        "inner": "#152a3d",
        "chapter_title": "#4FC3F7",
        "player_action": "#66BB6A",
        "border_w": 1,
        "rounding": 12,
    },
    "Sunset Ember": {
        "outer": "#1a1208",
        "mid": "#2a1a0e",
        "inner": "#3d2512",
        "chapter_title": "#FFB74D",
        "player_action": "#9CCC65",
        "border_w": 2,
        "rounding": 6,
    },
    "Slate Light": {
        "outer": "#e4e8ec",
        "mid": "#d8dde3",
        "inner": "#ccd2d9",
        "chapter_title": "#0277BD",
        "player_action": "#388E3C",
        "border_w": 1,
        "rounding": 8,
    },
    "Rosewood": {
        "outer": "#1a0f14",
        "mid": "#2a1620",
        "inner": "#3a1f2c",
        "chapter_title": "#F48FB1",
        "player_action": "#A5D6A7",
        "border_w": 1,
        "rounding": 10,
    },
    "Nord Frost": {
        "outer": "#2e3440",
        "mid": "#3b4252",
        "inner": "#434c5e",
        "chapter_title": "#88C0D0",
        "player_action": "#A3BE8C",
        "border_w": 1,
        "rounding": 10,
    },
}


def get_default_theme():
    """Return a copy of the built-in default theme dict."""
    return dict(DEFAULT_THEME)


def load_themes():
    """Load preset gallery from ``configs/themes.json``, merging defaults if missing."""
    configs_dir = ROOT_DIR / "configs"
    configs_dir.mkdir(exist_ok=True)
    themes_path = configs_dir / "themes.json"

    seed = {name: dict(preset) for name, preset in BUILTIN_THEME_PRESETS.items()}

    if not themes_path.exists():
        save_json_atomically(seed, themes_path)
        return seed

    try:
        data = load_json_safely(themes_path, "themes.json")
        if not isinstance(data, dict):
            raise ValueError("themes.json is not an object")
    except Exception:
        print(f"{Fore.YELLOW}Warning: themes.json was corrupted. Rebuilding defaults.{Style.RESET_ALL}")
        save_json_atomically(seed, themes_path)
        return seed

    changed = False
    for name, preset in seed.items():
        if name not in data:
            data[name] = dict(preset)
            changed = True

    for name, preset in data.items():
        if not isinstance(preset, dict):
            continue
        for key, val in DEFAULT_THEME.items():
            if key not in preset:
                preset[key] = val
                changed = True

    if changed:
        save_json_atomically(data, themes_path)

    return data


def save_themes(themes_dict):
    """Persist the full preset gallery to ``configs/themes.json``."""
    save_json_atomically(themes_dict, ROOT_DIR / "configs" / "themes.json")


def load_instance_config():
    """Loads volatile session settings safely. Heals the file automatically if corrupted."""
    configs_dir = ROOT_DIR / "configs"
    config_path = configs_dir / "instance_config.json"
    
    default_config = {
        "window_geometry": "1100x750",
        "window_state": "normal",
        "last_active_story": "",
        "last_author": "Anonymous",
        "story_bookmarks": {},  # Maps 'Rel/Path/To/Story': turn_index
        "story_theme_preference": {},  # Maps folder path -> "global" | "story"
        "force_chapter_transition_mode": "wrap_up",  # wrap_up | immediate
    }
    
    # If missing entirely, create it
    if not config_path.exists():
        save_json_atomically(default_config, config_path)
        return default_config
    
    # If corrupted or 0 bytes, self-heal
    try:
        config = load_json_safely(config_path, "instance_config.json")
        if not isinstance(config, dict): raise ValueError("Config is not a JSON object")
    except Exception:
        print(f"{Fore.YELLOW}Warning: instance_config.json was corrupted. Rebuilding to defaults.{Style.RESET_ALL}")
        save_json_atomically(default_config, config_path)
        return default_config
        
    needs_update = False
    for key, val in default_config.items():
        if key not in config:
            config[key] = val
            needs_update = True
            
    if needs_update:
        save_json_atomically(config, config_path)
        
    return config


# ---------------------------------------------------------
# DEFAULT FILE CREATION FOR NEW STORIES
# ---------------------------------------------------------

def create_boilerplate_files(adv_dir, mode):
    """Seed a new adventure folder with ``setup.json`` and ``system_prompt.txt``.

    Args:
        adv_dir: Target adventure directory (created if needed).
        mode: ``"sandbox"`` or ``"campaign"`` template selector.

    Raises:
        FileNotFoundError: If the system prompt template is missing and no
            fallback can be generated.
    """
    setup_file = adv_dir / "setup.json"
    prompt_file = adv_dir / "system_prompt.txt"
    
    # Paths for source templates in the configs directory
    default_setup = ROOT_DIR / "configs" / f"default_setup_{mode}.json"
    default_prompt = ROOT_DIR / "configs" / f"default_system_prompt_{mode}.txt"
    
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
                template["plot_outline"] = [{
                    "title": "Chapter 1", 
                    "objectives": [{
                        "goal": "Survive the night.", 
                        "obstacles": "Hostile environment.",
                        "setting": "",
                        "pov": ""
                    }]
                }]
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
            raise FileNotFoundError(f"Critical Error: Missing template file '{default_prompt.name}' in the root directory. Cannot initialize new story.")
            

ENGINE_CONFIG = load_engine_config()
INSTANCE_CONFIG = load_instance_config()