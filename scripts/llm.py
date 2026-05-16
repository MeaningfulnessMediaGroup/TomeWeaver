import json
import requests
import re
import time
import random
from colorama import Fore, Style
from config import ENGINE_CONFIG
from logger import log_llm_interaction

_request_timestamps =[]


def enforce_rate_limit():
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
    _request_timestamps = [t for t in _request_timestamps if current_time - t < 60.0]

    if len(_request_timestamps) >= max_qpm:
        oldest_request = _request_timestamps[0]
        sleep_duration = 60.0 - (current_time - oldest_request)
        if sleep_duration > 0:
            print(f"{Style.DIM}[Rate Limit] Pausing for {sleep_duration:.1f}s to respect '{max_qpm} RPM' limit...{Style.RESET_ALL}", end="\r")
            time.sleep(sleep_duration)
            print(" " * 70, end="\r") 
            
            current_time = time.time()
            _request_timestamps = [t for t in _request_timestamps if current_time - t < 60.0]

    _request_timestamps.append(current_time)


def validate_turn_schema(data, is_campaign=False, track_inventory=False, can_die=False, is_test_mode=False):
    """
    Final validation gatekeeper. Ensures the dictionary matches the required
    game engine schema and scrubs common LLM narrative artifacts from choices.
    """
    if not isinstance(data, dict): return None, "Output is not a dictionary"
    
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

    # --- SCHEMA DEFINITION ---
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
            
            # 2. Strip leading/trailing newlines, carriage returns, and spaces
            c_str = c_str.strip()
            
            # 3. Strip accidental wrapping quotes (e.g. "'Choice text'")
            c_str = c_str.strip("'\"")
            
            if c_str:
                cleaned_choices.append(c_str)
        
        data["choices"] = cleaned_choices
        
        # Shuffle for variety in gameplay (unless in deterministic test mode)
        if not is_test_mode:
            random.shuffle(data["choices"])
    else:
        data["choices"] = []
        
    # Always reset player_choice to None so the HUMAN player is forced to act
    data["player_choice"] = None 
    
    return data, None


def sanitize_json(raw):
    """
    Main entry point for JSON repair. Extracts the JSON block and applies
    a multi-stage repair pipeline: 
    1. Structural Extraction
    2. Naked Value Wrapping (The 'Libby' Fix)
    3. State-Machine Quote/Newline Repair
    4. Iterative Surgical Patching
    """
    # 1. Extract the JSON block (Handles Truncation)
    start_idx = raw.find('{')
    end_idx = raw.rfind('}')
    
    if start_idx == -1:
        return raw

    if end_idx == -1 or end_idx < start_idx:
        block = raw[start_idx:]
    else:
        block = raw[start_idx:end_idx+1]

    # 2. PRE-HEAL: Fix single-quoted keys and trailing commas
    block = re.sub(r"([{,])\s*'([^']+)'\s*:", r'\1 "\2":', block)
    block = re.sub(r"(:\s*)'([^']+)'(\s*[,}])", r'\1"\2"\3', block)
    block = re.sub(r',\s*([\]}])', r'\1', block)

    # 3. PRE-HEAL: Wrap Naked Values (The 'Libby' Fix)
    # This prevents the state-machine from flipping by ensuring values start/end with quotes.
    # Pattern A: Naked Start + Existing Closing Quote (e.g. : Libby ... up close ",)
    block = re.sub(
        r'("[\w_]+"\s*:\s*)(?![ \t]*["\[\{0-9\-]|true|false|null)([a-zA-Z].*?)("\s*[,}\]])',
        r'\1"\2\3',
        block,
        flags=re.DOTALL
    )
    # Pattern B: Naked Start + Naked End (e.g. : Libby lets out a giggle,)
    block = re.sub(
        r'("[\w_]+"\s*:\s*)(?![ \t]*["\[\{0-9\-]|true|false|null)([a-zA-Z].*?)\s*(?=[,}\]])',
        r'\1"\2"',
        block,
        flags=re.DOTALL
    )

    # 4. Apply State-Machine: Handle rogue internal quotes and literal newlines
    # (Calls the unchanged _repair_json_quotes_and_newlines function)
    block = _repair_json_quotes_and_newlines(block)

    # 5. Iterative Surgical Repair
    # If json.loads still fails, we use the error position (e.pos) to patch the string.
    max_fix_attempts = 4 
    for _ in range(max_fix_attempts):
        try:
            data = json.loads(block, strict=False)
            
            # SCHEMA HEALING: Ensure text fields are strings, not hallucinated objects
            for k in ["story_text", "inventory_and_state", "location", "goal_progress"]:
                if k in data and isinstance(data[k], (dict, list)):
                    data[k] = json.dumps(data[k])
            
            return json.dumps(data, indent=2)
            
        except json.JSONDecodeError as e:
            block = _attempt_surgical_fix(block, e)
            continue
            
    return block

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


def is_repetitive(prev_text, new_text, num_words=4): # Reduced from 6 to 4
    if not prev_text or not new_text: return False
    
    # Clean text: remove punctuation and lowercase
    clean_prev = re.sub(r'[^\w\s]', '', prev_text.lower()).split()
    clean_new = re.sub(r'[^\w\s]', '', new_text.lower()).split()
    
    # Grab the first few words
    start_prev = clean_prev[:num_words]
    start_new = clean_new[:num_words]
    
    # If the first 4 words are identical, the AI is likely stuck in a loop
    if len(start_prev) >= num_words and start_prev == start_new:
        return True
        
    return False

def extract_api_error(response):
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

    
# --- THE FIX: Added is_test_mode to the parameters ---
def get_llm_response(messages, attempt, adv_dir, prev_story_text=None, is_fix_mode=False, is_campaign=False, track_inventory=False, can_die=False, is_test_mode=False):
    temp_base = ENGINE_CONFIG.get("temperature_base", 0.8)
    temp = 0.3 + (attempt * 0.1) if is_fix_mode else min(1.5, temp_base + (attempt * 0.2))
        
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
            validated, err = validate_turn_schema(data, is_campaign, track_inventory, can_die, is_test_mode)
            
            if validated:
                if prev_story_text and not is_fix_mode and is_repetitive(prev_story_text, validated["story_text"]):
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
        
def generate_recap(setup_data, history):
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
        
        
        
def generate_narrative_bridge(prev_turn, action, current_turn):
    """
    Acts as a professional editor. Evaluates the transition between two turns.
    If a gap exists, it generates a narrative bridge and surgical patches.
    If the prose is already seamless, it returns "[OK]".
    """
    # We only send the end of the previous turn and the start of the current to focus the AI.
    p_last = prev_turn["story_text"].split('\n')[-1]
    c_first = current_turn["story_text"].split('\n')[0]
    
    system_prompt = (
        "You are a professional book editor. Your goal is to ensure a seamless narrative flow "
        "between two scenes by bridging the player's choice into the prose. "
        "You must output valid JSON."
    )
    
    user_prompt = (
        f"PREVIOUS SCENE END: {p_last}\n"
        f"PLAYER ACTION: {action}\n"
        f"NEXT SCENE START: {c_first}\n\n"
        "TASK:\n"
        "1. Evaluate if the PLAYER ACTION is already naturally described in the NEXT SCENE START.\n"
        "2. If it is already seamless, reply ONLY with the text: [OK]\n"
        "3. If there is a jump-cut, provide a JSON bridge object with these keys:\n"
        "   - 'action_text': 1-2 sentences describing the action and transition.\n"
        "   - 'outro_patch': {'remove': 'exact text to cut from end of previous scene', 'replace': 'new text'}\n"
        "   - 'intro_patch': {'remove': 'exact text to cut from start of next scene', 'replace': 'new text'}\n\n"
        "Note: Patches are optional. Use them only if the transition requires editing the existing prose. "
        "Otherwise, leave 'remove' and 'replace' as empty strings."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Use a low temperature for surgical consistency
    # We use the existing get_llm_response but with a flag or a simplified call
    headers = {"Content-Type": "application/json"}
    if ENGINE_CONFIG.get("api_key", "").strip():
        headers["Authorization"] = f"Bearer {ENGINE_CONFIG['api_key']}"
    
    payload = {
        "model": ENGINE_CONFIG.get("model"),
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 500
    }

    try:
        response = requests.post(ENGINE_CONFIG["api_url"], headers=headers, json=payload, timeout=30)
        raw = response.json()['choices'][0]['message']['content'].strip()
        
        if "[OK]" in raw.upper():
            return "OK"
            
        # Standardize and validate the bridge JSON
        from llm import sanitize_json
        clean_json = sanitize_json(raw)
        return json.loads(clean_json)
    except:
        return None # Fallback to no bridge if API fails