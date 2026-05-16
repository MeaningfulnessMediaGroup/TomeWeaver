"""
TomeWeaver: Logger Module
-------------------------
The "Flight Recorder" for the engine. Handles writing system events, 
user actions, and raw LLM interactions to the session_log.txt file 
for debugging and telemetry purposes.
"""

import datetime
from pathlib import Path

# ---------------------------------------------------------
# SYSTEM LOGGING
# ---------------------------------------------------------

def log_event(adv_dir, message):
    """
    Appends a standard system or user event to the session log 
    with a timestamp. Bypassed if logging_enabled is False.
    """
    from config import ENGINE_CONFIG
    if not ENGINE_CONFIG.get("logging_enabled", True): return
    
    log_file = Path(adv_dir) / "session_log.txt"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

# ---------------------------------------------------------
# LLM DIAGNOSTIC LOGGING
# ---------------------------------------------------------

def log_llm_interaction(adv_dir, messages, response_raw, error=None, attempt=1):
    """
    Logs the raw interactions with the LLM API. Specifically designed to 
    capture JSON syntax errors, rate limits, and full prompts based on 
    the verbosity settings in engine_config.json.
    """
    from config import ENGINE_CONFIG
    if not ENGINE_CONFIG.get("logging_enabled", True): return
    
    # Logic: 
    # 1. If it's a success, only log if verbose is on.
    # 2. If it's a failure, log the raw output if 'log_raw_json_on_failure' is on.
    # 3. Only log the prompt if 'log_verbose' is on.
    
    is_failure = error is not None
    should_log_raw = ENGINE_CONFIG.get("log_verbose", False) or (is_failure and ENGINE_CONFIG.get("log_raw_json_on_failure", True))
    
    if not should_log_raw:
        return

    log_file = Path(adv_dir) / "session_log.txt"
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n" + "="*60 + "\n")
        f.write(f"LLM {'FAILURE' if is_failure else 'SUCCESS'} at {timestamp} - Attempt {attempt}\n")
        
        if error: 
            f.write(f"ERROR: {error}\n")
            
        if ENGINE_CONFIG.get("log_verbose", False):
            f.write("-" * 20 + " [FULL PROMPT] " + "-" * 20 + "\n")
            for m in messages:
                f.write(f"[{m['role'].upper()}]: {m['content']}\n")
        
        f.write("-" * 20 + " [RAW LLM OUTPUT] " + "-" * 20 + "\n")
        f.write(f"{response_raw}\n")
        f.write("="*60 + "\n\n")