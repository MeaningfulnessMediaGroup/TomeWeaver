# TomeWeaver: Gameplay & Command Guide

This guide details how to interact with the TomeWeaver engine, how to use custom actions, and how to utilize the powerful "Director" commands to shape your adventure.

---

## 🎮 Making Choices

At the end of every turn, TomeWeaver will present you with 3 to 6 logical choices based on your current situation. 

**Standard Input:** 
Simply type the number of the choice you want (e.g., `1`, `2`, `3`) and press Enter.

**Custom Narrative Input:**
You are not restricted to the numbered choices! If you want to do something completely different, simply type your action, dialogue, or strategy directly into the prompt. 
*   *Example:* `I ignore the goblin entirely and begin inspecting the ancient runes on the wall.`
*   *Example:* `"I'll pay your toll, but only if you tell me what lies ahead," I say, tossing him two silvers.`

The AI will parse your custom input and immediately weave it into the resulting scene.

---

## ⚙️ The Master Command Table

These commands can be typed directly into the prompt at any time. They are categorized by function.

### Navigation & Utilities
| Command | Description |
| :--- | :--- |
| `help` / `?` | Displays the quick-reference command menu in the console. |
| `clear` | Clears the terminal screen and redraws the current turn. Useful if the text scrolled too far up. |
| `recap` / `summary` | Pauses the game and asks the AI to generate a "Story So Far" summary. Great for picking up an old save. |
| `export` | Opens the export menu. Converts your adventure history into a readable `TXT`, `Markdown`, or `HTML` storybook. |
| `quit`, `exit`, `q` | Safely saves your current state and exits the engine. |

### Time Travel & Editing
*TomeWeaver treats interactive fiction like a drafting process. You have full control over the timeline.*

| Command | Description |
| :--- | :--- |
| `undo` | Reverts the game state back to the previous turn. If you make a choice and don't like where the story went, this takes you back so you can choose again. |
| `redo` | Discards the AI's current text and forces it to generate a completely new response for your last action. Use this if the AI hallucinates or writes a boring response. |
| `fix: [instruction]` | Keeps the current turn, but sends it back to the AI with a strict instruction to edit a specific detail. <br>• *Example:* `fix: change the rusty dagger to a glowing blue sword.` <br>• *Example:* `fix: make the dialogue sound more aggressive.` |
| `restart` | Deletes your current history and restarts the adventure from the beginning. *(Note: This cannot be undone).* |

### Developer Tools
| Command | Description |
| :--- | :--- |
| `test` | Engages "Autopilot Mode." The engine plays itself by automatically selecting the choice that makes the story progress most rapidly for every turn until the game ends. Used to rapidly verify that your Campaign goals and JSON logic are functioning correctly. |

---

## 🎬 Director Commands (Sandbox Mode Only)

If you are playing in **Sandbox Mode**, you have access to special "Director" commands that allow you to forcefully steer the simulation. 

*(Note: These are disabled in Campaign Mode, as the plot outline controls the flow of time and setting automatically).*

| Command | Description |
| :--- | :--- |
| `chapter` | Opens the interactive Chapter Wizard. The engine will ask you to name the next chapter and optionally provide a new Setting, POV, or Time jump. The AI will then automatically wrap up the current scene. |
| `time: [instruction]` | Forcefully skips time. The AI will honor this in the next turn. <br>• *Example:* `time: Skip ahead three days to when we finally reach the mountain.` |
| `setting: [instruction]`| Forcefully shifts the location. <br>• *Example:* `setting: We are now inside the shadowy interior of the tavern.` |
| `pov: [character]` | Forcefully shifts the perspective character. <br>• *Example:* `pov: Switch the perspective to the villain watching them from the crystal ball.` |

