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
from config import ENGINE_CONFIG
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

def validate_turn_schema(data, prev_turn=None, is_campaign=False, track_inventory=False, can_die=False, is_test_mode=False):
    """
    Final validation gatekeeper. Ensures the dictionary matches the required
    game engine schema. Auto-fills missing static metadata from the previous turn 
    to save API retries. Scrubs common LLM narrative artifacts from choices.
    """
    if not isinstance(data, dict): return None, "Output is not a dictionary"
    
    # --- AUTO-HEALING (METADATA FALLBACKS) ---
    # If the AI got lazy and omitted static fields, we infer them from the previous turn
    if prev_turn:
        if "pov_character" not in data:
            data["pov_character"] = prev_turn.get("pov_character", "Unknown")
            
        if "location" not in data:
            data["location"] = prev_turn.get("location", "Unknown")
            
        if "is_game_over" not in data and can_die:
            # Assume survival unless explicitly stated otherwise
            data["is_game_over"] = False
            
        if "inventory_and_state" not in data and track_inventory:
            # Assume nothing changed if the AI forgot to track it
            data["inventory_and_state"] = prev_turn.get("inventory_and_state", "")

        if "chapter_goal_achieved" not in data and is_campaign:
            # Safest assumption: Goal is not met unless AI says so
            data["chapter_goal_achieved"] = False

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
    if is_campaign: 
        required_keys.add("chapter_goal_achieved")
        required_keys.add("goal_progress")
    if track_inventory: required_keys.add("inventory_and_state")
    if can_die: required_keys.add("is_game_over")
        
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys: return None, f"Missing required JSON keys: {missing_keys}"
        
    # --- THE CHOICE SCRUBBER ---
    if isinstance(data.get("choices"), list):
        cleaned_choices = []
        for c in data["choices"]:
            c_str = str(c)
            # 1. Remove LLM "Concatenation" artifacts (e.g. "Text" + "\n")
            c_str = c_str.replace('" + "', '').replace('\\" + \\"', '').replace('\" + \"', '')
            # 2. Remove escaped internal quotes if the choice was entirely encased in them
            # Fixes: "\"Tell me more.\"" -> "Tell me more."
            if c_str.startswith('\\"') and c_str.endswith('\\"'):
                c_str = c_str[2:-2]
            # 3. Strip leading/trailing newlines, spaces, and accidental raw quotes
            c_str = c_str.strip().strip("'\"")
            
            if c_str:
                cleaned_choices.append(c_str)
        
        data["choices"] = cleaned_choices
        
        # Shuffle for variety in gameplay (unless in explicit test mode)
        if not is_test_mode:
            # Create a deterministic seed based on the turn number and story length.
            # This ensures that if the user runs 'polish' or 'fix' on Turn 5, 
            # the shuffled order of the choices will remain exactly the same as before.
            # We add len(data["story_text"]) so different turns don't feel identical.
            turn_seed = data.get("turn", 0) + len(data.get("story_text", ""))
            
            # Save the current global random state so we don't break other systems
            state = random.getstate()
            
            random.seed(turn_seed)
            random.shuffle(data["choices"])
            
            # Restore the global random state
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
            
            # Strip ALL outer quotes recursively (handles '"Text"')
            while clean_line and clean_line[0] in ['"', "'"]: clean_line = clean_line[1:]
            while clean_line and clean_line[-1] in ['"', "'"]: clean_line = clean_line[:-1]
            
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

def extract_api_error(response):
    """Safely parses HTTP error objects returned by cloud LLM APIs."""
    try:
        err_json = response.json()
        if isinstance(err_json, list):
            return str(err_json)
        elif isinstance(err_json, dict):
            e = err_json.get("error", err_json)
            if isinstance(e, dict):
                return e.get("message", str(e))
            return str(e)
        return str(err_json)
    except:
        return response.text

    
def get_llm_response(messages, attempt, adv_dir, prev_story_text=None, is_fix_mode=False, is_campaign=False, track_inventory=False, can_die=False, is_test_mode=False):
    """
    Master API request function. Handles payload construction, dynamic 
    temperature scaling (cools down for syntax errors, heats up for loops), 
    API dispatch, and passes the raw response to the JSON Sanitizer.
    """
    temp_base = ENGINE_CONFIG.get("temperature_base", 0.8)
    
    # Analyze the reason for the retry by looking at the last injected feedback message
    last_msg = messages[-1].get("content", "") if messages else ""
    
    if "Linguistic loop detected" in last_msg:
        # If stuck in a creative rut, spike the temperature to force a new path
        temp = min(1.5, temp_base + 0.4)
    elif is_fix_mode:
        # Polish and Fix modes must be strictly deterministic
        temp = 0.3
    else:
        # CRITICAL FIX: For JSON syntax failures, LOWER the temperature on each retry.
        # High temperatures cause format collapse. Cold temperatures enforce logic.
        temp = max(0.2, temp_base - (attempt * 0.15))
        
    payload = {
        "model": ENGINE_CONFIG.get("model", "loaded-model"),
        "messages": messages,
        "temperature": temp,
        "max_tokens": ENGINE_CONFIG.get("max_tokens", 2000)
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
            err_msg = f"API Error {response.status_code}"
            log_llm_interaction(adv_dir, messages, response.text, error=err_msg, attempt=attempt+1)
            return None, err_msg, response.text
            
        raw = response.json()['choices'][0]['message']['content'].strip()
        clean_json = sanitize_json(raw)
        
        try:
            data = json.loads(clean_json, strict=False)
            
            # Pass prev_turn to the schema validator for auto-healing
            prev_turn = prev_story_text if isinstance(prev_story_text, dict) else None
            validated, err = validate_turn_schema(data, prev_turn, is_campaign, track_inventory, can_die, is_test_mode)
            
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
            
    except Exception as e:
        log_llm_interaction(adv_dir, messages, "CONNECTION_FAILURE", error=str(e), attempt=attempt+1)
        return None, str(e), ""


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
    messages =[
        {"role": "system", "content": f"Summarize the events of '{adv_title}'. Focus on the main plot, key events, and current situation."},
        {"role": "user", "content": "Adventure log:\n\n" + history_text + "\n\nWrite the recap."}
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
        
        

def generate_narrative_bridge(prev_turn, action, current_turn, debug=False):
    """
    Context-Aware Tense Converter with Mechanical Retry Loop.
    Searches the next scene to see if the action is already resolved. 
    If not, it mechanically converts the player's command into a single sentence.
    Includes strict length and regurgitation validators with a 3-attempt retry loop.
    """
    import sys
    import time
    import requests
    from colorama import Fore, Style
    from config import ENGINE_CONFIG
    
    c_text = current_turn.get("story_text", "").strip()
    turn_num = current_turn.get("turn", "?")
    pov = current_turn.get("pov_character", "The protagonist")
    
    if ENGINE_CONFIG.get("debug_novelizer", False): debug = True

    def log_status(msg):
        if debug:
            print(f"{Style.DIM}Novelizing Turn {turn_num}: {msg}{Style.RESET_ALL}")
        else:
            sys.stdout.write(f"\r{Style.DIM}Novelizing Turn {turn_num}: {msg}{Style.RESET_ALL}")
            sys.stdout.write(" " * max(0, 70 - len(msg)))
            sys.stdout.flush()

    system_prompt = (
        "You are a strict narrative parser. You follow instructions exactly and output only what is requested."
    )
    
    user_prompt = (
        f"CHARACTER: {pov}\n"
        f"ACTION TAKEN: {action}\n\n"
        f"NEXT SCENE:\n{c_text}\n\n"
        "TASK:\n"
        "1. Read the NEXT SCENE. Does it explicitly state that the CHARACTER performed the ACTION TAKEN?\n"
        "2. If YES, reply ONLY with the exact text: [OK]\n"
        "3. If NO (the scene skips directly to the result), rewrite the ACTION TAKEN into a single, third-person sentence.\n"
        "4. CRITICAL: Your sentence MUST match the tense (past or present) used in the NEXT SCENE.\n"
        "5. Output ONLY the sentence. Do not copy text from the scene. Do not explain.\n\n"
        "EXAMPLES IF NO:\n"
        "Action: climb the tree (If scene is past tense) -> Kaelen climbed the tree.\n"
        "Action: climb the tree (If scene is present tense) -> Kaelen climbs the tree."
    )

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
                if debug: print(f"   {Fore.RED}[REJECTED] Copied next scene: {raw_bridge}{Style.RESET_ALL}")
                messages.append({"role": "assistant", "content": raw_bridge})
                messages.append({"role": "user", "content": "REJECTED: You copied text from the NEXT SCENE. Convert the ACTION TAKEN into a NEW, single sentence."})
                continue
                
            # 2. Length Guard
            if len(raw_bridge) > 350:
                if debug: print(f"   {Fore.RED}[REJECTED] Too long ({len(raw_bridge)} chars): {raw_bridge[:100]}...{Style.RESET_ALL}")
                messages.append({"role": "assistant", "content": raw_bridge})
                messages.append({"role": "user", "content": "REJECTED: Your response is too long. Output ONLY ONE short sentence."})
                continue
                
            # If it passes validation, we are done!
            if debug:
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

    system_prompt = (
        "You are an interactive fiction engine. Your only job is to generate a JSON array "
        "of 3 to 6 brief actions the player can take next."
    )
    
    user_prompt = (
        f"CURRENT SCENE:\n{story_text}\n\n"
        "TASK:\n"
        "1. Based on the CURRENT SCENE, provide EXACTLY 3 to 6 logical choices for the player's next action.\n"
        "2. Each choice MUST be a short string (Max 15 words) describing ONLY the action, not the result.\n"
        "3. Output ONLY a raw JSON array of strings. No keys, no markdown.\n\n"
        "EXAMPLE OUTPUT:\n"
        '[\n  "Draw my sword and attack.",\n  "Run toward the heavy wooden door.",\n  "Search the room for clues."\n]'
    )

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