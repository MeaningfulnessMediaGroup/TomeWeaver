# TomeWeaver: Gameplay & User Guide

TomeWeaver is an interactive fiction engine, but it is also a powerful writing tool. This guide explains how to play the game, how to use the Timeline Editor to sculpt your adventure, and how to harness the AI to co-write your story.

---

## 🏗️ Starting an Adventure (The Story Forge)

You do not need to manually create folders or write raw JSON files to play TomeWeaver. From the **Library Dashboard**, click the **+ Create New Story** dropdown to access the Story Forge.

1.  **Guided Wizard:** The easiest way to start. The Wizard will walk you step-by-step through defining your protagonist, setting, rules, and goals, before dropping you into the Story World to review your choices.
2.  **Generate via AI:** Simply type a single concept (e.g., *"A gritty detective noir set on a space station"*) and let the AI instantly generate the entire world configuration, chapter outline, and starting lore.
3.  **Manual Setup:** Opens a clean, single-page form to quickly define the basics yourself.
4.  **Create Universe:** Creates a master container. Any stories you create *inside* this folder will share the same Global Lore and World Bible.

### The Two Game Modes
When creating a story, you must choose a Mode. This fundamentally changes how the engine behaves:
*   **Sandbox Mode:** Open-ended and player-driven. The world is persistent, but there is no strict plot. You use the Director Dropdown during gameplay to manually trigger time-jumps and scene shifts.
*   **Campaign Mode:** Plot-driven and structured. The AI strictly follows the Chapter Outline you define in the Story World. The engine will not allow you to progress until the conditions of the active chapter goal are met in the story.

---

## 🎮 Playing the Game (The Input Bar)

At the bottom of the **Story Mode** timeline, you will find the Input Bar.

1. **Choosing an Action:** Every turn, the AI generates 3-6 green action buttons. Click one to immediately submit it.
2. **Custom Actions:** If you don't like the AI's choices, type your own action or dialogue into the text box and hit `Enter` (or click Submit).
    *   *Example:* `I ignore the goblin entirely and inspect the runes on the wall.`
    *   *Example:* `"I'll pay your toll," I say, tossing him two silvers.`

### 🎬 Director Overrides (Sandbox Mode Only)
In Sandbox mode, a dropdown appears next to the text input box. Use this to force the AI to change the state of the simulation:
*   **Standard Action:** The default. Your text is treated as what the protagonist does or says.
*   **Force Setting:** Type a new location and submit. The AI will instantly transition the scene.
*   **Force Time:** Type a time-jump (e.g., "Three days later").
*   **Force POV:** Shift the perspective to a different character.
*   **Force Chapter:** Instantly triggers a Cold Open, starting a brand new chapter with the text you provide as the setting.
*   **Expand Notes:** Co-write with the AI! Select this, type a brief summary like "I defeat the guards in an epic sword fight," and the AI will expand it into 3-5 paragraphs of cinematic prose.

---

## 🛠️ Card Tools (Non-Destructive Editing)

TomeWeaver treats interactive fiction like a drafting process. Attached to the bottom of the active Turn Card are several powerful editing tools.

| Tool | Description |
| :--- | :--- |
| **⟳ Redo Turn** | *Destructive.* Discards the AI's entire current turn and forces it to generate a brand new response to your last action. |
| **⟳ Choices** | *Safe.* Keeps the story prose exactly as it is, but forces the AI to generate a brand new list of green action choices. |
| **✨ Expand** | *Safe.* Generates a Draft that adds rich sensory details and cinematic length to the current scene without advancing the plot. |
| **✨ Condense** | *Safe.* Generates a Draft that acts as an editor, making the current prose shorter and punchier while preserving key plot points. |
| **✨ Polish** | *Safe.* Generates a Draft that acts as a professional copy-editor. Fixes grammar and sentence flow while strictly preserving the plot and dialogue. |
| **🔧 Fix...** | *Safe.* Opens a prompt asking for an instruction. (e.g., "Make it raining" or "Change the rusty dagger to a glowing blue sword.") Generates a Draft applying your fix. |

*Note: "Safe" tools do not overwrite your game immediately. They open the **Visual Diff** window, highlighting exactly what words the AI changed in red and green, allowing you to accept or discard the revision.*

---

## ✂️ Narrative Surgery (The Timeline Editor)

Sometimes the story needs pacing adjustments that an AI cannot handle natively. The **Timeline Editor** (the top row of buttons on historical cards) gives you god-like control over the master clock.

### Time & Pacing
*   **+ Insert Turn:** Right-shifts all future turns and inserts a new card at your cursor. Choose one of three modes in the dialog:
    *   **Blank Turn** — Empty placeholder; use `✎ Edit Scene` to write prose manually.
    *   **Generate — continue story** *(Sandbox)* — The AI writes the next scene from the current prose. It does **not** auto-select a pending choice; Director meta-actions like `[ Continue the story ]` are hidden on cards.
    *   **Generate — bridge the gap** *(between two existing cards only)* — The AI writes an intervening scene that steers toward the upcoming turn without copying its prose.
*   **X Delete Turn:** Permanently deletes the active card and left-shifts all future turns to collapse the gap.
*   **↔ Turn to Bridge:** Rips the prose out of the current card, pushes it *forward* into the next turn's Narrative Bridge, and deletes the current card. (Great for collapsing slow scenes).
*   **↔ Bridge to Turn:** Rips the transition text out of the current card and explodes it into its own dedicated, standalone Turn card.

### Chapter Boundaries
*   **✂ Split Chapter:** Instantly slices the active chapter in half. The current card becomes Turn 1 of a brand new chapter.
*   **← Merge Chapter:** (Only visible on the first turn of a chapter). Dissolves the chapter boundary, merging this chapter backward into the previous one.

### 🍴 Slice Chapters (New Story Folder)
If you are playing a massive ensemble story and want to **spin off chapters into a separate cartridge**, use **Options → Slice Chapters...** in the workspace header. Check the boxes next to the chapters you want. The engine extracts them, re-indexes Master Clocks and RAG memories, and creates a **new story folder** on your Dashboard.

> **Note:** This is different from **Fork Here** / **Run Tree**, which keep alternate timelines inside the *same* story cartridge.

---

## 🌳 Run Tree (Alternate Timelines)

The Run Tree stores multiple playable timelines in one cartridge under `runs/manifest.json`. Each node has a snapshot folder with its own `history.json`, `chapters.json`, and `memory.json`.

### Creating branches
| Action | Result |
| :--- | :--- |
| **⑂ Fork Here** (Timeline Editor) | Archives the full timeline as a **parent** node, truncates after turn N when future turns exist, creates a **branch** snapshot, and clears your choice on N so you can pick again. Works on the **current card** before you choose. |
| **Restart → Save** | Archives the current root line, then wipes history for a fresh start (no fork point). |
| **Restore & Fork…** (Run Tree) | Loads an archived timeline, then forks @ a turn you specify. |

Forks can nest: fork again on any branch to grow a tree. Sibling timelines do not overwrite each other when you switch.

### Switching timelines
Open **Options → Run Tree…**:
1. The **● playing now** row is your active timeline (pre-selected).
2. Each row shows **`Chapter N - Turn T - YYYY-MM-DD HH:MM`** (story-first). Hover for the saved label, fork @ turn, turn count, chapter title, and run kind.
3. Click **Show preview ▸** (top right) for an optional side panel with prose and choices at that timeline's fork turn.
4. Select another row and click **Switch**.
5. The engine **saves progress in place** to the leaving timeline's snapshot, then loads the target into the cartridge root.

Switching does **not** create new tree nodes. Only Fork, Restart-save, and Restore & Fork add nodes.

### Restore & Fork
Select an archived timeline (not the active row), click **Restore & Fork…**, enter a valid fork turn (committed choice with turns after it, or the archive's last playable turn). Your current timeline is saved first; the archive loads; then the engine forks @ that turn.

### Sharing & comparing runs
**Export branch pack:** Story card **Options → Export to .zip → Branch pack**, or **Run Tree → Export…**. Select timelines (ancestors are included automatically). Optional **Shared by** name is embedded in the pack.

**Import branch pack:** Dashboard **Import .zip** (auto-detects format) or **Run Tree → Import…**. Pick your local copy of the story, choose which timelines to merge, set a label prefix (e.g. `[Alice] `). Imported rows appear in Run Tree—**Switch** to compare without losing your own branches.

Branch packs carry a **setup fingerprint**. Importers warn if your `setup.json` differs (different title, mode, or campaign outline)—you can still force import, but fork alignment may not match.

---

## 🤖 Auto-Play (Test Mode)

If you are playing a **Campaign**, you will see a `▶︎ Auto-Play` button in the top right header.
*   When clicked, the engine takes control. Every 2 seconds, it will automatically click the first available action choice (The "Golden Path").
*   **Purpose:** This is a developer tool. It allows you to rapidly stress-test your Chapter Goals and plot outlines to ensure the AI understands how to complete the game.
*   Click the button again (it will turn red and read `🛑 Stop Auto-Play`) to halt the autopilot and resume manual control.

---

## 💾 Saving, Exporting, and Seeds

### Auto-Saving
You do not need to manually save your game. TomeWeaver automatically writes your progress to `history.json` the exact moment a turn is generated or an edit is applied. You can safely close the app at any time.

### Exporting the Storybook
Click the **Options...** dropdown in the top right header and select **Export Story**. This will compile your chronological game log into a cleanly formatted, readable Novel.
*   You can choose between `TXT`, `Markdown`, or `HTML` formats.
*   If you enable "Seamless Novelization", the exporter will use the AI-generated Narrative Bridges to weave your actions seamlessly into the prose, hiding the "gameplay" mechanics entirely.

### Setting a "Story Seed"
If you want your adventure to start with a specific, hand-crafted first turn (instead of letting the AI generate one randomly), you can save a Story Seed.
1. Start a new game and let the AI generate Turn 1.
2. Click **✎ Edit** on the Turn 1 card.
3. Manually rewrite the prose, location, and choices to be exactly what you want the player's "Hook" to be.
4. Click the blue **💾 Set as Story Seed** button at the bottom of the editor.
5. Any time you (or anyone you share the cartridge with) restarts this adventure, it will perfectly load your hand-crafted hook!

---

## 📥 Bulk Import Turns (Writer Pipeline)

Use **Options → Import Turns...** in the Workspace header to paste large blocks of pre-written prose.

### Syntax
*   Lines starting with **`>`** or **`=`** begin a new **player action** and finalize the preceding prose block as a turn.
*   All other lines accumulate as **story text** for the current turn.
*   If you paste without a leading action marker, the engine assigns **`[ Imported Text ]`** as the bridge action on the anchor turn.

### Example
```
The rain hammered the cobblestones.

> I duck into the alley

Shadows swallow me whole. A flickering neon sign buzzes overhead.

> I knock on the rusted service door
```

The engine splices parsed turns after your current timeline position, right-shifts the Master Clock, adjusts chapter boundaries, and invalidates affected Plot Ledger entries (recompile afterward).

### Integration Evaluation (pre-import check)
Before importing, click **Integration Evaluation** in the import dialog. The engine scores the pasted text (0–100) against this story's local RAG and, when applicable, the shared universe lore—paying special attention to protagonist names and continuity. Review the fit/misfit reasons, then choose **Import & Splice Timeline** or **Cancel**.

---

## 📋 Generate Recap

**Options → Generate Recap** asks the AI to summarize the entire adventure chronology into a readable briefing. Useful when returning to a long save, preparing a session handoff, or reviewing before export.

---

## 🌉 Generate Missing Bridges

If **Auto Narrative Bridge** is disabled—or you performed timeline surgery—transitions may be missing. **Options → Generate Missing Bridges** runs the novelizer across history in a background thread, writing `narrative_bridge` metadata without altering main story prose.

---

## 🧠 Memory & Lore Tools (Entity Editor)

Open the **Memory & Lore** tab for advanced continuity management. Use the **top tab bar** to switch between Chapters, Plot, and entity ledgers (Characters, Locations, Artifacts, Factions). Entity tabs show a filterable list (when count > 15) and remember your last selected entry per tab.

| Tool | Description |
| :--- | :--- |
| **🔄 Compile Missing History** | Runs the RAG compiler (Standard, Base Lore, Deep Scan, or Integrity Check modes). |
| **🔗 Merge...** | Combines two entities; traits merge without data loss; aliases route future mentions. |
| **Deep Rename** | Phase 1 scans RAM + authorized files; Phase 2 executes rename only where you approve. |
| **Deep Scan** | Re-reads history in chunks to extract new traits/events for a single entity. |
| **✔️ Validate / 🔧 Auto-Patch** | QA a Plot Ledger chunk against raw turns (see [RAG.md](RAG.md)). |
| **State: Active / Archived / Pinned** | Manual override of auto-decay behavior per entity. |

---

## ✎ Manual Scene Editing

Click **✎ Edit Scene** on any turn card (current or historical) to open the full editor:
*   Rewrite `story_text`, `location`, `pov_character`, and `choices` directly.
*   Edit inventory strings when tracking is enabled.
*   Click **💾 Set as Story Seed** to save Turn 1 as `start_turn.json` for future restarts.

**Inline prose editing (optional):** Enable **Enable Inline Prose Editing** in Dashboard → `⚙ Settings` to edit story text directly on the timeline card. Changes auto-save (debounced) before you submit an action, navigate away, or close the workspace.

Manual edits do not automatically recompile RAG memory—run **Compile Missing History** if lore should reflect your changes.

### Offline prose linting (Spell Phase 1 + Grammar Phase 2 + Settings Phase 3)

Open **Dashboard → ⚙ Settings → Prose Lint Settings…** for all lint options (moved out of the main settings scroll):

| Setting | Purpose |
| :--- | :--- |
| **Enable Inline Prose Editing** | Direct edit on timeline cards |
| **Offline Spell Check** | Red typos (`pyspellchecker`) |
| **Offline Grammar Check** | Amber rule-based lint |
| **Offline Synonyms** | Right-click WordNet synonyms (no underlines) |
| **AI Spelling Suggestions** | LLM replacements on spell/grammar menus |
| **Spelling locale** | American, British, or **Both Allowed** (accept either variant) |
| **Save added words to** | Story / Universe / Global — applies to **Add to dictionary** and **Ignore** |

Two underline colors in the editor:

| Toggle | Underline | What it catches |
| :--- | :--- | :--- |
| **Offline Spell Check** | Red | Unknown words vs bundled dictionary + story lexicon; contractions & plurals handled automatically |
| **Offline Grammar Check** | Amber | Rule-based prose hygiene (see below) |

#### Spell check (Phase 1)
Uses **`pyspellchecker`** — fully offline. Right-click a red underline to pick a replacement, **Add to dictionary**, **Ignore** (same save scope as Add), **Synonyms** submenu (when enabled), or **Get AI suggestions…** (active LLM profile; local if using LM Studio).

**Dictionary scope:**
*   **Auto-allowlist:** Names and terms from this story's `setup.json`, universe `master_setup.json` (when tethered), Memory & Lore entity ledgers and aliases, and turn `location` / `pov_character` metadata (rebuilt in memory when you play).
*   **Your additions:** **Add to dictionary** writes per **Prose Lint Settings → Save added words to** (story / universe / global). **Ignore** writes to the same scoped file (`ignored` key). All lexicon layers plus RAG names are merged when checking.
*   **Token rules:** Surrounding `"` and `'` quotes are not part of the word. Common **contractions** and basic **plural stems** are accepted when their expanded or singular form is valid.

#### Grammar check (Phase 2)
Uses **offline regex rules** in `grammar_lint.py` — no network, no Java/LanguageTool server. Right-click an amber underline for an explanation; choose **Fix: …** when a safe replacement is offered, or **Ignore this issue** (saved to `ignored_grammar` at the same lexicon save scope as Add/Ignore for spelling).

**Rules include:**
*   Repeated words (`the the`)
*   Double/multiple spaces and tab characters
*   Space before punctuation; missing space after `. , ! ? ;`
*   Lowercase letter after sentence-ending punctuation
*   Stacked `!!` / `??` / long `....` runs
*   Basic **a/an** (`a apple` → `an apple`; keeps `an hour`)
*   Common **subject–verb** mismatches (`he don't`, `they was`, `I is` — subjunctive `if he were` is allowed)
*   **`your` vs `you're`** before common `-ing`/helper verbs (`Your going` → hint)

**Still not included:** Deep grammar, tense consistency across paragraphs, dialect, or voice-preserving copy edits — use **✨ Polish** for LLM proofreading.

#### Synonyms (WordNet)
When **Offline Synonyms** is on, right-click any word (no underline required). Correctly spelled words open a synonym list; misspelled words may also show a **Synonyms** submenu on the spell menu. Fully offline after NLTK WordNet data is cached (one-time download on first use if missing).

**Applies to:**
*   **✎ Edit Scene** → Narrative Bridge, Story Prose, and Action Choice entry fields.
*   Inline timeline prose (only when **Enable Inline Prose Editing** is also on).

**Disable:** Turn off individual toggles in **Prose Lint Settings…** if underlines or menus distract during read-only playback or on very slow hardware.

---

## 📦 ZIP Cartridges & Branch Packs (Share & Backup)

TomeWeaver supports two `.zip` formats:

### Full cartridge
*   **Export:** Story card **Options → Export to .zip → Full cartridge** (or universe folder export on Dashboard).
*   **Import:** Dashboard **Import .zip** — creates a **new** story folder with collision-safe naming.
*   **Contains:** `setup.json`, `system_prompt.txt`, root save files, run tree, prompts—everything except `index.json` (rebuilt locally).

Ideal for backups, publishing sample worlds, or sending someone a complete adventure.

### Branch pack
*   **Export:** **Export to .zip → Branch pack** or **Run Tree → Export…** — selected run-tree snapshots + `branch_pack.json` metadata only.
*   **Import:** Dashboard **Import .zip** or **Run Tree → Import…** — merges timelines into an **existing** story; does not replace setup or create a new folder.
*   **Contains:** `branch_pack.json`, `branches/<id>/history|chapters|memory|meta.json`.

Ideal for sharing “what if I chose B?” with a friend who has the same story setup, then comparing paths via Run Tree **Switch**.

---

## ⚠️ Known Limitations (Gameplay)

*   **Campaign goal completion is AI-judged**, not rule-engine verified. If the model refuses to advance, use Director tools, manual chapter edits, or **Fix...** on the turn card.
*   **Timeline surgery clears Plot/Chapter ledger entries** for affected chapters. Re-run **Compile Missing History** afterward.
*   **Import Turns** does not auto-generate narrative bridges or RAG summaries for imported text.
*   **Deep Rename** on Global entities can touch multiple universe files—review the authorization dialog carefully.
*   **Auto-Play** always picks the **first** green choice; it does not explore branching paths.
*   **Undo (↶)** reverts the last committed choice; it cannot restore pre-Restart root state unless you archived via Restart → Save or switched away from a Run Tree snapshot.
*   **Run Tree imported branches** keep their own memory snapshots; switching timelines swaps local RAG context for that branch—recompile if you edit history manually after import.

See also the full **Known Limitations** list in the [root README](../README.md).