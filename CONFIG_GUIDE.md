# TomeWeaver: Configuration Guide

This guide provides a detailed breakdown of the JSON schemas used by TomeWeaver. Use these configurations to fine-tune the AI's behavior and define the "DNA" of your adventure.

---

## ⚙️ Global Engine Configuration

The `engine_config.json` file in the root directory manages the global behavior of the engine, including API settings, memory limits, and the self-healing "Fortress" logic. Refer to typical configuration templates in the "configs" directory.

```json
{
    "api_url": "http://localhost:1234/v1/chat/completions",
    "api_key": "",
    "model": "loaded-model",
    "temperature_base": 0.8,
    "max_retries": 10,
    "context_window": 10,
    "max_query_per_minute": 0,
    "max_tokens": 2000,
    "logging_enabled": true,
    "log_verbose": false, 
    "log_raw_json_on_failure": true
}
```

### Configuration Parameters:

| Key | Description |
| :--- | :--- |
| **`api_url`** | The OpenAI-compatible endpoint. (e.g., `http://localhost:1234/v1/chat/completions` for LM Studio). |
| **`api_key`** | Your secret key for cloud services (OpenAI, OpenRouter, Grok). Leave empty for LM Studio. |
| **`model`** | The specific model identifier. Use `loaded-model` for LM Studio or IDs like `gpt-4o`. |
| **`temperature_base`** | Base creativity level (0.0 to 2.0). The engine automatically raises this during retries to break linguistic loops. |
| **`max_retries`** | The number of times the "Fortress" logic will attempt to surgically heal and re-parse broken LLM output. |
| **`context_window`** | The number of previous narrative turns the AI remembers. Higher values increase depth but also token cost. |
| **`max_query_per_minute`** | A rate-limiter to avoid 429 errors on cloud providers. Set to `0` for no limit (local play). |
| **`max_tokens`** | The hard limit for the AI's response length per turn. |
| **`logging_enabled`** | Master switch for the `session_log.txt` generated in every adventure folder. |
| **`log_verbose`** | If `true`, the engine logs the full JSON prompts sent to the AI (useful for prompt engineering). |
| **`log_raw_json_on_failure`** | Logs the raw, un-sanitized string when the AI fails to produce valid JSON to help diagnose model issues. |

***Refer to the configs directory to see samples of a few configuration files for the supported (tested) Cloud AI LLM.

### 🛡️ Understanding the "Fortress" Retry System

Local LLMs (especially smaller 8B models) will occasionally hallucinate, break strict JSON formatting, or get stuck in linguistic loops. TomeWeaver is designed to be highly resilient against this, acting as a "Fortress" around the game state.

Here is how the engine handles failures based on your `max_retries` setting:

**1. The Self-Healing Loop**
If the LLM returns invalid JSON (e.g., missing a quote, unescaped dialogue, or omitting a mandatory key like `"is_game_over"`), the engine intercepts it.
* It first attempts to run the **Surgical Sanitizer** to auto-fix the text without burning an API call.
* If the surgery fails, it triggers a **Retry**.

**2. The AI Feedback Loop**
On a Retry, the engine does not just resend the prompt. It dynamically appends the Python error to the prompt (e.g., *"Your previous JSON was invalid. Error: Expecting ',' delimiter. Please fix."*). This teaches the AI exactly what it broke so it can correct itself.

**3. Temperature Escalation**
If the AI gets stuck in a repetitive loop (starting 3 turns in a row with the exact same 4 words), the engine will reject the turn and trigger a Retry. With each retry, the engine slightly raises the `temperature` to forcefully bump the AI out of its rut.

**4. Critical Failure (Engine Stop)**
If the engine hits the `max_retries` limit (default is 10) and the LLM *still* cannot produce a valid, schema-compliant JSON object, **TomeWeaver will safely halt**. 
* The engine will print a `Critical Error: Max retries exceeded` message and close.
* **Your game state is perfectly safe.** Because the engine only saves *valid* turns to `history.json`, your save file is never corrupted by the failure.
* To resume, simply review the `session_log.txt` to see why the AI was failing, tweak your `setup.json` or system prompt if necessary, and launch the game again. It will pick up exactly where you left off.

---

### 🗺️ Adventure Configuration (`setup.json`)

The `setup.json` file acts as the "DNA" of your adventure. It defines the rules, the world, and the characters. While the engine requires specific keys to function, it is designed to be **extensible**—any custom field you add will be processed by the LLM as part of the world-building lore.

#### ⚠️ Essential Rules
1. **Never Remove Core Fields:** You can modify the values of the fields shown in the examples below, but do not delete the keys themselves, as the engine relies on them for logic.
2. **Infinite World Building:** You are encouraged to add **any** additional fields to provide depth (e.g., `family`, `traits`, `world_history`).
3. **Mid-Game Evolution:** This JSON is sent to the LLM every turn. If you edit `setup.json` in the middle of a game, the AI will immediately adapt to the new "facts" of your world.

---

#### Option A: Campaign Mode
Use this for structured, plot-heavy stories with defined goals and a sequence of chapters. 

```json
{
    "mode": "campaign",
    "track_inventory": true,
    "can_die": true,
    "title": "The Heist of the Ruby Skull",
    "tone": "Gritty, tense, low-fantasy",
    "main_character": "Kaelen, a master thief.",
    "lore_and_rules": "The Tomb is cursed. Magic items glow when near danger. Kaelen is mortal and must rely on stealth and tools rather than brute strength.",
    "starting_inventory": "[Status] Health: Good. Items: Short sword, Backpack (2 rations, bottle of water), Rope (30ft), Torch (unlit). State: Mischievious.",
    "plot_outline": [
        {
            "title": "The City Gates",
            "setting": "The slums outside the walls of Oakhaven. Midnight.",
            "pov": "Kaelen",
            "goal": "Find a way to sneak past or bribe the city guards to enter Oakhaven.",
            "obstacles": "The guards are highly alert. Kaelen has no money for a bribe."
        },
        {
            "title": "The Noble's Estate",
            "setting": "The courtyard of Lord Vane's massive estate.",
            "pov": "Kaelen",
            "time": "Later that night",
            "goal": "Break into the manor and locate the safe holding the Ruby Skull.",
            "obstacles": "Locked doors, patrolling guard dogs, trap runes on the windows."
        }
    ],
    "narrative": {
        "prologue": "expand",
        "epilogue": "as_is"
    },
    "allow_cheats": false
}
```

#### Campaign Mode: Field Definitions

| Key | Description |
| :--- | :--- |
| **`mode`** | Must be set to `"campaign"`. Triggers the plot-driven engine logic. |
| **`track_inventory`** | If `true`, the engine forces the LLM to track items and health in every response. |
| **`can_die`** | If `true`, the engine allows the LLM to trigger a "Game Over" state for the player. |
| **`lore_and_rules`** | Global constraints and "truths" the AI must respect throughout the whole story. |
| **`starting_inventory`**| The initial string describing the player's status and gear at Turn 1. |
| **`plot_outline`** | An array of chapter objects. The engine advances through these sequentially. |
| **`narrative`** | Defines how the engine handles external text assets (see below for details). |
| **`allow_cheats`** | If `false`, the `fix:` command and `undo` are disabled to enforce a "Hardcore" run. |

#### 📂 The Plot Outline (Chapter Object)
Each chapter in the `plot_outline` array supports these keys:
*   **`title`**: The name of the chapter (displayed in the UI).
*   **`setting`**: Detailed description of the area where this chapter takes place.
*   **`pov`**: The name of the character whose perspective the AI must maintain.
*   **`goal`**: The specific condition the AI checks to decide when to end the chapter.
*   **`obstacles`**: Specific threats or barriers the AI should introduce to prevent a "speedrun."
*   **`time`** *(Optional)*: Injects a time-jump instruction (e.g., "Two days later").

---

#### 📖 Understanding the "Narrative" Settings

The `narrative` object controls how TomeWeaver handles your `prologue.txt` and `epilogue.txt` files.

| Value | Behavior |
| :--- | :--- |
| **`none`** | **(The Skip Option)** The engine completely ignores this phase. The game skips the "Turn 0" intro and proceeds directly to the start of the adventure. |
| **`generate`** | **(The Full AI Option)** The engine ignores external text files and asks the AI to generate a cinematic introduction based on the world setup. |
| **`expand`** | **(The Hybrid Option)** Requires a `.txt` file. The AI uses your text as a "seed" to write a rich, multi-paragraph opening. |
| **`as_is`** | **(The Manual Option)** Requires a `.txt` file. The engine displays your text exactly as written, bypassing the AI entirely. |

**Example Usage:**
- Use `expand` if you only have a few bullet points in your prologue and want the AI to "cinematize" them.
- Use `as_is` if you have written a professional, custom introduction that you don't want the AI to touch.

**Note on Fallbacks:** If you set a field to `expand` or `as_is` but the corresponding `.txt` file is missing from the adventure folder, the engine will automatically fallback to `generate` mode to prevent a crash.

---

### 🌟 The "Story Seed" (`start_turn.json`)

TomeWeaver supports a specialized feature for adventure authors called the **Story Seed**. 

If you want your adventure to start with a specific, hand-crafted first turn (instead of letting the AI generate one), place a file named `start_turn.json` in your adventure folder.

**How it works:**
1. When the game starts (after the Prologue), the engine checks for `start_turn.json`.
2. If found, it **loads this file as Turn 1** instead of calling the AI.
3. This ensures every player begins with the same high-quality prose, location, and set of initial choices.
4. On Turn 2, the AI takes over, using your "Seed" as the context for its style and tone.

**Pro-Tip:** To create a seed, just play your adventure, `fix:` the AI's first turn until it's perfect, then copy that block from `history.json` into a new `start_turn.json` file.


---

#### Option B: Sandbox Mode
Use this for open-ended "What if?" simulations and player-driven exploration where the world is persistent but the plot is free-form.

```json
{
    "mode": "sandbox",
    "track_inventory": false,
    "can_die": false,
    "title": "The Default Adventure",
    "tone": "Mysterious, atmospheric, fast-paced",
    "goal": "Survive the night and find a way out.",
    "setting": "An abandoned sci-fi research facility on a frozen moon.",
    "main_character": "Subject 84 (Amnesiac, agile, cautious)",
    "starting_situation": "Waking up in a cryo-pod with alarms blaring.",
    "allow_cheats": true
}
```

#### Sandbox Mode: Field Definitions

| Key | Description |
| :--- | :--- |
| **`mode`** | Must be set to `"sandbox"`. Disables plot tracking and enables the manual Chapter Wizard. |
| **`setting`** | The initial environment where the story begins. |
| **`starting_situation`** | The "Cold Open" instruction that tells the AI exactly how the first scene starts. |
| **`goal`** | A high-level motivation for the character (The AI will entice the player toward this). |
| **`allow_cheats`** | Usually set to `true` for Sandbox play to allow narrative correction and rerolls. |

---

#### 🧪 Adding Custom Depth (Extensibility)

TomeWeaver allows you to inject complex lore and logic directly into the configuration. Because the entire JSON is passed to the LLM in every prompt, the AI will respect the relationships, traits, and specific instructions you define. Here are two examples using the fields `family` and `instructions` but you can add any valid structured data to the configuration.

**Example 1: Social Connections & Family Bloodlines**

By adding a `family` or `connections` object, the AI will know exactly who characters are if they are mentioned, and can even introduce them naturally into the story.

```json
"family": {
  "mother": "Liana, a retired herbalist with a secret past.",
  "father": "Bram, missing for ten years.",
  "brothers": [
    "Kael, 31yo. Twin brother, soldier in the royal guard.",
    "Jace, 27yo. Younger brother, a wandering bard."
  ],
  "pet": "Mallow, his friendly but protective 7 years old cat.",
  "friend": "Antoine, 30yo. Best friend. Knows the city's sewers perfectly."
}
```

**Example 2: Narrative Instructions**

You can provide an `instructions` array to force the AI to follow specific literary styles, perspectives, or pacing rules.

```json
"instructions": [
    "Always maintain a first-person perspective from the main character's POV.",
    "Incorporate vivid descriptions of physical sensations (smells, temperature, heart rate).",
    "Include dialogue that highlights the character's internal curiosity.",
    "Progress the story by offering increasingly difficult and critical choices.",
    "Focus on the thrill of discovery and the atmosphere of the environment."
]
```