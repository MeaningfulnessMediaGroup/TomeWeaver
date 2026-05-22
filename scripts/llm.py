"""
TomeWeaver: LLM Communication and JSON Sanitization Module
----------------------------------------------------------
Handles all interactions with local and cloud Large Language Models.
Includes the 'Fortress' JSON sanitizer, schema validation, rate-limiting,
and specialized narrative tools (Recap, Novelizer Bridge).
"""

import json
import requests
import re
import time
import random

from colorama import Fore, Style
from config import ENGINE_CONFIG, PROMPTS
from logger import log_llm_interaction

# ---------------------------------------------------------
# GLOBALS & RATE LIMITING
# ---------------------------------------------------------

_request_timestamps = []

def enforce_rate_limit():
    """
    Implements a sliding-window rate limiter to prevent HTTP 429 errors 
    when using strict cloud providers (like OpenRouter).
    """
    global _request_timestamps
    try:
        max_qpm = ENGINE_CONFIG.get("max_query_per_minute", 0)
        if max_qpm is None or str(max_qpm).strip() == "":
            return
        max_qpm = int(max_qpm)
        if max_qpm <= 0:
            return
    except ValueError:
        return

    current_time = time.time()
    # Keep only timestamps from the last 60 seconds
    _request_timestamps = [t for t in _request_timestamps if current_time - t < 60.0]

    # If we hit the limit, calculate how long to sleep until the oldest request expires
    if len(_request_timestamps) >= max_qpm:
        oldest_request = _request_timestamps[0]
        sleep_duration = 60.0 - (current_time - oldest_request)
        if sleep_duration > 0:
            print(f"{Style.DIM}[Rate Limit] Pausing for {sleep_duration:.1f}s to respect '{max_qpm} RPM' limit...{Style.RESET_ALL}", end="\r")
            time.sleep(sleep_duration)
            print(" " * 70, end="\r") 
            
            # Recalculate window after sleeping
            current_time = time.time()
            _request_timestamps = [t for t in _request_timestamps if current_time - t < 60.0]

    _request_timestamps.append(current_time)


# ---------------------------------------------------------
# SCHEMA VALIDATION
# ---------------------------------------------------------

def validate_turn_schema(data, prev_turn=None, is_campaign=False, track_inventory=False, can_die=False, is_test_mode=False, inv_schema=None):
    """
    Final validation gatekeeper. Ensures the dictionary matches the required
    game engine schema. Auto-fills missing static metadata from the previous turn 
    to save API retries. Scrubs common LLM narrative artifacts from choices.
    """
    if not isinstance(data, dict): return None, "Output is not a dictionary"
    
    # --- AUTO-HEALING (METADATA FALLBACKS) ---
    if prev_turn:
        if "pov_character" not in data:
            data["pov_character"] = prev_turn.get("pov_character", "Unknown")
            
        if "location" not in data:
            data["location"] = prev_turn.get("location", "Unknown")
            
    # Force Mortality rules regardless of hallucination
    if not can_die:
        data["is_game_over"] = False
    elif "is_game_over" not in data:
        data["is_game_over"] = False
            
    # --- THE INVENTORY PATCHER (Zero-Trust) ---
    if track_inventory:
        curr_str = data.get("inventory_and_state", "")
        if not isinstance(curr_str, str): curr_str = ""
        
        # Baseline: Establish the strict skeleton from setup.json so keys are NEVER dropped
        merged_dict = {k: "None" for k in inv_schema.keys()} if inv_schema else {}
        
        # 1. Overlay the previous turn's data to establish continuity
        prev_str = ""
        if prev_turn:
            # Failsafe in case a legacy Turn 0 with the wrong key name exists in memory
            prev_str = prev_turn.get("inventory_and_state", prev_turn.get("inventory_dictionary", ""))
            
        if prev_str and isinstance(prev_str, str):
            for k, v in re.findall(r'([A-Za-z0-9_]+)\s*:\s*(.*?)(?=(?:[A-Za-z0-9_]+\s*:|$))', prev_str.replace("[Status]", "")):
                clean_k = k.strip()
                if inv_schema and clean_k not in inv_schema: continue
                merged_dict[clean_k] = v.split('\n')[0].strip(' .,;')
                
        # 2. Overlay the AI's current hallucinated data (Only allowing approved keys to overwrite)
        if curr_str:
            for k, v in re.findall(r'([A-Za-z0-9_]+)\s*:\s*(.*?)(?=(?:[A-Za-z0-9_]+\s*:|$))', curr_str.replace("[Status]", "")):
                clean_k = k.strip()
                if inv_schema and clean_k not in inv_schema: continue
                merged_dict[clean_k] = v.split('\n')[0].strip(' .,;')
                
        # 3. Rebuild the perfect string
        if merged_dict:
            data["inventory_and_state"] = " ".join([f"{k}: {v}." for k, v in merged_dict.items()]).strip()
        else:
            data["inventory_and_state"] = prev_str

    if "objective_achieved" not in data and is_campaign:
        # Safest assumption: Objective is not met unless AI says so
        data["objective_achieved"] = False

    # Infer Input Type based on context
    if "input_type" not in data:
        if data.get("text_prompt") and not data.get("choices"):
            data["input_type"] = "text"
        else:
            data["input_type"] = "choice"

    # --- THE HEALER: Structural Conversions ---
    # If the AI sent an object or list instead of a string for goals, flatten it.
    if "goal_progress" in data:
        val = data["goal_progress"]
        if isinstance(val, (list, dict)):
            if isinstance(val, dict):
                lines = []
                for k, v in val.items():
                    if isinstance(v, dict):
                        inner = ", ".join([f"{ik}: {iv}" for ik, iv in v.items()])
                        lines.append(f"• {k}: {inner}")
                    else:
                        lines.append(f"• {k}: {v}")
                data["goal_progress"] = "\n".join(lines)
            else:
                data["goal_progress"] = "\n".join([f"• {str(i)}" for i in val])
        else:
            data["goal_progress"] = str(val)

    # --- SCHEMA DEFINITION (Final Check) ---
    required_keys = {"story_text", "pov_character", "location", "input_type", "choices"}
    # The auditor now injects goal progression, so Phase 1 doesn't require it natively!
    if track_inventory: required_keys.add("inventory_and_state")
    if can_die: required_keys.add("is_game_over")
        
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys: return None, f"Missing required JSON keys: {missing_keys}"
    
    # --- THE PROSE FLATTENER (Hard-Return Removal) ---
    # Many LLMs artificially wrap text at 80 characters by inserting single \n tags mid-sentence.
    # We strip single newlines into spaces to allow the GUI to wrap dynamically, but preserve \n\n as paragraphs.
    for text_key in ["story_text", "narrative_bridge"]:
        if text_key in data and isinstance(data[text_key], str):
            # 1. Normalize all massive gaps (3+ newlines) down to exactly 2
            cleaned_text = re.sub(r'\n{3,}', '\n\n', data[text_key])
            # 2. Replace single newlines (that aren't part of a double newline) with a space
            cleaned_text = re.sub(r'(?<!\n)\n(?!\n)', ' ', cleaned_text)
            # 3. Clean up any double spaces created by the previous step
            cleaned_text = re.sub(r' {2,}', ' ', cleaned_text).strip()
            data[text_key] = cleaned_text
        
    # --- THE CHOICE SCRUBBER ---
    if isinstance(data.get("choices"), list):
        cleaned_choices = []
        
        # 0. Pre-flatten choices in case the AI illegally merged them with newlines
        flat_choices = []
        for c in data["choices"]:
            c_str = str(c)
            if '\n' in c_str:
                flat_choices.extend(c_str.split('\n'))
            else:
                flat_choices.append(c_str)
                
        for c_str in flat_choices:
            c_str = c_str.strip()
            if not c_str: continue
            
            # 0.5 Remove LLM inline editorial comments (e.g. "// #1 - Direct Progression" or "/* comment */")
            c_str = re.split(r'//|/\*', c_str)[0].strip()
            
            # 1. Remove LLM "Concatenation" artifacts (e.g. "Text" + "\n")
            c_str = c_str.replace('" + "', '').replace('\\" + \\"', '').replace('\" + \"', '')
            
            # 2. Strip leading and trailing array garbage (commas, colons, hyphens)
            c_str = re.sub(r"^[,;:\.\-\s]+", "", c_str)
            c_str = re.sub(r"[,;\s]+$", "", c_str)
            
            # 3. Aggressively strip all external wrapper quotes (handles typos like 'Action'')
            c_str = c_str.strip("\"' ")
                
            # 4. Convert any internal dialogue double-quotes into single-quotes 
            c_str = c_str.replace('"', "'")
            
            if c_str:
                cleaned_choices.append(c_str)
        
        data["choices"] = cleaned_choices
        
        # Shuffle for variety in gameplay (unless in explicit test mode)
        if not is_test_mode:
            turn_seed = data.get("turn", 0) + len(data.get("story_text", ""))
            state = random.getstate()
            random.seed(turn_seed)
            random.shuffle(data["choices"])
            random.setstate(state)
    else:
        data["choices"] = []
        
    # Always reset player_choice to None so the HUMAN player is forced to act
    data["player_choice"] = None 
    
    return data, None

# ---------------------------------------------------------
# THE "FORTRESS" JSON SANITIZER
# ---------------------------------------------------------

def sanitize_json(raw):
    """
    Main entry point for JSON repair. Extracts the JSON block and applies
    a multi-stage repair pipeline: 
    1. Structural Extraction
    2. Naked Value Wrapping & Stray Quote removal
    3. Array Quote-Soup Flattener
    4. State-Machine Quote/Newline Repair
    5. Iterative Surgical Patching
    """
    start_idx = raw.find('{')
    end_idx = raw.rfind('}')
    
    if start_idx == -1: return raw

    if end_idx == -1 or end_idx < start_idx:
        block = raw[start_idx:]
    else:
        block = raw[start_idx:end_idx+1]

    # --- 1. PRE-HEAL: Structural cleanup ---
    block = re.sub(r"([{,])\s*'([^']+)'\s*:", r'\1 "\2":', block)
    block = re.sub(r"(:\s*)'([^']+)'(\s*[,}])", r'\1"\2"\3', block)
    block = re.sub(r',\s*([\]}])', r'\1', block)

    # Remove stray quotes immediately following a comma (Fixes: room "," \n "key")
    block = re.sub(r',\s*"(?=\s*[\n\r]+\s*")', ',', block)

    # Wrap Naked Values (The 'Libby' Fix)
    block = re.sub(
        r'("[\w_]+"\s*:\s*)(?![ \t]*["\[\{0-9\-]|true|false|null)([a-zA-Z].*?)("\s*[,}\]])',
        r'\1"\2\3', block, flags=re.DOTALL
    )
    block = re.sub(
        r'("[\w_]+"\s*:\s*)(?![ \t]*["\[\{0-9\-]|true|false|null)([a-zA-Z].*?)\s*(?=[,}\]])',
        r'\1"\2"', block, flags=re.DOTALL
    )

    # --- 2. PRE-HEAL: Array Quote-Soup Flattener ---
    # Fixes chaotic single/double quote nesting inside the choices array
    def fix_choices_array(match):
        prefix, inner, suffix = match.groups()
        lines = inner.split('\n')
        cleaned_lines = []
        for line in lines:
            clean_line = line.strip()
            if not clean_line or clean_line in ["[", "]"]: continue
            
            # Remove trailing commas from the line
            clean_line = clean_line.rstrip(',')
            clean_line = clean_line.strip()
            
            # Remove existing invalid escapes on single quotes before processing
            clean_line = clean_line.replace("\\'", "'")
            
            # Strip list artifacts (- or *) that LLMs frequently mistakenly put inside the array
            clean_line = re.sub(r'^[-*]\s+', '', clean_line)
            
            # Strip wrapper quotes carefully to avoid eating internal dialogue quotes.
            # We only remove quotes if they match on BOTH ends.
            for _ in range(2):
                if len(clean_line) >= 2 and clean_line[0] == '"' and clean_line[-1] == '"':
                    clean_line = clean_line[1:-1]
                if len(clean_line) >= 2 and clean_line[0] == "'" and clean_line[-1] == "'":
                    clean_line = clean_line[1:-1]
            
            if clean_line:
                # 1. Temporarily protect already-escaped double quotes
                clean_line = clean_line.replace('\\"', '§ESC_QUOTE§')
                # 2. Escape all remaining raw double quotes
                clean_line = clean_line.replace('"', '\\"')
                # 3. Restore the previously protected quotes
                clean_line = clean_line.replace('§ESC_QUOTE§', '\\"')
                
                # CRITICAL: We DO NOT touch single quotes. They are valid in JSON strings.
                cleaned_lines.append(f'    "{clean_line}"')
                
        if cleaned_lines:
            new_inner = "\n" + ",\n".join(cleaned_lines) + "\n  "
            return prefix + new_inner + suffix
        return match.group(0)

    block = re.sub(r'("choices"\s*:\s*\[)(.*?)(\])', fix_choices_array, block, flags=re.DOTALL)

    # --- 3. STATE MACHINE REPAIR ---
    block = _repair_json_quotes_and_newlines(block)

    # --- 4. ITERATIVE SURGERY ---
    max_fix_attempts = 4 
    for _ in range(max_fix_attempts):
        try:
            data = json.loads(block, strict=False)
            # SCHEMA HEALING
            for k in ["story_text", "inventory_and_state", "location", "goal_progress"]:
                if k in data and isinstance(data[k], (dict, list)):
                    data[k] = json.dumps(data[k])
            return json.dumps(data, indent=2)
            
        except json.JSONDecodeError as e:
            block = _attempt_surgical_fix(block, e)
            continue
            
    # --- 6. NUCLEAR FAILSAFE (REGEX REBUILDER) ---
    # If standard surgery fails, aggressively scrape the raw string 
    # to rebuild the JSON from scratch before giving up.
    return _aggressive_regex_recovery(raw)


def _attempt_surgical_fix(block, e):
    """
    Targeted surgery based on Python's JSONDecodeError metadata.
    """
    pos = e.pos
    msg = e.msg.lower()
    
    # --- CASE 1: Naked Value (Emergency Fallback) ---
    if "expecting value" in msg:
        before = block[:pos].rstrip()
        if before.endswith(':'):
            after = block[pos:]
            # Capture until next key or end brace
            match = re.search(r'^(.*?)(?=\s*,\s*"\w+"\s*:|\s*\}$)', after, re.DOTALL)
            if match:
                val = match.group(1).strip()
                if val.lower() not in ["true", "false", "null"] and not val.replace('.','',1).isdigit():
                    return block[:pos] + f'"{val}"' + block[pos + len(match.group(1)):]

    # --- CASE 2: Stray Quotes Missing Escape ---
    if "expecting ',' delimiter" in msg or "expecting ':' delimiter" in msg:
        before = block[:pos]
        last_quote = before.rfind('"')
        # SAFETY CHECK: Only escape if the quote isn't followed by structural markers.
        # This prevents the corruption of key names (e.g. player_choice).
        if last_quote != -1 and (last_quote == 0 or before[last_quote-1] != '\\'):
            after = block[last_quote+1:]
            peek = after.strip()
            if not (peek and peek[0] in ': , } ]'):
                return block[:last_quote] + '\\"' + block[last_quote+1:]

    # --- CASE 3: Truncation & Hanging Brackets ---
    if "expecting" in msg or "unterminated" in msg or "end of input" in msg:
        block = block.strip()
        if block.endswith(','):
            block = block[:-1].rstrip()
        if block.count('"') % 2 != 0:
            block += '"'
        
        # Balance braces and brackets
        open_braces = block.count('{') - block.count('}')
        if open_braces > 0: block += ('}' * open_braces)
        open_brackets = block.count('[') - block.count(']')
        if open_brackets > 0: block += (']' * open_brackets)
            
        return block

    return block


def _repair_json_quotes_and_newlines(raw_str):
    """
    A Look-Ahead State Machine.
    Determines if a " character is a structural JSON boundary or a rogue 
    unescaped dialogue quote. Also converts literal newlines into \\n.
    """
    out = []
    state = 0  # 0: outside string, 1: inside string
    i = 0
    n = len(raw_str)
    
    # Valid characters that can mathematically follow a closing quote
    json_structure_chars = set(': , } ]')
    
    while i < n:
        char = raw_str[i]
        
        # --- STATE: OUTSIDE STRING ---
        if state == 0:
            out.append(char)
            if char == '"':
                state = 1
            i += 1
            
        # --- STATE: INSIDE STRING ---
        elif state == 1:
            # Handle Escaped Characters: Skip next char to avoid identifying \" as an end
            if char == '\\':
                out.append(char)
                if i + 1 < n:
                    out.append(raw_str[i+1])
                i += 2
                continue
                
            # Handle Potential End of String
            if char == '"':
                # LOOK-AHEAD: Is this a structural boundary?
                peek_idx = i + 1
                next_char = ''
                while peek_idx < n:
                    if not raw_str[peek_idx].isspace():
                        next_char = raw_str[peek_idx]
                        break
                    peek_idx += 1
                
                # If followed by structure or EOF, it's a real closing quote
                if next_char in json_structure_chars or next_char == '':
                    out.append(char)
                    state = 0
                else:
                    # Rogue dialogue quote detected! Escape it.
                    out.append('\\"')
            
            # Handle Literal Newlines: Convert actual 'Enter' keys to \n
            elif char == '\n':
                out.append('\\n')
            elif char == '\r':
                out.append('\\r')
            elif char == '\t':
                out.append('\\t')
            else:
                out.append(char)
            i += 1
            
    return ''.join(out)


def is_repetitive(prev_text, new_text, num_words=4):
    """
    Loop Detection. Compares the first N words of the new story text 
    with the previous turn. If identical, the AI is likely stuck in a loop.
    """
    if not prev_text or not new_text: return False
    
    # Clean text: remove punctuation and lowercase
    clean_prev = re.sub(r'[^\w\s]', '', prev_text.lower()).split()
    clean_new = re.sub(r'[^\w\s]', '', new_text.lower()).split()
    
    # Grab the first few words
    start_prev = clean_prev[:num_words]
    start_new = clean_new[:num_words]
    
    if len(start_prev) >= num_words and start_prev == start_new:
        return True
        
    return False


# ---------------------------------------------------------
# LLM API COMMUNICATION
# ---------------------------------------------------------

def translate_api_error(exception=None, response=None):
    """Safely translates HTTP codes and Network Exceptions into user-friendly error messages."""
    import requests
    
    # 1. Handle Hard Network Failures (Server offline, No internet)
    if exception:
        if isinstance(exception, requests.exceptions.ConnectionError):
            return "Server Unreachable (Connection Refused). Is your local AI (LM Studio) running, or are you offline?"
        if isinstance(exception, requests.exceptions.Timeout):
            return "Request Timed Out. The AI took too long to respond."
            
        # If it's a generic Python exception that leaked through, show its class name to help debug
        return f"Internal Exception [{type(exception).__name__}]: {str(exception)}"

    # 2. Handle API HTTP Status Codes
    if response is not None:
        code = response.status_code
        
        # A. EXTRACT EXACT PROVIDER ERROR FIRST
        provider_msg = ""
        try:
            err_data = response.json()
            if isinstance(err_data, dict):
                if "error" in err_data:
                    e = err_data["error"]
                    provider_msg = e.get('message', str(e)) if isinstance(e, dict) else str(e)
                elif "message" in err_data:
                    provider_msg = str(err_data["message"])
        except Exception:
            # If the response isn't JSON, grab the raw text block
            provider_msg = response.text[:200].strip() if response.text else ""

        # B. ASSIGN BROAD HTTP CONTEXT
        base_err = f"API Error [{code}]"
        if code == 400:
            base_err = "Bad Request (Error 400)"
        elif code == 401: 
            base_err = "Unauthorized Access (Error 401)"
        elif code == 403: 
            base_err = "Forbidden (Error 403)"
        elif code == 404: 
            base_err = "Endpoint Not Found (Error 404)"
        elif code == 429: 
            base_err = "Rate Limit Exceeded (Error 429)"
        elif code == 502:
            base_err = "Bad Gateway (Error 502)"
        elif code == 503:
            base_err = "Service Unavailable (Error 503)"
        elif code == 504:
            base_err = "Gateway Timeout (Error 504)"

        # C. COMBINE FOR MAXIMUM CLARITY
        if provider_msg:
            return f"{base_err}.\nServer Response: {provider_msg}"
        else:
            return f"{base_err}.\nServer Response: No specific message provided."
            
    return "Unknown Generation Error."

    
def get_llm_response(messages, attempt, adv_dir, prev_story_text=None, is_fix_mode=False, is_campaign=False, track_inventory=False, can_die=False, is_test_mode=False, inv_schema=None, override_tokens=None, override_temp=None):
    """
    Master API request function. Handles payload construction, dynamic 
    temperature scaling (cools down for syntax errors, heats up for loops), 
    API dispatch, and passes the raw response to the JSON Sanitizer.
    """
    temp_base = ENGINE_CONFIG.get("temperature_base", 0.8)
    
    # Analyze the reason for the retry by looking at the last injected feedback message
    last_msg = messages[-1].get("content", "") if messages else ""
    
    if override_temp is not None:
        # Strict Director override from the UI
        temp = override_temp
    elif "Linguistic loop detected" in last_msg:
        # If stuck in a creative rut, spike the temperature to force a new path
        temp = min(1.5, temp_base + 0.4)
    elif is_fix_mode:
        # Default Polish and Fix modes
        temp = 0.3
    else:
        # For JSON syntax failures, LOWER the temperature on each retry
        temp = max(0.2, temp_base - (attempt * 0.15))
        
    # Use dynamically calculated tokens if provided, otherwise default to global config
    final_max_tokens = override_tokens if override_tokens is not None else ENGINE_CONFIG.get("max_tokens", 2000)
        
    payload = {
        "model": ENGINE_CONFIG.get("model", "loaded-model"),
        "messages": messages,
        "temperature": temp,
        "max_tokens": final_max_tokens
    }
    
    api_url = ENGINE_CONFIG.get("api_url", "")
    if "generativelanguage.googleapis.com" not in api_url:
        payload["frequency_penalty"] = 0.3
        payload["presence_penalty"] = 0.4
    
    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip():
        headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
    
    try:
        enforce_rate_limit()
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            err_msg = translate_api_error(response=response)
            log_llm_interaction(adv_dir, messages, response.text, error=err_msg, attempt=attempt+1)
            return None, err_msg, response.text
            
        raw = response.json()['choices'][0]['message']['content'].strip()
        clean_json = sanitize_json(raw)
        
        try:
            data = json.loads(clean_json, strict=False)
            
            # Pass prev_turn to the schema validator for auto-healing
            prev_turn = prev_story_text if isinstance(prev_story_text, dict) else None
            validated, err = validate_turn_schema(data, prev_turn, is_campaign, track_inventory, can_die, is_test_mode, inv_schema)
            
            if validated:
                prev_text_str = prev_turn.get("story_text", "") if prev_turn else ""
                
                if prev_text_str and not is_fix_mode and is_repetitive(prev_text_str, validated["story_text"]):
                    err_loop = "Linguistic loop detected"
                    log_llm_interaction(adv_dir, messages, raw, error=err_loop, attempt=attempt+1)
                    return None, err_loop, raw
                
                log_llm_interaction(adv_dir, messages, raw, attempt=attempt+1)
                return validated, None, raw
            
            log_llm_interaction(adv_dir, messages, raw, error=err, attempt=attempt+1)
            return None, err, raw
                
        except json.JSONDecodeError as e:
            log_llm_interaction(adv_dir, messages, raw, error=f"JSON Parse Error: {str(e)}", attempt=attempt+1)
            return None, str(e), raw
            
    except requests.exceptions.RequestException as e:
        # Catches ACTUAL network drops, timeouts, and API server crashes
        err_msg = translate_api_error(exception=e)
        log_llm_interaction(adv_dir, messages, "NETWORK_ERROR", error=err_msg, attempt=attempt+1)
        return None, err_msg, ""
        
    except Exception as e:
        # Catches internal Python code crashes and prints the traceback to the console for easy debugging
        import traceback
        traceback.print_exc()
        log_llm_interaction(adv_dir, messages, "INTERNAL_ENGINE_CRASH", error=str(e), attempt=attempt+1)
        return None, f"Internal Engine Crash: {str(e)}", ""


# ---------------------------------------------------------
# NARRATIVE GENERATORS
# ---------------------------------------------------------

def generate_recap(setup_data, history):
    """
    Summarizes the entire adventure history to date. Useful for readers 
    or for loading context into long-term memory solutions.
    """
    history_text = "".join([f"{t.get('story_text', '')}\nPlayer Action: {t.get('player_choice', '')}\n\n" for t in history[:-1]])[-15000:]
    adv_title = setup_data.get('title', 'The Adventure')
    
    sys_prompt = PROMPTS.get("SYS_RECAP", "").replace("{adv_title}", adv_title)
    user_prompt = PROMPTS.get("USER_RECAP", "").replace("{history_text}", history_text)
    
    messages =[
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip(): headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
    payload = {"model": ENGINE_CONFIG.get("model", "loaded-model"), "messages": messages, "temperature": 0.5, "max_tokens": ENGINE_CONFIG.get("max_tokens", 2000)}
    
    try:
        enforce_rate_limit()
        response = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=120)
        
        if response.status_code != 200:
            return f"API Error ({response.status_code}): {extract_api_error(response)}"
            
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"Failed to generate recap: {str(e)}"
        
        

def generate_narrative_bridge(prev_turn, action, current_turn):
    """
    Context-Aware Tense Converter with Mechanical Retry Loop.
    Searches the next scene to see if the action is already resolved. 
    If not, it mechanically converts the player's command into a single sentence.
    Includes strict length and regurgitation validators with a 3-attempt retry loop.
    """
    import time
    import requests
    from colorama import Fore, Style
    from config import ENGINE_CONFIG
    
    c_text = current_turn.get("story_text", "").strip()
    turn_num = current_turn.get("turn", "?")
    pov = current_turn.get("pov_character", "The protagonist")

    def log_status(msg):
        # We now simply print to the UI Console tab
        print(f"{Style.DIM}Bridging Turn {turn_num}: {msg}{Style.RESET_ALL}")

    system_prompt = PROMPTS.get("SYS_BRIDGE", "")
    user_prompt = PROMPTS.get("USER_BRIDGE", "")
    user_prompt = user_prompt.replace("{pov}", pov)
    user_prompt = user_prompt.replace("{action}", action)
    user_prompt = user_prompt.replace("{c_text}", c_text)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip():
        headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
    
    max_attempts = 5
    for attempt in range(max_attempts):
        log_status(f"Converting action to prose (Attempt {attempt+1}/{max_attempts})...")
        
        payload = {
            "model": ENGINE_CONFIG.get("model"),
            "messages": messages,
            "temperature": 0.1 + (attempt * 0.2), # Slightly increase temp on retries
            "max_tokens": 60 
        }

        try:
            response = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
            raw_bridge = response.json()['choices'][0]['message']['content'].strip()
            
            if "[OK]" in raw_bridge.upper():
                log_status(f"{Fore.GREEN}[OK] Already seamless")
                return "[OK]"
                
            # Clean up common LLM artifacts
            raw_bridge = raw_bridge.replace("Output:", "").strip('\'" \n')
            if raw_bridge and raw_bridge[0].isdigit() and raw_bridge[1] in [".", ")"]:
                raw_bridge = raw_bridge[2:].strip()
            
            # --- MECHANICAL VALIDATORS ---
            # 1. Regurgitation Guard
            if raw_bridge in c_text and len(raw_bridge) > 10:
                print(f"   {Fore.RED}[REJECTED] Copied next scene: {raw_bridge}{Style.RESET_ALL}")
                messages.append({"role": "assistant", "content": raw_bridge})
                messages.append({"role": "user", "content": "REJECTED: You copied text from the NEXT SCENE. Convert the ACTION TAKEN into a NEW, single sentence."})
                continue
                
            # 2. Length Guard
            if len(raw_bridge) > 350:
                print(f"   {Fore.RED}[REJECTED] Too long ({len(raw_bridge)} chars): {raw_bridge[:100]}...{Style.RESET_ALL}")
                messages.append({"role": "assistant", "content": raw_bridge})
                messages.append({"role": "user", "content": "REJECTED: Your response is too long. Output ONLY ONE short sentence."})
                continue
                
            # If it passes validation, we are done!
            print(f"   {Fore.CYAN}[GENERATED]: {raw_bridge}{Style.RESET_ALL}")
                
            log_status(f"{Fore.GREEN}[OK] Bridge Created")
            return raw_bridge
            
        except requests.exceptions.RequestException as e:
            log_status(f"{Fore.RED}[WARNING] API Error on attempt {attempt+1}")
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
            return "[FAILED]"
            
    log_status(f"{Fore.RED}[FAILED] Max retries reached")
    return "[FAILED]"
    
def _aggressive_regex_recovery(raw):
    """
    Absolute last resort. If the LLM completely abandons JSON syntax 
    (e.g., outputs a plaintext list for choices), we use regex to scrape 
    the story and choices directly from the text and rebuild the JSON from scratch.
    """
    recovered = {}
    
    # 1. Scrape Story Text
    # Look for "story_text", capture everything until the next JSON key or a common list header
    story_match = re.search(r'"story_text"\s*:\s*"?([\s\S]*?)(?="\w+"\s*:|Player Choice|Player Action|Choices:|"choices"|\Z)', raw, re.IGNORECASE)
    if story_match:
        story = story_match.group(1).strip()
        # Clean up hanging quotes or braces from the scrape
        story = story.strip('",} \n\r')
        # Fix literal newlines so it JSON encodes safely
        story = story.replace('\n', '\\n').replace('\r', '')
        recovered["story_text"] = story
        
    # 2. Scrape Choices
    choices = []
    
    # Attempt A: Try to find a raw bracketed array first [ "a", "b" ]
    array_match = re.search(r'\[([\s\S]*?)\]', raw)
    if array_match:
        # Extract things inside quotes
        quotes = re.findall(r'"([^"]+)"|\'([^\']+)\'', array_match.group(1))
        for q in quotes:
            choice = q[0] if q[0] else q[1]
            if choice and len(choice) > 1 and choice.lower() not in ["ok", "failed", "approved", "rejected"]:
                choices.append(choice.strip())
                
    # Attempt B: If no array, look for plaintext list patterns (- Action, 1. Action, A: Action)
    if not choices:
        lines = raw.split('\n')
        for line in lines:
            line = line.strip()
            # Matches: "- choice", "* choice", "1. choice", "A) choice", "A: choice"
            match = re.match(r'^(?:[-*]|\d+[\.\)]|[A-Z][:|\)])\s*(.*)', line)
            if match:
                choice = match.group(1).strip().strip('",\'')
                if choice and choice.lower() not in ["story_text", "choices", "player action", "player choice"]:
                    choices.append(choice)
                    
    if choices:
        recovered["choices"] = choices
        
    # If we successfully scraped the absolute minimum required fields, rebuild it
    if "story_text" in recovered and "choices" in recovered:
        return json.dumps(recovered, indent=2)
        
    return raw # Give up, let the retry loop handle it
    
    
def generate_missing_choices(story_text, turn_num):
    """
    Surgical Choice Generator.
    If the AI fails to provide adequate choices for a generated turn, 
    this function asks the AI specifically for a JSON array of 3-6 new choices.
    """
    import sys
    import requests
    import re
    import time
    from colorama import Fore, Style
    from config import ENGINE_CONFIG
    
    print(f"{Style.DIM}Generating missing choices for Turn {turn_num}...{Style.RESET_ALL}")

    system_prompt = PROMPTS.get("SYS_CHOICES", "")
    user_prompt = PROMPTS.get("USER_CHOICES", "").replace("{story_text}", story_text)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip():
        headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
    
    max_attempts = 3
    for attempt in range(max_attempts):
        payload = {
            "model": ENGINE_CONFIG.get("model", "loaded-model"),
            "messages": messages,
            "temperature": 0.6 + (attempt * 0.1), # Warm temp for varied choices
            "max_tokens": 150 
        }

        try:
            response = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
            raw = response.json()['choices'][0]['message']['content'].strip()
            
            # Use the existing regex to aggressively extract the array
            array_match = re.search(r'\[([\s\S]*?)\]', raw)
            if array_match:
                quotes = re.findall(r'"([^"]+)"|\'([^\']+)\'', array_match.group(1))
                choices = []
                for q in quotes:
                    choice = q[0] if q[0] else q[1]
                    if choice and len(choice) > 1:
                        choices.append(choice.strip())
                        
                if len(choices) >= 2:
                    return choices
                    
            time.sleep(1)
        except Exception:
            time.sleep(1)
            continue
            
    # Absolute bottom-of-the-barrel fallback so the UI never crashes
    print(f"{Fore.RED}[System] LLM failed to generate choices. Using fallbacks.{Style.RESET_ALL}")
    return ["Proceed forward.", "Examine my surroundings.", "Take a moment to decide."]
    
    
def generate_single_choice(story_text, current_choices):
    """
    Surgical Choice Generator (Single).
    Asks the AI to read the current scene and the existing choices, 
    and provide exactly ONE new unique choice to replace a discarded one.
    """
    import sys
    import requests
    import re
    import time
    from colorama import Fore, Style
    from config import ENGINE_CONFIG, PROMPTS
    
    print(f"{Style.DIM}Generating single replacement choice...{Style.RESET_ALL}")

    sys_prompt = PROMPTS.get("SYS_SINGLE_CHOICE", "You are an interactive fiction engine. Output ONLY a JSON array containing one string.")
    
    choices_str = "\n".join([f"- {c}" for c in current_choices])
    user_prompt = PROMPTS.get("USER_SINGLE_CHOICE", "SCENE:\n{story_text}\n\nAVOID THESE CHOICES:\n{current_choices}\n\nOutput ONLY a raw JSON array containing ONE new choice string.")
    user_prompt = user_prompt.replace("{story_text}", story_text)
    user_prompt = user_prompt.replace("{current_choices}", choices_str)

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip():
        headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
    
    max_attempts = 3
    for attempt in range(max_attempts):
        payload = {
            "model": ENGINE_CONFIG.get("model", "loaded-model"),
            "messages": messages,
            "temperature": 0.7 + (attempt * 0.1), # Warm temp for creativity
            "max_tokens": 50 
        }

        try:
            response = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
            raw = response.json()['choices'][0]['message']['content'].strip()
            
            # Aggressively extract the single string from the array
            array_match = re.search(r'\[([\s\S]*?)\]', raw)
            if array_match:
                quotes = re.findall(r'"([^"]+)"|\'([^\']+)\'', array_match.group(1))
                for q in quotes:
                    choice = q[0] if q[0] else q[1]
                    if choice and len(choice) > 1:
                        return choice.strip()
                        
            time.sleep(1)
        except Exception:
            time.sleep(1)
            continue
            
    print(f"{Fore.RED}[System] LLM failed to generate a single choice.{Style.RESET_ALL}")
    return None
    
    
def evaluate_campaign_objective(context_turns, new_turn, active_obj, adv_dir):
    """
    Phase 2 Auditor: Runs a strict, low-temperature evaluation of the story text
    to determine if the active objective was explicitly completed.
    """
    import requests, time
    from colorama import Style
    from config import ENGINE_CONFIG, PROMPTS
    
    print(f"{Style.DIM}Auditing goal progression...{Style.RESET_ALL}")
    
    ctx_text = ""
    for t in context_turns:
        ctx_text += f"Turn {t.get('turn', '?')}: {t.get('story_text', '')}\nAction: {t.get('player_choice', '')}\n\n"
    
    ctx_text += f"LATEST SCENE:\n{new_turn.get('story_text', '')}\n"
    
    goal = active_obj.get("goal", "Survive")
    obs = active_obj.get("obstacles", "None")
    
    sys_prompt = PROMPTS.get("SYS_AUDITOR", "You are a strict game logic auditor. Output ONLY valid JSON.")
    user_prompt = PROMPTS.get("USER_AUDITOR", "").replace("{context}", ctx_text)
    user_prompt = user_prompt.replace("{goal}", goal).replace("{obstacles}", obs)
    
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]
    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip():
        headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
        
    for attempt in range(2):
        payload = {
            "model": ENGINE_CONFIG.get("model", "loaded-model"),
            "messages": messages,
            "temperature": 0.1,  # Near-zero temperature forces pure logic
            "max_tokens": 150
        }
        try:
            enforce_rate_limit()
            resp = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                raw = resp.json()['choices'][0]['message']['content'].strip()
                clean_json = sanitize_json(raw)
                data = json.loads(clean_json, strict=False)
                if isinstance(data, dict) and "objective_achieved" in data:
                    reason = data.get("reasoning", "Evaluated by Auditor.")
                    achieved = str(data["objective_achieved"]).lower() == "true"
                    return achieved, reason
        except Exception:
            time.sleep(1)
    
    return False, "Auditor failed to respond correctly. Defaulting to false."