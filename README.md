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
*   **Python 3.10+**
*   **LM Studio** (for local play) or an **API Key** for cloud providers.

### Quick Start
1.  **Clone the Repo:**
    ```bash
    git clone https://github.com/dobrado76/TomeWeaver.git
    cd TomeWeaver
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure your LLM:**
    Edit `engine_config.json` in the root folder.
    
    **For LM Studio:**
    ```json
    {
      "api_url": "http://localhost:1234/v1/chat/completions",
      "model": "loaded-model"
    }
    ```
    **For OpenRouter:**
    ```json
    {
      "api_url": "https://openrouter.ai/api/v1/chat/completions",
      "api_key": "your-key-here",
      "model": "anthropic/claude-3.5-sonnet"
    }
    ```
4.  **Launch an Adventure:**
    ```bash
    python scripts/tome_weaver.py adventures/my_story
    ```

---

## ⌨️ In-Game Commands

While playing, you can use these commands at any time:
*   `?` / `help`: Show the command menu.
*   `undo`: Roll back the last turn.
*   `redo`: Reroll the current AI response.
*   `fix: [reason]`: Keep the turn but instruct the AI to edit it (e.g., `fix: make it raining`).
*   `novelize`: Run the batch processor to fill narrative gaps with seamless bridges.
*   `export`: Save your storybook to disk (TXT, MD, HTML).
*   `restart`: Wipe progress and start from Turn 0.

---

## 📖 How to Build an Adventure

TomeWeaver uses a simple folder-based "Cartridge" system. A new adventure requires:
*   `setup.json`: Defines the world, tone, and character.
*   `system_prompt.txt`: The core rules for your Game Master.
*   `prologue.txt` (Optional): The fixed opening of your story.
*   `epilogue.txt` (Optional): The fixed ending of your story.

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