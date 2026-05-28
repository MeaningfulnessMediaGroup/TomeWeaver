# TomeWeaver - Non-linear Narrative Orchestration Platform

![License](https://img.shields.io/badge/license-Polyform--NonCommercial-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen)
![LLM](https://img.shields.io/badge/LLM-Agnostic-orange)

[ ![Download Latest Release](https://img.shields.io/github/v/release/dobrado76/TomeWeaver?label=Download%20Latest%20Executables&style=for-the-badge) ](https://github.com/dobrado76/TomeWeaver/releases/latest)


### AI stories that remember.

TomeWeaver is a world-binding infrastructure for AI narrative. A continuity-first narrative engine for long-form AI storytelling.

Not your typical disposable chatbot session.  
Not a prompt toy.  
Not a chaos simulator.

TomeWeaver was built to sustain coherent campaigns, persistent worlds, evolving characters, and exportable storybooks across hundreds or thousands of turns.

**Play the game. Export the novel.**

---

## 📄 Systems Specification (Article)

TomeWeaver’s design is described in **The Narrative State Machine (NSM) Architecture** — a reference framework for stateful AI narrative orchestration (Protocol `MMG-NSM-1.0`).

*   **[Read the PDF](docs/article/MMG-NSM-1.0%20-%20The%20Narrative%20State%20Machine.pdf)** — formatted systems specification
*   **[LaTeX source](docs/article/main.tex)** — for citations, forks, and academic reuse

**Contributions welcome:** If you spot typos, unclear wording, or minor LaTeX formatting issues while reading, pull requests that fix the article are appreciated—no need to open an issue first for small edits.

---

# 📖 Overview

Most AI storytelling tools eventually collapse under narrative entropy.

They forget characters.  
Lose inventory.  
Contradict earlier events.  
Skip transitions.  
Drift off-tone.  
Break under long campaigns.  

These are not merely prompting problems.  
They are **state-management problems**.

**TomeWeaver** approaches AI storytelling differently.

Instead of treating a story as a disposable chat log, TomeWeaver treats it as a structured, evolving narrative system with persistent memory, campaign-aware progression, continuity auditing, non-destructive editing, and long-term archival compression.

The engine combines:
- Stateful campaign orchestration
- Shared Universes (Multi-threaded Multiverses)
- Structured world lore and schema management
- Long-term Dual-Tiered RAG memory ledgers
- Narrative bridge generation
- Non-destructive AI-assisted editing
- Timeline branching, surgery, and time-travel
- Exportable storybook compilation
- Resilient JSON repair and recovery systems

The result is an AI storytelling experience designed not merely for novelty, but for **long-form narrative continuity**.

Whether you want:
- a persistent solo RPG,
- a living world simulator,
- an AI game master,
- a branching interactive novel,
- or a story-to-book creative pipeline,

TomeWeaver provides the infrastructure to make long-form AI storytelling coherent, editable, replayable, and durable.

---

# ⚔️ How TomeWeaver Compares

Most AI storytelling tools optimize for fast generation.

TomeWeaver optimizes for **long-term narrative continuity**.

| Platform | Primary Focus | Strengths | Common Limitations | TomeWeaver Difference |
|---|---|---|---|---|
| **AI Dungeon** | Open-ended AI roleplay | Fast improvisation, accessible gameplay | Narrative drift, weak long-term continuity, limited editing control | TomeWeaver is designed around persistent state, continuity repair, campaign structure, and exportable storybooks |
| **NovelAI** | AI-assisted prose generation | Strong prose quality, author-oriented tooling | Primarily session-centric writing workflows, limited systemic campaign orchestration | TomeWeaver behaves more like a narrative operating system than a writing assistant |
| **SillyTavern** | Character chat orchestration | Highly customizable model front-end, character roleplay | Primarily chat-oriented, continuity heavily dependent on manual prompt engineering | TomeWeaver externalizes memory and narrative state into structured ledgers and progression systems |
| **KoboldCPP / Tavern Ecosystem** | Local LLM storytelling infrastructure | Local/private inference flexibility | Tooling fragmentation, inconsistent long-form continuity, technical setup burden | TomeWeaver provides a cohesive continuity-first narrative engine on top of local models |
| **Traditional Interactive Fiction Tools** *(Twine, Ink, ChoiceScript)* | Deterministic branching narratives | Authorial control, handcrafted pacing | Static authored content, no emergent AI generation | TomeWeaver combines structured progression with dynamic AI-driven narrative evolution |

## 🧠 The Core Difference

Most systems treat storytelling as:
> "Generate the next paragraph."

TomeWeaver treats storytelling as:
> "Maintain a coherent evolving narrative state over time."

That architectural difference changes everything.

Instead of relying purely on prompt context windows, TomeWeaver introduces systems for:
- Persistent campaign memory
- Entity tracking and archival
- Structured world lore (Global and Local)
- Narrative bridging
- Non-destructive revision workflows
- Continuity auditing
- Timeline surgery (Insertion, Deletion, Slicing)
- Run Tree branching, snapshot switch, and branch-pack sharing
- Long-term compression via RAG ledgers

The result is an experience designed not just for momentary generation, but for **sustained narrative integrity across long-form adventures**.

---

## Full Runtime Transparency

TomeWeaver has verbose logging settings (`log_verbose`, `log_raw_json_on_failure` in Global Settings) that, when enabled, expose:
- the full composite prompt (in `session_log.txt` and the Developer Console),
- injected memory state,
- active runtime fragments,
- continuity directives,
- and raw LLM output on failures.

No black boxes.
No hidden orchestration.
No opaque prompt engineering.

Inspect, debug, modify, and optimize the narrative runtime yourself.

---

## 🚀 The Vision

A Stateful Narrative Orchestration Engine for LLMs. TomeWeaver bridges the gap between generative AI and structured game design, transforming player adventures into seamless, exportable storybooks.

Most AI storytelling tools are "chaos simulators"—they struggle with context drift, lose track of goals, and produce "jumpy" prose. **TomeWeaver** is a narrative pipeline that treats a story as a structured database. 

It provides the "bones" of a game engine (inventory, chapters, goals, UI virtualization) and the "soul" of a novel, resulting in a journey that is fun to play and beautiful to read back later.

## ✨ Key Features

### 1. The "Non-Linear Video Editor" Timeline & Surgery
Say goodbye to scrolling endless walls of text. TomeWeaver renders your story as a virtualized timeline of **Cards**. You can scrub back through history using the Time Travel slider, or use the **Timeline Editor** to exercise god-like pacing control. **+ Insert Turn** offers three modes: a blank card to write yourself, **Generate — continue story** (AI extends the scene without picking a pending choice), or **Generate — bridge the gap** (AI stitches two existing cards). You can also permanently delete bad turns, or convert a player action into a narrative bridge with a single click.

### 2. Shared Universes (The Multiverse)
Create a "Universe" container to run multiple parallel stories (Sandbox or Campaign) that all share the same Global Lore and World Bible. Play as a Thief in one thread and a Detective in another—when the Thief burns down a tavern, the Detective will find the ashes.

### 3. Non-Destructive Editing (Visual Diffs)
When you ask the AI to "Polish" or "Expand" a scene, TomeWeaver does not blindly overwrite your history. It generates a **Draft** and opens a Git-style Visual Diff window, highlighting exactly what words the AI changed in Red and Green before you click "Accept."

### 4. The Visual "Codex" (Zero JSON Syntax Errors)
You never have to look at raw JSON brackets again. The built-in **Story World** and **Universe** tabs dynamically generate UI forms for strings, bulleted lists, and dictionaries, allowing authors to build massive, deeply nested world lore safely.

### 5. The "Story Forge" (AI Generation & Guided Wizard)
Banish the blank page. You can initialize a brand new world manually, use the **Guided Wizard** for a step-by-step onboarding experience, or type a single concept into the **AI World Generator** to instantly overhaul the entire cartridge with rich, AI-generated lore, settings, and goals.

### 6. Granular AI Co-Writing (Inspire & Reroll)
AI assistance isn't just for the main story. Every lore field, chapter goal, and inventory schema features dedicated **🪄 Inspire** and **⟳ Reroll** buttons. Type a quick shorthand idea, click Inspire, and watch the AI expand it into rich, cinematic detail. Stuck? Click the **💡 Help** button to browse dozens of ready-to-use templates.

### 7. Dual-Mode Storytelling
*   **Sandbox Mode:** Open-ended world simulation. Use the Director tools to manually trigger scene shifts, POV changes, or time-jumps.
*   **Campaign Mode:** Plot-driven adventures. The AI strictly follows a `plot_outline`, tracking goals and obstacles, and automatically triggers chapter transitions when you succeed.

### 8. Thread Forking (Slice Chapters)
Playing a massive 300-turn ensemble epic? Use **Options → Slice Chapters...** to check boxes next to chapters you want to extract. The engine re-indexes the master clock and spins them off into a **new standalone story folder** in your Dashboard—a derivative cartridge, not an in-place branch.

### 9. Run Tree (Multiverse Timelines)
Explore “what if I chose differently?” **inside the same story cartridge** without losing your main line.
*   **⑂ Fork Here** (Timeline Editor): Archives the full timeline, opens a new branch at turn N, and registers **parent + branch** snapshots in `runs/manifest.json`.
*   **Run Tree…** (Workspace Options): Switch between timelines—progress saves **in place** to each branch’s snapshot (no new tree nodes on switch).
*   **Restore & Fork…**: Load an archived timeline and fork again from a chosen turn.
*   **Restart → Save**: Archives the current run before wiping the root for a fresh playthrough.

### 10. Non-Destructive Narrative Bridging
TomeWeaver solves the "narrative gap" common in AI games. 
*   **The Problem:** You click "Go inside" and the next paragraph starts inside, leaving a jarring jump-cut.
*   **The Solution:** TomeWeaver auto-generates a **Narrative Bridge**—a surgical patch that weaves your action into the prose. These bridges are stored as metadata, meaning your original human-curated prose is never modified.

### 11. The "Fortress" JSON Sanitizer & Error Handler
Local LLMs often struggle with strict JSON formatting. TomeWeaver’s multi-stage sanitizer is built for extreme resilience:
*   **State-Machine Repair:** Differentiates between structural JSON markers and rogue dialogue quotes.
*   **Surgical Repair:** Uses Python's error-coordinate metadata to "patch" missing quotes or trailing commas before giving up.
*   **Truncation Recovery:** If the AI hits its token limit mid-sentence, the engine auto-balances the JSON so you can continue playing without a crash.
*   **API Translator:** Gracefully intercepts network timeouts, 429 rate limits, and 502 bad gateways, providing human-readable UI alerts instead of crashing.

### 12. Modern Native UX
TomeWeaver feels like a professional OS application. It features global OS-standard keyboard shortcuts (`Ctrl+Z` to undo, `Ctrl+Backspace` to delete words), fully dynamic flat-UI text wrapping without clunky scrollbars, and object-pooled rendering for buttery-smooth performance.

### 13. Atmospheric Theme Engine
Customize the app's look from **Dashboard → ⚙ Settings**. Pick a built-in preset (**Default Dark**, **Default Light**, **Parchment**, **Horror**, **Cyberpunk**, **Forest**, **Ocean Deep**, and others) or create your own in the theme editor. The global choice applies to the library dashboard and is the **default** while playing.

Authors can optionally bundle a **story theme** in **Story World → UI Theme** (`setup.json`). Exported cartridges include embedded colors so receivers get the intended look even without custom presets. Players keep their global theme unless they choose **Workspace Options → Use Story Theme**.

### 14. Storybook Compiler (Export)
Export your adventure as a polished **TXT, Markdown, or HTML** file. The engine compiles your chronological game log into a cleanly formatted, readable document.

### 15. Autonomous Long-Term Memory (RAG Engine)
Play infinitely without breaking your model's context limit. TomeWeaver features a background Retrieval-Augmented Generation (RAG) engine that silently compiles your history into dense, token-efficient ledgers.
*   **Dual-Tiered Memory:** Entities are scoped to "Local" (This story only) or "Global" (The Shared Universe).
*   **Tiered Summarization:** Automatically compresses turn chunks (default: every 10 turns via `context_window`) into Plot **Parts**, and finished chapters into high-level **Chapter** summaries. At generation time, the engine injects completed chapter summaries plus **only the active chapter’s** plot parts that **bridge the gap** between summaries and the full-turn history window—not stale ledgers from old chapters.
*   **The Auto-Decay Engine:** Characters, Locations, Artifacts, and Factions are tracked dynamically. If an entity hasn't been mentioned in 40 turns, they are quietly "Archived" out of the AI's prompt to save memory, and instantly "Revived" the moment they reappear in the story.
*   **Continuity Auditor:** Includes a built-in QA tool that cross-references the Plot Ledger against the Lore Bible to flag contradictions, complete with 1-click Auto-Patching. 

🧠 **[Read the deep dive into the RAG Engine (docs/RAG.md)](docs/RAG.md)**

### 16. The Memory & Lore Editor (Visual RAG Console)
The **Memory & Lore** tab is a full narrative database UI—not a raw JSON editor. A **top tab bar** separates Chapters, Plot, and entity ledgers (Characters, Locations, Artifacts, Factions), each with live count badges. Summary tabs use the full width; entity tabs show a filterable list plus Lore Bible editor. Pin important characters so they never decay, merge duplicate entities (e.g. "Vance" and "Captain Vance") with zero data-loss trait combining, and run **Deep Scan** or **Deep Rename** operations that crawl history and even offline universe files when authorized.

### 17. Bulk Turn Import (Writer's Pipeline)
Authors can paste large blocks of pre-written prose directly into a running adventure via **Options → Import Turns...** The engine parses `>` or `=` action markers into structured turns, splices them into the Master Clock, and re-indexes chapter boundaries automatically—ideal for importing a novella draft or co-written scenes. Use **Integration Evaluation** in the import dialog to score narrative fit against local and universe memory before splicing.

### 18. Adventure Recap & Bridge Catch-Up
*   **Generate Recap:** Summarizes the entire story so far into a readable briefing (useful after a long break or before sharing a save).
*   **Generate Missing Bridges:** Manually triggers the narrative bridge novelizer across history—handy when `auto_narrative_bridge` is off or after timeline surgery.

### 19. ZIP Cartridges & Branch Packs (Share & Compare)
Share adventures and individual timelines as portable `.zip` files.
*   **Full cartridge** — entire story folder (setup, prompts, run tree, saves). Export from **Options → Export to .zip** on any story card; import from Dashboard **Import .zip** as a new story folder.
*   **Branch pack** — selected run-tree timelines only (`branch_pack.json` + snapshot folders). Import into an **existing** copy of the same story setup to compare a friend’s path with yours. Export/import from the export dialog or **Run Tree → Export… / Import…**.

Branch packs include a **setup fingerprint** (title, mode, plot outline) so the importer can warn when setups differ.

### 20. Scalable Library Index
The Dashboard maintains an autonomous `index.json` cache so you can search, sort, and paginate through **thousands** of nested folders and universe threads without the UI freezing. Custom folder icons (PNG/JPG) are supported for visual organization at a glance.

### 21. Prologue, Epilogue & Story Seeds
*   **`prologue.txt` / `epilogue.txt`:** Hand-written bookends loaded as-is on first launch or campaign conclusion—no AI roll required.
*   **`start_turn.json`:** A saved "Story Seed" guarantees every restart begins at your curated Turn 1 hook (set via **💾 Set as Story Seed** in the scene editor).

### 22. Headless Engine & Automated Tests (Developers)
The core engine (`BaseEngine`, timeline surgery, JSON sanitizer, RAG decay, theme resolution) runs fully **headless**—no GUI required. A pytest suite under `/tests` (230+ tests) validates critical mechanics against disposable temp adventures. Run via `Run_Tests.bat` or `venv\Scripts\python.exe -m pytest tests/ -v` after `setup.bat`.

### 23. Offline Prose Linting (Spell, Grammar, Synonyms)
Catch typos and common grammar slips while you edit—no cloud API required for core linting.

**Phase 1 — Spell check** (red underlines): bundled `pyspellchecker` dictionary, story/universe RAG allowlist, contractions, plurals, and layered custom lexicons (`spelling_lexicon.json` at story, universe, and global levels).

**Phase 2 — Grammar check** (amber underlines): offline rule-based lint for double spaces, repeated words, `a`/`an`, subject–verb agreement, `your`/`you're` hints, punctuation spacing, and similar prose hygiene. Right-click for an explanation, **Fix**, or **Ignore this issue**.

**Phase 3 — Author settings:** **Dashboard → ⚙ Settings → Prose Lint Settings…** — spell/grammar/synonym toggles, **American / British / Both Allowed** locale, **Save added words to** (story / universe / global), optional **Get AI suggestions…** on right-click menus, and **Ignore** lists (same save scope as Add to dictionary).

**Synonyms (optional):** When **Offline Synonyms** is on, right-click any word for WordNet alternatives (no underlines; NLTK WordNet, one-time corpus download then offline).

*   **Where it runs:** **✎ Edit Scene** (bridge, prose, choices) and inline timeline prose when **Enable Inline Prose Editing** is on.
*   **Toggles:** All in **Prose Lint Settings…** (spell and grammar on by default; synonyms off by default).
*   **Not a full copy editor:** Deep rewrites remain **✨ Polish** (LLM). Grammar lint is conservative—rule-based and fully offline.

See [docs/COMMAND_GUIDE.md](docs/COMMAND_GUIDE.md) and [docs/CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md).

---

## 🧠 Supported LLM Providers

TomeWeaver is provider-agnostic and supports any API compatible with the OpenAI specification. Use the **API Connections Manager** in the UI to plug in your provider of choice.

### 🌟 Highly Recommended: LM Studio (Local AI)
We strongly recommend running TomeWeaver locally using **[LM Studio](https://lmstudio.ai/)**. 
*   **100% Free & Private:** Runs entirely on your own hardware offline. No subscriptions, no data harvesting.
*   **Uncensored:** Cloud providers (like OpenAI or Anthropic) often filter dark fantasy, horror, or gritty violence. Local models do not.
*   **Infinite Play:** Play a 5-hour campaign or a 50-hour campaign; you will never have to pay per token.

📖 **[Read the LM Studio Setup & Model Guide](docs/LM_STUDIO_CONFIG.md)** for step-by-step instructions on configuring the local server, preventing context-limit crashes, and downloading our curated list of the best local models for JSON-based story generation.

### Cloud Providers
If you do not have a dedicated GPU, TomeWeaver supports cloud providers seamlessly:
*   **OpenAI:** Native support for GPT-4o, GPT-5 and GPT-5.5.
*   **OpenRouter:** Access Claude 3.5 Sonnet, Llama 3.1, and dozens of other top-tier models for pennies.
*   **Gemini & Grok:** Fully compatible via their respective OpenAI-compatible endpoints.

---

## 🛠️ Installation & Setup

### Prerequisites
*   **An LLM Provider** (Local via LM Studio, or Cloud via an API key).

### Option A: Download Executable (Recommended)
The easiest way to run TomeWeaver. No Python installation or command-line knowledge is required. We provide pre-built, portable executables for Windows, macOS, and Linux.

1.  Navigate to the **[Latest Releases](https://github.com/dobrado76/TomeWeaver/releases/latest)** page on GitHub.
2.  Download the `.exe` file for your operating system.
3.  The configurations will be saved along the .exe, it is recommended you create a folder for it.
4.  Double-click the `TomeWeaver` executable to launch the app!

### Option B: Windows (Run from Source Setup)
If you prefer running from source, we provide an automated setup script that creates an isolated virtual environment and installs the UI dependencies. *(Requires Python 3.10+ installed and added to PATH)*.

1a. Either **Clone the repo:**
    ```cmd
    git clone https://github.com/dobrado76/TomeWeaver.git
    cd TomeWeaver
    ```
1b. or **Download the compressed Repo '.zip' file:**
    **[Latest Releases](https://github.com/dobrado76/TomeWeaver/releases/latest)**
2.  **Run the Installer:**
    Double-click the `setup.bat` file in the root directory. This will download everything needed for the GUI.
3.  **Launch the Engine:**
    Double-click the newly generated `Start_TomeWeaver.bat`. This will boot the main Graphical Interface.

4.  **(Optional) Run Automated Tests:**
    Double-click `Run_Tests.bat` to execute the headless pytest suite against the engine core.

### Option C: macOS / Linux / Manual Source Setup
If you are on a UNIX-based system or prefer setting up your environment manually:

1.  **Clone the Repo:**
    ```bash
    git clone https://github.com/dobrado76/TomeWeaver.git
    cd TomeWeaver
    ```
2.  **Create and Activate a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Launch the GUI:**
    *(Ensure your virtual environment is active before running)*
    ```bash
    python scripts/gui.py
    ```
---

## 📖 The Adventure "Cartridge" System

TomeWeaver treats every adventure as a self-contained "Cartridge" (a folder inside `/adventures`). You can easily share your worlds or back up your saves just by zipping the folder. 

### The Universe Structure
If you are using the Shared Universe feature, cartridges are nested to share memory:
*   `[UNIVERSE FOLDER]` -> Contains `master_setup.json` and `shared_memory.json` (Global Lore).
    *   `[STORY THREAD A]` -> Contains local `setup.json` and `history.json`.
    *   `[STORY THREAD B]` -> Contains local `setup.json` and `history.json`.

### Core Configuration Files (Author Created)
To build a new adventure, these files dictate the logic:
*   `setup.json`: The "DNA" of your world. Defines the tone, characters, plot outline, mechanics, and optional **`theme_preset` / `theme_embedded`** UI skin. *(Edited via the Story World UI tab).*
*   `system_prompt.txt`: The core rules and strict formatting instructions for your AI Game Master.
*   `prologue.txt` *(Optional)*: A hand-written opening text to anchor the start of your story.
*   `epilogue.txt` *(Optional)*: A hand-written closing text for when the campaign goal is achieved.
*   `start_turn.json` *(Optional)*: A "Story Seed." Provide a pre-generated Turn 1 JSON object to guarantee players begin with a specific, high-quality hook and set of choices.

### Engine State Files (Auto-Generated)
As you play, TomeWeaver automatically generates and manages these files to maintain the game state:
*   `history.json`: The master ledger. A perfect chronological record of every turn, AI response, player choice, and narrative bridge.
*   `memory.json`: The RAG database. Contains the compressed Plot Ledger and Local Entity lore.
*   `chapters.json`: The pacing metadata. Tracks where chapters begin and end.
*   `runs/manifest.json`: The **Run Tree** index—archived timelines, fork metadata, and which branch is active at the cartridge root.
*   `runs/snapshots/<run_id>/`: Per-timeline copies of `history.json`, `chapters.json`, and `memory.json` for fork/switch/share workflows.
*   `session_log.txt`: The "Flight Recorder." A diagnostic log of every API call, retry, and raw JSON output for debugging your prompts.
*   `spelling_lexicon.json` *(Optional, per story)*: Custom dictionary, ignored spellings, and ignored grammar hits for this cartridge.
*   `{universe}/spelling_lexicon.json` *(Optional)*: Shared Universe lexicon layer (merged when checking).
*   `{adventures_dir}/spelling_lexicon_global.json` *(Optional)*: Library-wide lexicon when using global save scope.

---

## 📚 Official Documentation

TomeWeaver is a massive, feature-rich application. Please refer to our dedicated guides for detailed instructions on using the UI and configuring your worlds:

*   🖼️ **[The UI Walkthrough (docs/README.md)](docs/README.md)** - A visual guide to the Library Dashboard, Story Timeline, and Editors.
*   📄 **[NSM Architecture Article (PDF)](docs/article/MMG-NSM-1.0%20-%20The%20Narrative%20State%20Machine.pdf)** - Systems specification; [LaTeX source](docs/article/main.tex).
*   ⌨️ **[Gameplay & User Guide (docs/COMMAND_GUIDE.md)](docs/COMMAND_GUIDE.md)** - How to play, perform Timeline Surgery, and use Director tools.
*   ⚙️ **[Configuration & Architecture (docs/CONFIG_GUIDE.md)](docs/CONFIG_GUIDE.md)** - Deep dive into how the engine processes Campaign logic, Universes, and JSON schemas.
*   🧠 **[Long-Term Memory & RAG (docs/RAG.md)](docs/RAG.md)** - Plot ledgers, entity tracking, auto-decay, and continuity auditing.
*   🧠 **[LM Studio Setup & Models (docs/LM_STUDIO_CONFIG.md)](docs/LM_STUDIO_CONFIG.md)** - How to configure local, free LLMs to run the engine.
*   🗺️ **[Future Roadmap (docs/FUTURE.md)](docs/FUTURE.md)** - v0.3 → v1.0 stabilization and planned post-v1.0 features.

---

## 🗺️ Roadmap

TomeWeaver is at **v0.3**. The path to **v1.0**—a release ready for prime time—is focused on testing, debugging, and hardening the engine, not piling on new features. After that gate, planned work follows a **high value / low VRAM overhead** philosophy:

*   **RPG Mode (Third Pillar)** — A dedicated crunchy mode with `character_stats.json`, `[CHECK: …]` skill tags, local dice resolution, and a Story Tab overlay.
*   **Tension Heatmap** — Narrative pacing analytics compiled during RAG (physical danger + emotional tension line graphs).
*   **Party Management** — Multi-POV `party_ledger` with header portraits and one-click active POV switching.
*   **Voice of the Weaver (TTS)** — Optional per-turn narration via local Piper/Kokoro or cloud ElevenLabs, lazy-loaded so gameplay never blocks.

For the full architect's vision—data models, engine integration, phased rollout, and explicit out-of-scope items—see **[docs/FUTURE.md](docs/FUTURE.md)**.

---

## 🤝 Contributing

We welcome contributions! Whether it's improving the "Fortress" sanitizer, adding new export formats, sharing Adventure Cartridges, or **minor fixes to the NSM article LaTeX** (see [PDF](docs/article/MMG-NSM-1.0%20-%20The%20Narrative%20State%20Machine.pdf)):

1.  Fork the repository.
2.  Create your feature branch (`git checkout -b feature/AmazingFeature`).
3.  Run the test suite (`Run_Tests.bat` or `venv\Scripts\python.exe -m pytest tests/ -v`) before submitting engine changes.
4.  Commit your changes (`git commit -m 'Add AmazingFeature'`).
5.  Push to the branch (`git push origin feature/AmazingFeature`).
6.  Open a Pull Request.

---

## ⚠️ Known Limitations

TomeWeaver is a powerful narrative operating system, but it is not magic. Understanding these boundaries helps set realistic expectations:

### LLM & Hardware Dependencies
*   **Model quality varies widely.** Smaller local models (7B–8B) may require more JSON repair retries, produce weaker campaign goal reasoning, or drift off-tone despite the Fortress sanitizer. Cloud models generally produce more consistent structured output.
*   **Context is finite.** Even with RAG compression, extremely lore-heavy worlds or very long `context_window` settings can exceed your model's `n_ctx` (LM Studio) or provider token cap, causing HTTP 400 errors. Lower `context_window`, raise `memory_decay_threshold`, or use a model with a larger context.
*   **`auto_polish` doubles token cost.** Every turn runs a second LLM pass for copy-editing when enabled.

### Narrative & Gameplay
*   **Campaign goals are AI-interpreted, not deterministic.** The engine prompts the model to verify goal completion; it cannot mathematically prove a puzzle was solved. Complex logic puzzles may require Director intervention or manual chapter advancement.
*   **RAG summaries can hallucinate.** Plot Ledger and Entity entries are AI-generated compressions. Use **Validate** and **Auto-Patch** in the Memory tab, or run **Integrity Check** compile mode, to audit contradictions.
*   **Timeline surgery invalidates affected RAG ledgers.** Inserting, deleting, splitting, or merging turns/chapters clears plot/chapter ledger entries for impacted chapter numbers—they must be recompiled via **Compile Missing History**.
*   **Universe threads require careful migration.** Moving stories into or out of Shared Universes triggers wizards and may require a full memory recompile. Orphaned threads (moved folders) are auto-recovered to standalone mode with a warning.

### UI & Platform
*   **Desktop GUI only.** TomeWeaver is a CustomTkinter desktop application. There is no web client, mobile app, or multiplayer session sharing in real time.
*   **Windows-first launcher scripts.** `setup.bat`, `Start_TomeWeaver.bat`, and `Run_Tests.bat` are Windows batch files. macOS/Linux users should follow Option C and use manual `venv` + `python scripts/gui.py` commands.
*   **Executable builds hide the terminal.** PyInstaller `--noconsole` builds suppress stdout; use the **Developer Console** tab or `session_log.txt` for diagnostics.
*   **Single-player, local saves.** Progress lives in your `/adventures` folder. There is no cloud sync, account system, or cross-device save merge.
*   **Offline spell check is dictionary-based.** It flags likely typos, not deep grammar or style. Fantasy coinages can be **Add to dictionary**, **Ignore**, or appear in Memory & Lore to be accepted.
*   **Offline grammar check is rule-based.** It catches common mechanical errors but not nuanced voice, dialect, or intentional stylistic breaks. Use **Ignore this issue** or disable **Offline Grammar Check** if amber underlines distract during dialogue-heavy drafts.
*   **Offline synonyms use WordNet.** Suggestions are literal thesaurus entries, not voice-aware rewrites; proper nouns and lore terms often return no results.

### Import, Export & Interoperability
*   **Export Story (TXT/MD/HTML)** is prose compilation for reading—not a playable save.
*   **Bulk Import Turns** expects a simple `>` / `=` action-marker syntax; free-form prose without markers becomes a single trailing turn block.
*   **Full ZIP cartridges** require `setup.json` and `system_prompt.txt` at minimum. Custom prompts referencing external files not included in the zip will break on import.
*   **Branch packs** import timelines into an existing story; they do not replace `setup.json` or the active root unless you **Switch** to an imported branch. Setup fingerprint mismatches are warned but can be forced.
*   **Run Tree switch** persists the active timeline to its snapshot before loading another; unlinked root play (no `active_run_id`) is not auto-associated with manual restart archives until you switch from an active branch.

### Developer Notes
*   **Tests cover the headless engine core**, not the full GUI or live LLM API calls. Integration tests that hit real models should be run manually.
*   **`ADV_DIR` is relative to the process working directory.** Always launch from the repo root (or the folder containing `adventures/`) so paths resolve correctly.

---

## ⚖️ License & Commercial Use

TomeWeaver is released under the **Polyform Non-Commercial License 1.0.0**.

### What this means:
- ✅ **Personal Use:** You can use, modify, and play with TomeWeaver for free forever.
- ✅ **Contribution:** You are encouraged to fork the repo and submit Pull Requests to improve the engine.
- ✅ **Education/Research:** You can use this code for learning or academic purposes.
- ❌ **Commercial Use:** You **cannot** sell this software, use it to power a paid service, or include it in a commercial product without a separate agreement.

**For commercial licensing inquiries, please contact the author directly via [GitHub Profile](https://github.com/dobrado76).**

---

**TomeWeaver** — *Play the game. Export the novel.*