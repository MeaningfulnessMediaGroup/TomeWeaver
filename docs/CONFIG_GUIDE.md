# TomeWeaver: Configuration Guide

While TomeWeaver provides a powerful GUI to manage your adventures, the engine relies on strict underlying JSON schemas to function. This guide explains how the engine's DNA works.

*Note: You rarely need to edit these JSON files manually. The **Global Settings** and **World Builder (Codex)** UI tabs handle the serialization safely for you.*

---

## ⚙️ Global Engine Configuration (`engine_config.json`)

The `engine_config.json` file manages the global behavior of the engine, including API settings and the "Fortress" auto-healing logic.

**Access in UI:** Dashboard -> `⚙ Settings`

| Key | Description |
| :--- | :--- |
| **`active_api_profile`** | The name of the cloud/local profile currently selected (e.g., "LM_Studio", "OpenRouter"). |
| **`temperature_base`** | Base creativity level (0.0 to 2.0). The engine automatically raises this during retries to break linguistic loops. |
| **`max_retries`** | The number of times the "Fortress" logic will attempt to surgically heal broken LLM JSON output before halting. |
| **`context_window`** | The number of previous narrative turns the AI remembers. Higher values increase depth but also token cost. |
| **`auto_polish`** | If `true`, the engine silently runs a second copy-editing LLM pass on every single turn to guarantee novel-quality prose. (Costs double tokens). |
| **`auto_narrative_bridge`**| If `true`, the engine automatically patches missing transition prose in the background while you play. |

---

### 🛡️ Understanding the "Fortress" Retry System

Local LLMs (especially smaller 8B models) will occasionally break strict JSON formatting or get stuck in linguistic loops. TomeWeaver acts as a "Fortress" around the game state.

**1. The Self-Healing Loop**
If the LLM returns invalid JSON (e.g., missing a quote), the engine intercepts it. It first runs a **Surgical Regex Sanitizer** to auto-fix the text without burning an API call. If surgery fails, it triggers an API Retry.

**2. The AI Feedback Loop**
On a Retry, the engine appends the Python error to the prompt (e.g., *"Your previous JSON was invalid. Error: Expecting ',' delimiter."*). This teaches the AI exactly what it broke so it can correct itself.

**3. Temperature Escalation**
If the AI gets stuck in a repetitive loop (starting 3 turns in a row with the exact same 4 words), the engine rejects the turn. With each retry, the engine slightly raises the `temperature` to forcefully bump the AI out of its rut.

---

## 🗺️ Adventure Configuration (`setup.json`)

The `setup.json` file acts as the "DNA" of your adventure. 
**Access in UI:** Workspace -> `World Builder` tab.

### ⚠️ Extensibility
The configuration is infinitely extensible. Any custom field you add in the UI (e.g., `family_tree`, `magic_rules`, `ship_inventory`) is instantly serialized into the JSON and sent to the LLM every turn. 

### Option A: Campaign Mode
Use this for structured, plot-heavy stories with defined goals and a sequence of chapters. 

*   **`track_inventory`**: The engine forces the LLM to maintain a persistent inventory string in the background.
*   **`can_die`**: The AI is permitted to trigger a "Game Over" state if the player makes a fatal mistake.
*   **`plot_outline`**: (Managed in the **Chapter Outline** UI Tab). An array of chapter objects defining the exact `goal` and `obstacles` the player must overcome before the AI is allowed to advance the story.

### Option B: Sandbox Mode
Use this for open-ended "What if?" simulations and player-driven exploration where the world is persistent but the plot is free-form.

*   **`starting_situation`**: The "Cold Open" instruction that tells the AI exactly how the first scene starts.
*   **`allow_cheats`**: Enables the Director Overrides (Force Time, Force Setting) and the Edit/Polish/Fix buttons on the cards.

---

## 🌟 The "Story Seed" (`start_turn.json`)

TomeWeaver supports a specialized feature for adventure authors called the **Story Seed**. 

If you want your adventure to start with a specific, hand-crafted first turn (instead of letting the AI generate one), you can save a `start_turn.json` file.

**How to use it in the UI:**
1. Start a new game and let the AI generate Turn 1.
2. Click **✎ Edit** on the Turn 1 card.
3. Manually rewrite the prose, location, and choices to be exactly what you want the player's "Hook" to be.
4. Click the blue **💾 Set as Story Seed** button at the bottom of the editor.
5. Now, anytime someone plays your cartridge, they will instantly start at your hand-crafted hook!