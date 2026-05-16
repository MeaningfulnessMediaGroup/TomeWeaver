# TomeWeaver

A Stateful Narrative Orchestration Engine for LLMs. TomeWeaver bridges the gap between generative AI and structured game design, transforming player adventures into seamless, exportable storybooks.

![License](https://img.shields.io/badge/license-Polyform--NonCommercial-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen)
![LLM](https://img.shields.io/badge/LLM-Agnostic-orange)

---

## 🚀 The Vision

Most AI storytelling tools are "chaos simulators"—they struggle with context drift, lose track of goals, and produce "jumpy" prose. **TomeWeaver** is a narrative pipeline that treats a story as a structured database. 

It provides the "bones" of a game (inventory, chapters, goals) and the "soul" of a novel, resulting in a journey that is fun to play and beautiful to read back later.

## ✨ Key Features

### 1. Dual-Mode Storytelling
*   **Sandbox Mode:** Open-ended world simulation. Use the built-in **Chapter Wizard** to manually trigger scene shifts, POV changes, or time-jumps.
*   **Campaign Mode:** Plot-driven adventures using a "Chapter Cartridge" system. The AI follows a `plot_outline` with specific goals and obstacles for every chapter.

### 2. Non-Destructive Narrative Bridging
TomeWeaver solves the "narrative gap" common in AI games. 
*   **The Problem:** In most games, you click "Go inside" and the next paragraph starts inside, leaving a jump-cut.
*   **The Solution:** TomeWeaver generates a **Narrative Bridge**—a surgical patch that weaves your choice into the prose.
*   **Integrity:** These bridges are stored as metadata. Your original human-curated prose is never modified or overwritten.

### 3. The "Fortress" JSON Sanitizer
Local LLMs often struggle with strict JSON formatting. TomeWeaver’s multi-stage sanitizer is built for resilience:
*   **State-Machine Repair:** Uses a look-ahead parser to differentiate between structural JSON markers and rogue dialogue quotes.
*   **Surgical Repair:** Uses error-coordinate metadata to "patch" missing quotes or trailing commas.
*   **Truncation Recovery:** If the AI hits its token limit mid-sentence, the engine auto-balances the JSON so you can continue playing without a crash.

### 4. Self-Healing Master Clock
Never worry about manual edit errors. Every time an adventure launches, TomeWeaver performs a **Master Clock Resync**, ensuring all turn indices are perfectly sequential to protect chapter and bridge logic.

### 5. Storybook Compiler (Export)
Export your adventure as a polished **TXT, Markdown, or HTML** file. The engine "compiles" the story on the fly, merging your prose and narrative bridges into a fluid, professional-grade storybook.

---

## 🧠 Supported LLM Providers

TomeWeaver is provider-agnostic and supports any API compatible with the OpenAI specification:

*   **LM Studio (Highly Recommended):** For 100% free, unlimited, and private local generations. This is the gold standard for testing and personal play.
*   **OpenAI:** Native support for GPT-5 and GPT-5.5.
*   **Gemini:** Access to your favorite AI model via Google AI Studio.
*   **OpenRouter:** Access Claude 3.5 Sonnet, Llama 3.1, and dozens of other top-tier models.
*   **Grok / xAI:** Compatible with the Grok API.

---

## 🛠️ Installation & Setup

### Prerequisites
*   **Python 3.10+** (Ensure Python is added to your system PATH)
*   **An LLM Provider:** 
    *   **Local:** [LM Studio](https://lmstudio.ai/) (Recommended for privacy and zero cost).
    *   **Cloud:** OpenAI, OpenRouter, or Gemini (API Key required).


### ⚙️ Configure your LLM
Before anything, edit the `engine_config.json` file in the root directory to point to your chosen AI provider.

**For LM Studio (Default):**
```json
{
  "api_url": "http://localhost:1234/v1/chat/completions",
  "model": "loaded-model"
}
```

### Option A: Windows (Automated Setup)
We provide an automated setup script that creates an isolated virtual environment and generates your Master Launcher.

1.  **Clone or Download the Repo:**
    ```cmd
    git clone https://github.com/dobrado76/TomeWeaver.git
    cd TomeWeaver
    ```
2.  **Run the Installer:**
    Double-click the `setup.bat` file in the root directory. 
3.  **Launch the Engine:**
    Double-click the newly generated `Start_TomeWeaver.bat`. This opens the **Main Menu Wizard**, allowing you to select an existing story or create a new one.


### Option B: macOS / Linux / Manual Setup
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
4.  **Launch the Main Menu:**
    *(Ensure your virtual environment is active before running)*
    ```bash
    python scripts/tome_weaver.py
    ```

---

## 📖 How to Build an Adventure

TomeWeaver treats every adventure as a self-contained "Cartridge" (a folder inside `/adventures`). 

**The Easiest Way to Start:**
1. Open the Main Menu (`Start_TomeWeaver.bat`).
2. Select **[Start a New Story]**.
3. Type a title. The engine will automatically generate the folder, create a desktop-friendly `.bat` shortcut (e.g., `Story - My Epic Tale.bat`), and prompt you to choose between Campaign or Sandbox mode.
4. Open your new `adventures/Your_Title/setup.json` file to define your world, tone, and character.
5. Double-click your new `Story - Your_Title.bat` shortcut to play!

### Core Configuration Files
*   `setup.json`: The "DNA" of your world. Defines the tone, characters, plot outline, and mechanics.
*   `system_prompt.txt`: The core rules and strict formatting instructions for your AI Game Master.
*   `prologue.txt` *(Optional)*: A hand-written opening text to anchor the start of your story.
*   `epilogue.txt` *(Optional)*: A hand-written closing text for when the campaign goal is achieved.
*   `start_turn.json` *(Optional)*: A "Story Seed." Provide a pre-generated Turn 1 JSON object to guarantee players begin with a specific, high-quality hook and set of choices.

---

## ⌨️ Gameplay & In-Game Commands

Playing TomeWeaver is as simple as typing the number of your desired choice. However, the engine is highly flexible. Instead of a number, you can type **any custom action or dialogue** (e.g., *"I draw my sword and demand to know who sent them!"*), and the AI will adapt the story instantly.

You also have access to powerful "Director" commands to shape the narrative, edit history, or change the mechanics on the fly. 

👉 **[Read the Full Command Guide (COMMAND_GUIDE.md)](COMMAND_GUIDE.md)**

**Quick Reference:**
*   `?` / `help`: Show the command menu.
*   `undo`: Roll back the last turn.
*   `redo`: Reroll the current AI response.
*   `fix: [instruction]`: Instruct the AI to edit the current turn (e.g., `fix: make it raining`).
*   `novelize`: Weave your mechanical choices into seamless prose.
*   `export`: Save your adventure to a readable TXT, Markdown, or HTML file.
*   `restart`: Wipe progress and start from Turn 0.

---

## 📖 The Adventure "Cartridge" System

TomeWeaver treats every adventure as a self-contained folder. You can easily share your worlds or back up your saves just by zipping the folder.

### Core Configuration Files (Author Created)
To build a new adventure, you only need to create these files:
*   `setup.json`: The "DNA" of your world. Defines the tone, characters, plot outline, and mechanics.
*   `system_prompt.txt`: The core rules and strict formatting instructions for your AI Game Master.
*   `prologue.txt` *(Optional)*: A hand-written opening text to anchor the start of your story.
*   `epilogue.txt` *(Optional)*: A hand-written closing text for when the campaign goal is achieved.
*   `start_turn.json` *(Optional)*: A "Story Seed." Provide a pre-generated, hand-crafted Turn 1 JSON object to guarantee players begin with a specific, high-quality hook and set of choices.

### Engine State Files (Auto-Generated)
As you play, TomeWeaver automatically generates and manages these files to maintain the game state:
*   `history.json`: The master ledger. A perfect chronological record of every turn, AI response, player choice, and narrative bridge.
*   `chapters.json`: The pacing metadata. Tracks where chapters begin and end, and stores Wizard overrides (like POV or Time jumps).
*   `session_log.txt`: The "Flight Recorder." A diagnostic log of every API call, retry, and raw JSON output for debugging your prompts.

---

## ⚙️ Configuration & Documentation

TomeWeaver is designed for deep customization. For detailed instructions on API setup, campaign logic, and advanced world-building lore, please refer to the separate guide:

👉 **[Adventure Configuration Guide (CONFIG_GUIDE.md)](CONFIG_GUIDE.md)**

**This guide covers:**
- Global API and "Fortress" settings (`engine_config.json`)
- Differences between **Campaign** and **Sandbox** schemas (`setup.json`)
- How to add custom fields for family trees, world lore, and AI instructions.
- Narrative pacing and Prologue/Epilogue behavior.


---

## 🤝 Contributing

We welcome contributions! Whether it's improving the "Fortress" sanitizer, adding new export formats, or sharing your own Adventure Cartridges:
1.  Fork the repository.
2.  Create your feature branch (`git checkout -b feature/AmazingFeature`).
3.  Commit your changes (`git commit -m 'Add AmazingFeature'`).
4.  Push to the branch (`git push origin feature/AmazingFeature`).
5.  Open a Pull Request.

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