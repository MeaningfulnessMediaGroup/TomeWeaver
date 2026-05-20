# TomeWeaver: Gameplay & User Guide

TomeWeaver is an interactive fiction engine, but it is also a powerful writing tool. This guide explains how to play the game, how to use the UI's "Director Tools" to sculpt your adventure, and how to harness the AI to co-write your story.

---

## 🏗️ Starting an Adventure (The Story Forge)

You do not need to manually create folders or write raw JSON files to play TomeWeaver. From the **Library Dashboard**, click the **+ Create New Story** dropdown to access the Story Forge.

1.  **Guided Wizard:** The easiest way to start. The Wizard will walk you step-by-step through defining your protagonist, setting, rules, and goals, before dropping you into the World Builder to review your choices.
2.  **Generate via AI:** Simply type a single concept (e.g., *"A gritty detective noir set on a space station"*) and let the AI instantly generate the entire world configuration, chapter outline, and starting lore.
3.  **Manual Setup:** Opens a clean, single-page form to quickly define the basics yourself.

### The Two Game Modes
When creating a story, you must choose a Mode. This fundamentally changes how the engine behaves:
*   **Sandbox Mode:** Open-ended and player-driven. The world is persistent, but there is no strict plot. You use the Director Dropdown during gameplay to manually trigger time-jumps and scene shifts.
*   **Campaign Mode:** Plot-driven and structured. The AI strictly follows the Chapter Outline you define in the World Builder. The engine will not allow you to progress until the conditions of the active chapter goal are met in the story.

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

## ⏳ Time Travel & Timelines

### The Undo Button
Located in the footer of the active card (and next to the Submit button). Click `↶ Undo Last Turn` to roll back time by one turn. This deletes the current scene and restores the green action buttons of the previous turn, allowing you to make a different choice.

### The History Slider
On the right side of the screen is the **Time Travel Slider**. The engine only renders 3 cards at a time to prevent performance lag, but you can drag this slider up to instantly scrub back through hundreds of past turns.
*   **Manually Editing History:** If you find a typo in Turn 5, click **✎ Edit** on its card to manually fix the text without asking the AI.
*   **Branching History:** If you want to permanently change the course of the story from Turn 5, you must `Undo` all the way back to it and make a new choice.

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