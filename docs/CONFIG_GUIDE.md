# TomeWeaver: Configuration & Architecture Guide

While TomeWeaver provides a powerful GUI to manage your adventures, the engine relies on strict underlying JSON schemas and configuration files to function. This guide explains how the engine's DNA works.

*Note: You rarely need to edit these JSON files manually. The **Global Settings**, **Story World**, and **Universe** UI tabs handle the serialization safely for you.*

---

## ⚙️ Global Engine Configuration (`engine_config.json`)

The `engine_config.json` file manages the global behavior of the engine, including API settings, UI scaling, and the "Fortress" auto-healing logic.

**Access in UI:** Dashboard -> `⚙ Settings`

| Key | Description |
| :--- | :--- |
| **`active_api_profile`** | The name of the cloud/local profile currently selected (e.g., "LM_Studio", "OpenRouter"). |
| **`temperature_base`** | Base creativity level (0.0 to 2.0). The engine automatically raises this during retries to break linguistic loops. |
| **`context_window`** | The number of previous narrative turns the AI remembers. This also dictates how often the background RAG memory engine triggers. |
| **`memory_decay_threshold`** | The number of turns before an unmentioned entity is auto-archived out of the AI's prompt to save context tokens. |
| **`max_retries`** | The number of times the "Fortress" logic will attempt to surgically heal broken LLM JSON output before halting. |
| **`auto_polish`** | If `true`, the engine silently runs a second copy-editing LLM pass on every single turn to guarantee novel-quality prose. (Costs double tokens). |
| **`auto_narrative_bridge`**| If `true`, the engine automatically patches missing transition prose in the background while you play. |
| **`inline_prose_edit`** | If `true`, story prose on the active timeline card is directly editable (debounced auto-save). Configure in **Prose Lint Settings** (Dashboard → Global Settings). |
| **`offline_spell_check`** | Red underlines for likely typos. Configure in **Prose Lint Settings**. |
| **`offline_grammar_check`** | Amber underlines for rule-based grammar/style checks. Configure in **Prose Lint Settings**. |
| **`offline_synonyms`** | If `true`, right-click any word for offline WordNet synonyms (no underlines; lookup when the menu opens). **Prose Lint Settings**. |
| **`spelling_locale`** | `american` (default), `british`, or `both` (accept either spelling variant). **Prose Lint Settings**. |
| **`custom_dictionary_scope`** | Where **Add to dictionary** and **Ignore** / **Ignore this issue** write: `story`, `universe`, or `global`. All lexicon layers merge when checking. **Prose Lint Settings**. |
| **`spell_ai_suggestions`** | If `true` (default), spell/grammar right-click menus offer **Get AI suggestions…** via the active LLM (small prompt, ~80 token cap). **Prose Lint Settings**. |
| **`ui_scaling`** | Scales the entire application interface for 4K/high-res monitors (e.g., 1.25). Requires restart. |
| **`prose_font_size`** | Font size for story timeline prose (pixels). |
| **`ui_wrap_margin`** | Extra horizontal margin subtracted from wrap width for comfortable reading on wide monitors. |
| **`prose_font_family`** | The font face used for the story timeline and editors (e.g., "Georgia", "Arial"). |
| **`logging_enabled`** | Master switch to record all game events and API calls to `session_log.txt`. |
| **`log_verbose`** | When `true`, logs full LLM prompts to `session_log.txt` (in addition to console output when verbose UI is active). |
| **`log_raw_json_on_failure`** | When `true`, always logs raw model output on JSON parse failures—even if verbose logging is off. |
| **`max_inventory_keys`** | Maximum tracked inventory slots in the World Builder pill editor (default 8). |
| **`global_theme_name`** | Name of the active **global** UI skin preset from `configs/themes.json` (e.g., `"Default Dark"`, `"Parchment"`). Used for the dashboard and as the default workspace appearance. |

Per-story appearance overrides are **not** stored here—see `setup.json` (author bundle) and `instance_config.json` (`story_theme_preference`, `adventures_dir`).

**Access in UI:** Dashboard → `⚙ Settings` (engine keys above); **Adventures Library** is under `instance_config.json` (see below).

---

## 🎨 Visual Theme Presets (`configs/themes.json`)

Stores named UI skins (outer/mid/inner colors, border width, corner rounding). Built-in presets include **Default Dark**, **Default Light**, **Parchment**, **Horror**, **Cyberpunk**, **Forest**, **Ocean Deep**, **Sunset Ember**, **Slate Light**, **Rosewood**, and **Nord Frost**.

**Access in UI:** Dashboard → `⚙ Settings` → **Active Theme** dropdown and **…** (theme editor).

Each preset is a JSON object with keys such as `outer`, `mid`, `inner`, `border_w`, and `rounding`. The active global preset name is saved in `engine_config.json` as `global_theme_name`.

### Optional story theme (`setup.json`)

Authors can recommend a skin that travels with a shared cartridge:

| Field | Description |
| :--- | :--- |
| **`theme_preset`** | Preset name from `themes.json` (e.g., `"Horror"`), or omit for no bundled theme. |
| **`theme_embedded`** | Full color object copied at save time so importers get exact colors even if they lack a custom preset. |

**Player choice:** `instance_config.json` → `story_theme_preference` maps each story folder to `"global"` (default) or `"story"`. Toggle in **Workspace → Options → Use Story Theme** / **Use My Global Theme** when a bundle exists.

**UI:** Story World → Core Settings → **UI Theme (optional, travels with export)**.

The dashboard always uses the global theme; only the active workspace respects the per-story override.

---

## 📡 API Connections Manager (`configs/API_configs/`)

TomeWeaver is completely LLM-agnostic. Instead of hardcoding API keys into the engine, it uses a modular Profile system. 

**Access in UI:** Dashboard -> `⚙ Settings` -> `⚙ Configure` (Next to Active API Profile).

Each `.json` file in this directory represents a distinct AI provider. You can seamlessly swap between a free, local LM Studio instance and a paid cloud provider (like OpenAI or OpenRouter) with a single click.

**Profile Structure:**
*   **`api_url`**: The endpoint for your LLM (e.g., `http://localhost:1234/v1/chat/completions` or `https://openrouter.ai/api/v1/chat/completions`).
*   **`api_key`**: Your secret authentication token. (Leave blank for local providers).
*   **`model`**: The exact model identifier (e.g., `gpt-4o`, `claude-3.5-sonnet`, or `loaded-model`).
*   **`max_query_per_minute`**: The engine's built-in Rate Limiter. If set > 0, the engine will automatically pause execution to prevent `HTTP 429` errors from strict cloud providers.
*   **`max_tokens`**: The absolute limit of tokens the AI is allowed to generate per response.

---

## 🛡️ Understanding the "Fortress" Error System

Local LLMs (especially smaller 8B models) will occasionally break strict JSON formatting or get stuck in linguistic loops. TomeWeaver acts as a "Fortress" around the game state.

**1. The Self-Healing Loop**
If the LLM returns invalid JSON (e.g., missing a quote), the engine intercepts it. It first runs a **Surgical Regex Sanitizer** to auto-fix the text without burning an API call. If surgery fails, it triggers an API Retry.

**2. The AI Feedback Loop**
On a Retry, the engine appends the Python error to the prompt (e.g., *"Your previous JSON was invalid. Error: Expecting ',' delimiter."*). This teaches the AI exactly what it broke so it can correct itself.

**3. Temperature Escalation**
If the AI gets stuck in a repetitive loop (starting 3 turns in a row with the exact same 4 words), the engine rejects the turn. With each retry, the engine slightly raises the `temperature` to forcefully bump the AI out of its rut.

**4. The API Error Translator**
If the network connection drops or the Cloud Provider goes offline, TomeWeaver intercepts raw Python traceback exceptions and HTTP Error codes (502, 503, 504) and translates them into explicit, human-readable popup alerts so the user knows exactly what failed.

---

## 🌌 Shared Universes (`master_setup.json`)

If you want multiple stories to share the same World Lore, you can create a Universe container. 
**Access in UI:** Workspace -> `Universe` tab.

*   `master_setup.json`: Holds the `universe_title`, global `tone`, and global `lore_and_rules`. The Prompt Compiler will dynamically inject these global rules above the local story rules every turn.
*   `shared_memory.json`: The Global World Bible. Holds characters, locations, artifacts, and factions that span across all threads in the Universe.

**The Migration Wizard:** If you drag a standalone story into a Universe folder via the Dashboard, the engine will automatically launch an in-memory Migration Wizard. It will ask you how you want to merge the Local Rules with the Universe Rules, and safely resolve any Name Collisions before securely tethering the story to the Universe.

---

## 🗺️ Adventure Configuration (`setup.json`)

The `setup.json` file acts as the "DNA" of your local adventure Cartridge. 
**Access in UI:** Workspace -> `Story World` tab.

### Cartridge format version (engine schema)

Separate from the author **Version** field in the World Builder:

| Key | Purpose |
| :--- | :--- |
| **`cartridge_format_version`** | Integer schema revision for this cartridge (currently **`1`**). Used for deterministic upgrades when TomeWeaver changes on-disk layout. Auto-stamped on load if missing. |
| **`cartridge_format_spec`** | Documentation label for the spec family (currently **`MMG-LSM-1.0`**). |
| **`version`** | *Your* story/cartridge revision string (e.g. `"1.0"`, `"2.3-beta"`) — author metadata only. |

Legacy cartridges without `cartridge_format_version` are treated as **format 0** and upgraded to **1** on first load (no field renames today). Future engine releases register step migrations in `scripts/cartridge_format.py`.

Related version stamps: `runs/manifest.json` → `version` (run tree); `branch_pack.json` → `pack_version` (timeline sharing).

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
*   **`allow_cheats`**: Enables the Director Overrides (Force Time, Force Setting) and the Edit/Polish/Fix buttons on the timeline cards.

---

## 💡 The Help & Templates System (`configs/field_guides.txt`)

TomeWeaver includes a robust, offline Help system to assist users in building their worlds without suffering from "Blank Page Syndrome."

This system is driven entirely by the `configs/field_guides.txt` file. 

**Structure:**
The file uses a custom markup syntax to bind Help Text and Examples to specific UI elements in the World Builder.
*   `[HELP:UID]`: Defines the instructional text that appears at the top of the modal.
*   `[EXAMPLE:UID]`: A list of clickable templates.

**Mode Filtering:**
Examples must be prefixed with a Mode Tag (`SANDBOX:`, `CAMPAIGN:`, or `ALL:`). When a user clicks the **💡 Help** button in the World Builder, TomeWeaver automatically filters the list so Sandbox players don't see Campaign templates, and vice versa.

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

---

## 🖥️ Instance Configuration (`instance_config.json`)

Separate from engine behavior, `instance_config.json` stores **per-machine session and library state** (window geometry, story library path, bookmarks). It is auto-created on first launch and self-heals if corrupted. This file is gitignored and is not meant to be shared across machines.

| Key | Description |
| :--- | :--- |
| **`window_geometry`** | Last window size/position (e.g., `"1100x750"`). |
| **`window_state`** | `"normal"` or `"zoomed"`. |
| **`last_active_story`** | Relative path hint for session restore. |
| **`last_author`** | Default author field pre-fill for new stories. |
| **`story_bookmarks`** | Maps story paths to last-viewed turn indices for Time Travel restore. |
| **`story_theme_preference`** | Maps story folder path → `"global"` or `"story"` (workspace appearance override). |
| **`run_tree_preview_open`** | Whether **Run Tree → Show preview** side panel is open (remembered on this PC). |
| **`adventures_dir`** | Absolute path to **your** story library root on this PC. Empty string uses the default ``./adventures`` folder beside the app. ``index.json`` lives inside this folder. |

**Access in UI:** Dashboard → `⚙ Settings` → **Adventures Library** (Browse). Bookmarks update automatically when you scrub the timeline.

---

## 🌳 Run Tree (`runs/manifest.json`)

Parallel timelines for a single cartridge live under `runs/`:

| Path | Purpose |
| :--- | :--- |
| **`runs/manifest.json`** | Index of archived runs: labels, `parent_id` tree, `fork_at_turn`, `run_kind` (`original` / `branch` / `snapshot`), and `active_run_id` (which snapshot owns the cartridge root). |
| **`runs/snapshots/<run_id>/`** | Per-timeline trio: `history.json`, `chapters.json`, `memory.json`, plus `meta.json` label metadata. |

**UI:** Workspace **Options → Run Tree…** (switch, restore & fork, export/import branch packs).

**On disk behavior:** The cartridge **root** always holds the hot copy of the active timeline. **Switch** overwrites the leaving node's snapshot from root, then copies the target snapshot to root. **Fork Here** creates two new nodes (parent archive + branch) at fork time.

Branch packs export/import only the `runs/snapshots` data and `branch_pack.json`—not `setup.json`. See [COMMAND_GUIDE.md](COMMAND_GUIDE.md) for sharing workflows.

---

## 📇 Autonomous Library Index (`adventures/index.json`)

The Dashboard maintains a cached metadata index for fast search and pagination across large libraries. The index file lives at ``<adventures_dir>/index.json`` (inside whichever library folder is configured in Settings). The index rebuilds when stories are created, renamed, moved, or when you trigger a manual refresh. It is **never exported** inside ZIP cartridges or branch packs (regenerated on import).

---

## 📜 Optional Text Bypasses (`prologue.txt`, `epilogue.txt`)

| File | Behavior |
| :--- | :--- |
| **`prologue.txt`** | If present and history is empty, Turn 1 loads this text **as-is** without calling the LLM (unless overridden by `start_turn.json`). |
| **`epilogue.txt`** | When the player chooses **Conclude the Story**, the epilogue loads as-is instead of generating a final turn. |
| **`start_turn.json`** | Highest-priority Turn 1 seed; overrides prologue for structured JSON hooks (choices, location, inventory). |

These files are edited as plain text in the adventure folder or via **✎ Edit Scene → Set as Story Seed** for JSON seeds.

---

## 🔤 Story Spell Lexicon (`spelling_lexicon.json`)

Custom words and ignore lists from right-click **Add to dictionary**, **Ignore**, and **Ignore this issue**. Configure scope and locale in **Dashboard → ⚙ Settings → Prose Lint Settings…**

**Three lexicon layers (merged when checking):**

| Layer | Path | Notes |
| :--- | :--- | :--- |
| **Global** | `{adventures_dir}/spelling_lexicon_global.json` | Shared across your whole library on this PC. |
| **Universe** | `{universe folder}/spelling_lexicon.json` | Shared by all threads in a Shared Universe. |
| **Story** | `{cartridge}/spelling_lexicon.json` | This adventure only. |

**Save scope** (`custom_dictionary_scope` in Prose Lint Settings): **Add to dictionary**, **Ignore**, and **Ignore this issue** write to **story**, **universe** (if tethered), or **global** only — but checking always merges all applicable files.

**Schema (each file):**
```json
{
  "words": ["eldritch", "runeweaver", "whisperwind"],
  "ignored": ["intentionaltypo"],
  "ignored_grammar": ["repeat_word|the the"]
}
```

| Key | Behavior |
| :--- | :--- |
| **`words`** | Accept as correct spelling (same as **Add to dictionary**). |
| **`ignored`** | Suppress red underlines without treating the word as correctly spelled elsewhere—right-click **Ignore** at the configured save scope. Merged from all layers when checking. |
| **`ignored_grammar`** | Suppress a specific grammar hit (`rule_id\|flagged span`, lowercased). Right-click **Ignore this issue** on amber underlines. |

Legacy files may be a plain JSON array of words; those load as **`words`** only.

| Source | Behavior |
| :--- | :--- |
| **Auto-allowlist (RAM, not written to disk)** | Tokens from story `setup.json`, universe `master_setup.json` (when tethered), Memory & Lore **local + global** entity ledgers and aliases, and turn `location` / `pov_character`. Universe shared_memory entities are included automatically for universe threads. |
| **`spelling_lexicon.json` (persistent)** | Words you add via right-click (`words`), plus optional `ignored` and `ignored_grammar`. Lowercased on save. Story file is per-cartridge; universe and global layers merge when checking. |
| **Bundled dictionary** | `pyspellchecker` English word list (offline). |
| **WordNet (synonyms)** | NLTK WordNet when **`offline_synonyms`** is on; corpus cached locally after first use. |

**Smart matching (Phase 1 spell):** Leading/trailing `"` and `'` are stripped before lookup. Common contractions and plural stems pass when their expansion or singular is valid.

**Grammar lint (Phase 2):** Implemented in `scripts/grammar_lint.py` as conservative regex rules—fully offline, no LanguageTool/Java dependency. Covers repeated words, extra spaces, punctuation spacing, basic agreement, `a`/`an`, and common `your`/`you're` confusion. Not exhaustive grammar; disable via **`offline_grammar_check`** if too noisy for your voice.

**Synonyms (WordNet):** When **`offline_synonyms`** is on, right-click a correctly spelled word for a synonym list (misspelled words also get a **Synonyms** submenu when WordNet has matches). Uses NLTK WordNet; on first use the app may download the WordNet corpus once if it is not already cached (~30MB, then fully offline).

**Not in scope:** Full style editing or LLM-quality proofreading—that remains **✨ Polish** or future tooling.

**Export:** Included in **full cartridge** ZIP exports. Branch packs do not carry lexicon files (target story keeps its own).

**Access in UI:** Dashboard → `⚙ Settings` → **Prose Lint Settings…**; right-click words in **✎ Edit Scene** or inline prose fields (underlines when spell/grammar are on; synonyms when **Offline Synonyms** is on).

---

## 🗂️ Engine State Schemas (Auto-Generated)

### `history.json`
A flat array of turn objects. Each turn typically includes:
`turn`, `story_text`, `pov_character`, `location`, `choices`, `player_choice`, `narrative_bridge`, `input_type`, `is_game_over`, and optionally `inventory_and_state`, `chapter_goal_achieved`, `goal_progress`.

Turn numbers form the **Master Clock**—must stay sequential. Timeline surgery (insert, delete, split, merge, import, fork) re-indexes turns, chapter bounds, and plot-ledger turn ranges via the centralized `master_clock` module; the engine also auto-resyncs on load if hand-edited files drift.

### `chapters.json`
Array of chapter metadata: `chapter_number`, `title`, `start_turn`, `end_turn`, plus Campaign `objectives` arrays with `ACTIVE` / `LOCKED` status.

### `memory.json` (on disk)
Flat JSON written by `save_state()`. Contains `plot_ledger`, `chapter_ledger`, entity ledgers, `aliases`, and `global_states`. **In RAM**, the engine nests entity ledgers as `{ "local": {...}, "global": {...} }` for universe threads.

---

## 📝 System prompt registry (`configs/system_prompts.txt`)

All framework LLM prompts (world generator, RAG memory, bridge tools, editor fragments, spell-check suggestions, etc.) live in this single file. The engine parses it at startup into `PROMPTS` and `PROMPT_KINDS`.

**Header format:** `[PROMPT:KEY:JSON]` or `[PROMPT:KEY:TEXT]`

| Suffix | Meaning |
| :--- | :--- |
| **JSON** | The call site expects structured JSON in the reply. Cloud APIs (OpenAI, OpenRouter, Groq, etc.) may also get `response_format: json_object`. **LM Studio / localhost never receive that field** — they only allow `json_schema` or `text`; the engine still parses JSON via prompts + the Fortress sanitizer. |
| **TEXT** | Plain prose or a single string; JSON mode is not enabled. |

**Rules:** Do not rename keys. You may edit prompt wording. Block comments (`'''` … `'''`) inside a section are stripped and are for author notes only. Placeholders like `{story_text}` must stay unchanged.

**Per-story prompts:** Turn generation still uses each cartridge’s `system_prompt.txt`; `FRAG_*` entries from this file are appended to that system message for mode-specific behavior.

**Customization:** On first run, the bundled file is copied to your user `configs/` folder. Merge new keys from app updates manually if you heavily customized your copy.

---

## ⚠️ Known Limitations (Configuration)

*   **Editing JSON by hand** can trigger integrity warnings on next load; the engine quarantines corrupted entity entries but may reset malformed ledgers.
*   **`engine_config.json` API fields** (`api_url`, `model`, etc.) mirror the active profile but are overwritten when you switch profiles in the UI—prefer editing `configs/API_configs/*.json`.
*   **Universe global lore changes** propagate to all threads immediately; there is no per-thread "undo" for `shared_memory.json`.
*   **Custom `setup.json` fields** are sent to the LLM every turn until stripped by mode logic—extremely large custom dictionaries will consume context tokens.
*   **Lexicon layers merge when checking** (story + universe + global + RAG allowlist), but **writes** go only to the scope selected in Prose Lint Settings. Copy lexicon files manually if you want the same custom words across unrelated cartridges.
*   **WordNet synonyms** require NLTK; the WordNet corpus may download once on first use (~30MB) if not already cached.
*   **PyInstaller executables** hydrate `configs/` to the user directory on first run; bundled defaults are not auto-updated until you manually merge new template keys.

See the full **Known Limitations** list in the [root README](../README.md).