--- START OF FILE COMMAND_GUIDE.md ---

# TomeWeaver: Gameplay & User Guide

TomeWeaver is an interactive fiction engine, but it is also a powerful writing tool. This guide explains how to play the game and how to use the UI's "Director Tools" to sculpt your adventure.

---

## 🎮 Playing the Game (The Input Bar)

At the bottom of the **Story Mode** timeline, you will find the Input Bar.

1. **Choosing an Action:** Every turn, the AI generates 3-6 green action buttons. Click one to immediately submit it.
2. **Custom Actions:** If you don't like the AI's choices, type your own action or dialogue into the text box and hit `Enter` (or click Submit).
    *   *Example:* `I ignore the goblin entirely and inspect the runes on the wall.`
    *   *Example:* `"I'll pay your toll," I say, tossing him two silvers.`

### 🎬 Director Overrides (Sandbox Mode Only)
In Sandbox mode, a dropdown appears next to the text input box. Use this to force the AI to change the state of the simulation:
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
| **✨ Polish** | *Safe.* Generates a Draft that acts as a professional copy-editor. Fixes grammar and sentence flow while strictly preserving the plot and dialogue. |
| **🔧 Fix...** | *Safe.* Opens a prompt asking for an instruction. (e.g., "Make it raining" or "Change the rusty dagger to a glowing blue sword.") Generates a Draft applying your fix. |

*Note: Safe tools open the **Visual Diff** window, allowing you to compare the original text to the AI's changes before accepting them.*

---

## ⏳ Time Travel & Timelines

### The Undo Button
Located next to the Submit button. Click `↶ Undo` to roll back time by one turn. This deletes the current scene and restores the green action buttons of the previous turn, allowing you to make a different choice.

### The History Slider
On the right side of the screen is the **Time Travel Slider**. You can drag this up to scroll back through hundreds of past turns.
*   If you find a typo in Turn 5, click **✎ Edit** on its card to manually fix the text.
*   If you want to branch the story from Turn 5, you must `Undo` all the way back to it.

---

## 🤖 Auto-Play (Test Mode)

If you are playing a **Campaign**, you will see a `▶︎ Auto-Play` button in the top right header.
*   When clicked, the engine takes control. Every 2 seconds, it will automatically click the first available action choice (The "Golden Path").
*   **Purpose:** This is a developer tool. It allows you to rapidly stress-test your Chapter Goals and plot outlines to ensure the AI understands how to complete the game.
*   Click the button again to stop Auto-Play and resume manual control.