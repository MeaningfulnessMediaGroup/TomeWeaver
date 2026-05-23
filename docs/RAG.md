# TomeWeaver: Long-Term Memory (RAG Engine)

One of the greatest challenges of playing AI text adventures is the "Context Limit." Local LLMs can only remember a certain amount of text before they run out of VRAM and crash, or suffer from "Context Amnesia," forgetting characters and plot points from earlier in the game.

TomeWeaver solves this by implementing an autonomous **Retrieval-Augmented Generation (RAG) Engine**.

![Memory Tab Overview](../images/rag_dashboard.jpg "Screenshot of the Memory & Lore tab showing the Left Nav and the Plot Ledger.")

---

## 📚 The Dual-Ledger System

Instead of feeding the AI thousands of lines of raw game history, TomeWeaver's background compiler actively reads your gameplay and extracts data into token-efficient "Ledgers".

### 1. The Plot Ledger (Chronological Memory)
The engine mathematically slices your raw game history into chunks (dictated by your `Context Window` setting, usually 10-15 turns). 
*   **Part Summaries:** It asks the AI to convert those raw turns into a dense, bulleted list of facts.
*   **Chapter Summaries:** When a Chapter concludes, the engine gathers all the granular "Parts" for that chapter and condenses them into a single, high-level Chapter Summary, saving massive amounts of API tokens while retaining the overall narrative arc.

### 2. The Entity Ledgers (Stateful Memory)
The engine tracks the evolving state of the world across four categories:
*   👤 **Characters**
*   🗺️ **Locations**
*   💎 **Artifacts & Items**
*   🛡️ **Factions & Organizations**

Every time a chunk is processed, the AI extracts new events or static traits (e.g., Age, Appearance, Magic rules) and permanently appends them to the entity's Lore profile.

---

## 🌐 Dual-Tiered Memory (Global vs. Local)

In Version 0.2, TomeWeaver introduces **Shared Universes**. This means the RAG Engine must manage data across multiple timelines without confusing the AI.

When playing inside a Universe, entities are assigned a Memory Scope:
*   **Local Scope (Blue/Purple Icon):** This entity only exists in the current story thread (e.g., a random tavern cashier). It prevents the global Universe from bloating with minor characters.
*   **Global Scope (Orange Icon):** This entity is stored in the Universe's World Bible. Any story played in this Universe will recognize and interact with them.

### Local Overrides (The Prequel Solution)
What happens if you want to play a flashback story set 10 years before the main campaign? 
TomeWeaver allows you to create a **Local Override**. If an entity exists in *both* Global and Local memory, they will appear side-by-side in your UI. The engine will seamlessly send the Local version to the AI for that specific story. This allows you to play a prequel where the King is young and benevolent (Local), without overwriting his Present-Day profile as an old tyrant (Global)!

---

## ⚙️ The Auto-Decay Engine (Context Bloat Prevention)

If you track 50 characters, feeding all 50 to the AI every single turn will instantly blow out your Context Limit. TomeWeaver uses an invisible "Auto-Decay" regex scanner to manage this.

![Entity State Dropdown](../images/rag_decay.jpg "Screenshot of the state dropdown showing Active, Pinned, and Archived options.")

*   **Active:** The entity is currently relevant and injected into the AI's prompt.
*   📦 **Archived:** The entity has not been mentioned in the story for `X` turns (Configurable via "Memory Decay Threshold" in Global Settings). They are hidden from the AI to save tokens. **If you or the AI mention an archived entity by name, they are instantly revived and returned to Active status!**
*   📌 **Pinned:** A manual override. The entity will NEVER decay and will always be sent to the AI (useful for tracking the main villain, even if they aren't currently in the room).

---

## 🛠️ The Continuity Editor & Auto-Patching

Because LLMs occasionally hallucinate, TomeWeaver provides powerful Quality Assurance (QA) tools to ensure your memory ledgers are mathematically perfect.

### The Missing History Compiler
If you edit the timeline manually or drag a story into a new Universe, you can click **Compile Missing History**. You have 4 modes:
1.  **Base Lore:** Extracts static traits from your `setup.json` without reading the game history.
2.  **Standard:** Fast. Only reads and summarizes new turns that haven't been compiled yet.
3.  **Deep Entity Scan:** Forcefully re-reads your entire history. Useful if you just added a new Character manually and want the AI to retroactively find past events involving them.
4.  **Integrity Check (Verify):** Acts as a Continuity Editor. It reads your current Plot Ledger against your current Entity Lore and generates a detailed report of any logical contradictions (e.g., *"The Plot says Kaelen died, but his Lore profile says he is drinking at the tavern."*)

### Granular Validation & Auto-Patching
If you suspect a specific Plot Chunk hallucinated a detail, click the **✔️ Validate** button on its card.

![Validation Report](../images/rag_validation.jpg "Screenshot of a Fidelity Score report showing missing and fabricated details, with the Auto-Patch button.")

1.  The engine will send the original raw turns and the summary to the AI and ask for a strict Fidelity Score (e.g., "85/100").
2.  It generates a bulleted QA Report detailing exactly what is missing, fabricated, or inaccurate.
3.  Click **🔧 Auto-Patch Summary**. The engine will autonomously order the AI to rewrite the summary using the QA report as an instruction manual, update the UI, and automatically re-validate itself to prove the fix worked!

### Zero Data-Loss Merging
If the AI accidentally extracts "Vance" and "Captain Vance" as two separate characters, you can easily merge them. The engine uses a "Smart Merger" to elegantly combine their traits. If one says `Appearance: Tall` and the other says `Appearance: Wears a hat`, the merged entity becomes `Appearance: Tall | Wears a hat`. It also creates a permanent **Alias** so future mentions of "Vance" automatically route to the Master Entity.