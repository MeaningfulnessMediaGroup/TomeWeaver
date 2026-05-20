# TomeWeaver: User Interface Guide

TomeWeaver features a modern, dark-mode desktop GUI built on `CustomTkinter`. This guide provides a visual walkthrough of the application's major interfaces and how to use them.

---

## 1. The Library Dashboard

When you launch TomeWeaver, you are greeted by the Library Dashboard. This is your central hub for managing Adventure Cartridges. The dashboard features a blazing-fast virtualized grid, allowing you to seamlessly search, sort, and navigate through hundreds of nested folders and stories.

![Dashboard](images/dashboard.jpg "Screenshot of the Dashboard. Shows a grid of story cards, a search bar, breadcrumb folder navigation, and the '+ Create New Story' dropdown.")

### The "Story Forge" (Creating a New Adventure)
Clicking the green **+ Create New Story** dropdown in the top right offers three distinct ways to build a new world:
1.  **Manual Setup:** Opens a clean, single-page form allowing you to instantly type out the Title, Author, and Rules for a new Sandbox or Campaign.
2.  **Generate via AI:** Don't know what to write? Type a single concept prompt (e.g., *"A cyberpunk detective hunting a rogue AI"*), and the engine will automatically generate the title, lore, chapters, and setting for you.
3.  **Guided Wizard:** The ultimate onboarding tool. Walks you step-by-step through a clean, multi-screen process to define your protagonist, tone, and goals.

Once a story is created, the engine automatically routes you directly into the **World Builder** tab so you can review your configuration.

### Story Management
Each card displays the story's mode, turn count, current location, and status. Click **Play** to enter the Workspace. You can also use the **Options** dropdown on any card to Rename, Move, Delete, or Export the story to a `.zip` file to share with friends.

---

## 2. The World Builder (Codex)

The World Builder tab replaces the need to manually edit `setup.json` files. It translates the raw code of the engine into a user-friendly master-detail editor.

![World Builder Core Settings](images/world_builder.jpg "Screenshot of the World Builder 'Core Settings' tab. Shows text fields for Adventure Title, Author, Tone, and the AI Co-writing buttons.")

### Granular AI Co-Writing
TomeWeaver is a true Narrative IDE. Every major field in the World Builder features granular AI assistance:
*   **🪄 Inspire:** Type a quick shorthand idea (e.g., *"Grumpy dwarf"*), click Inspire, and the AI will expand it into rich, cinematic detail based on the overall context of your world.
*   **⟳ Reroll:** Completely stuck? Click Reroll, and the AI will invent a brand new, highly creative entry for that field from scratch.
*   **💡 Help:** Opens a scrollable modal packed with high-quality templates and examples. Click any example to instantly apply it to the field.

### Custom Lore (Codex)
Allows you to add infinite custom fields to your world. When you click "+ Add New Entry", you choose a data type (String, List, Dictionary). The UI dynamically transforms into the correct editor, preventing you from ever making a JSON syntax error.

### Inventory Schema Editor
If you enable "Track Inventory & Health", a visual pill-editor appears. You can define up to 8 tracking slots. When you hit Save, the AI will automatically scan your slots and assign perfectly matching Emojis and Hex Colors to them!

### ✨ The "Master Overhaul" Button
At the very top of the Core Settings tab is the **Generate World** button. If you are ever unhappy with your current story, you can use this to completely overwrite the active cartridge with a brand new AI-generated world without having to return to the Dashboard.

---

## 3. Chapter Outline Editor (Campaign Only)

If you are playing a Campaign, the **Chapter Outline** tab becomes available. This acts as the "Director's Script" for the adventure.

![Chapter Outline](images/chapter_editor.jpg "Screenshot of the Chapter Outline tab. Left pane shows a list of chapters. Right pane shows text fields for Chapter Title, Goal, Obstacles, and the AI Chapter Generator buttons.")

*   **Pacing the Plot:** The AI reads the active chapter's "Goal" and "Obstacles" every turn. It will not allow the player to progress until the conditions of the Goal are met in the story.
*   **Reordering:** You can easily add new chapters or use the arrow buttons to move plot beats up and down the timeline.
*   **AI Plotting Board:** The Chapter Outline features its own dedicated AI generator. Click **🪄 Inspire Chapter**, and the AI will look at the events of Chapter 1, figure out what naturally happens next, and automatically write Chapter 2 for you!

---

## 4. The Story Workspace (Timeline)

Clicking "Play" on the Dashboard opens the Workspace. The **Story Mode** tab is where the game is played. The engine only renders the 3 most recent turns to keep memory usage low, but you can scrub through older turns using the **Time Travel Slider** on the far right.

### The Turn Cards
Each card represents a single turn. It displays the active Chapter, Location, POV, and the **Story Prose**.
If Inventory tracking is enabled, the bottom of the card displays a dynamic, flat-UI ribbon of **Inventory Pills**. These pills seamlessly update every turn to reflect the protagonist's exact physical health, items, and status.

### The Input Bar & Actions
At the very bottom of the Story Timeline is the Input Bar.

![Input Bar](images/input_bar.jpg "Screenshot of the bottom Input frame. Shows a dropdown menu set to 'Standard Action', a text entry box saying 'Type a custom action...', a 'Submit' button, and an orange '↶ Undo' button.")

You can click the green choices generated by the AI, or type your own custom action into the text box. In **Sandbox Mode**, you have access to a Director Dropdown to force the AI's hand:
*   **Standard Action:** The default. Your text is treated as what the protagonist does or says.
*   **Expand Notes:** Co-write with the AI! Type a brief summary like "I defeat the guards in an epic sword fight," and the AI will expand it into cinematic prose.
*   **Force Setting:** Type a new location. The AI will instantly transition the scene.
*   **Force Time:** Type a time-jump (e.g., "Three days later").

---

## 5. Non-Destructive Editing (Visual Diffs)

TomeWeaver treats interactive fiction like a drafting process. Attached to the bottom of every Turn Card are several powerful editing tools: **⟳ Redo Turn**, **⟳ Choices**, **✨ Expand**, **✨ Condense**, **✨ Polish**, and **🔧 Fix...**

When you use "Safe" Card Tools like Expand, Polish, or Fix, the engine does not blindly overwrite your history. Instead, it opens the **Review Draft** modal.

![Visual Diff Editor](images/visual_diff.jpg "Screenshot of the Review Draft modal. It shows a split screen. On the left is the Original Text with red highlights for deleted words. On the right is the Proposed Revision with green highlights for inserted words. Buttons at the bottom: Cancel, Reroll, Accept.")

*   **Red Highlights:** Words the AI removed from the original text.
*   **Green Highlights:** New words the AI inserted.
*   **Safety First:** If the AI hallucinates, simply click **⟳ Reroll Draft** to ask the LLM to try again, or **Cancel** to discard it entirely.

---

## 6. Narrative Bridges

TomeWeaver solves the "narrative gap" common in AI storytelling. 

**The Problem:** In standard AI games, you choose an action like *"Go inside the tavern."* The AI responds by immediately describing the interior of the tavern. When you read the story back later, it feels like a jarring jump-cut. 

**The Solution:** Narrative Bridges.
*   **What they are:** Small, italicized paragraphs generated *between* your main story cards. They surgically convert your clicked action into third-person (or first-person) prose that matches the tense of the surrounding story.
*   *(Example Action: "Go inside") -> (Example Bridge: "Deciding the chill was too much, he pushed open the heavy oak doors and stepped inside.")*
*   **How they work:** You don't have to do anything. If "Auto Narrative Bridge" is enabled in your Global Settings, the engine spawns a silent background thread while you play. It looks at the action you just took, looks at the new scene the AI just generated, and writes a bridge connecting them.
*   **Non-Destructive:** Bridges are stored as metadata. They do not permanently alter the main prose of the story, meaning you can regenerate them or delete them in the Narrative IDE without breaking the game's logic.

---

## 7. The Developer Console

The Workspace features a dedicated **Developer Console** tab. This acts as the engine's "Flight Recorder." It provides a real-time, scrolling, color-coded view of the engine's internal states. If the engine catches an API timeout, rate limit, or JSON syntax error, it is broadcast here in real-time, allowing advanced users to monitor exactly what the LLM is doing under the hood.