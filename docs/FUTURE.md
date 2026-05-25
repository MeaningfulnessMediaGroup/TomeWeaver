# TomeWeaver: Future Roadmap (Architect's Vision)

This document describes **planned** features—not shipped functionality. It is the long-form design brief for where TomeWeaver goes *after* the current engine stabilizes.

**Related guides (what exists today):**
*   [User Interface Guide (README.md)](README.md)
*   [Configuration & Architecture (CONFIG_GUIDE.md)](CONFIG_GUIDE.md)
*   [Long-Term Memory / RAG (RAG.md)](RAG.md)
*   [Gameplay & Timeline Surgery (COMMAND_GUIDE.md)](COMMAND_GUIDE.md)
*   [Root README — current features & Known Limitations](../README.md)

---

## Where We Are: v0.3 → v1.0

TomeWeaver today is a **continuity-first narrative operating system** with Sandbox mode, Campaign mode, Shared Universes, dual-tiered RAG memory, timeline surgery, narrative bridges, and storybook export. That foundation is real and usable—but it is **not yet prime-time software**.

**Version 0.3** represents the current architectural milestone: the core engine, GUI, and memory systems are in place, and a growing headless test suite (`Run_Tests.bat`) covers timeline surgery, JSON sanitization, RAG behavior, export, and configuration paths. What remains before **v1.0** is not feature sprawl—it is **hardening**:

| Stabilization pillar | What “done” looks like for v1.0 |
|---|---|
| **Regression coverage** | Critical engine paths (timeline, RAG compile, save/load, universe migration) covered by automated tests; manual LLM integration checks documented. |
| **Edge-case debugging** | Known failure modes from [Known Limitations](../README.md#-known-limitations) triaged: campaign goal ambiguity, post-surgery RAG invalidation, JSON repair retries, context overflow. |
| **UX polish** | Loading states, error surfacing in the Developer Console, and Settings flows that do not require editing raw JSON for common tasks. |
| **Performance baselines** | Acceptable cold-start, dashboard scroll, and RAG compile times on mid-range hardware (8–12 GB VRAM class machines). |
| **Documentation parity** | Every shipped v1.0 feature documented in `docs/` with limitations called out honestly. |

**v1.0** is the release I would call **ready for prime time**: stable enough to recommend to non-developers, predictable enough to trust with hundred-turn campaigns, and honest enough about LLM limitations that users are not surprised when a local 7B model struggles.

Everything below is the **post-v1.0 “Level Up” roadmap**—or, where risk is low, features that may land in late v0.x releases *only after* stabilization gates are met. The guiding rule: **high narrative value, low VRAM overhead, no architectural bloat.**

---

## Design Philosophy: Why This List, and Not Something Else

Most AI “all-in-one” storytelling tools fail for predictable reasons:

*   They bolt on **image generation**, **voice cloning**, **multi-agent orchestration**, and **real-time world simulation** in one process.
*   VRAM becomes a zero-sum game: the model that writes prose competes with the model that draws portraits.
*   Load times balloon. UI threads block. Users on 8 GB GPUs—the heart of TomeWeaver’s audience—are abandoned.

TomeWeaver’s rebuttal to that approach is architectural discipline:

1. **Respect the VRAM wall.** New features must not require a second loaded model by default. Prefer deterministic logic, lightweight local libraries, or optional cloud APIs the user explicitly enables.
2. **Respect load times.** Heavy analysis runs in background threads (like RAG compilation today), never on the critical path of “click choice → read next paragraph.”
3. **Respect mode separation.** Sandbox is emergent chaos. Campaign is plot-driven prose. Crunchy mechanics belong in their own lane—not pasted onto Campaign’s goal engine.
4. **Reuse existing subsystems.** Universe scope, entity ledgers, RAG chunk compilation, and the Fortress JSON pipeline are extension points—not excuses to rewrite the engine.

The four features below were chosen because they score **High Value / Low Overhead** on every axis.

---

## 1. RPG Mode — The Third Pillar

### The Problem Today

Sandbox mode optimizes for **emergent narrative freedom**. Campaign mode optimizes for **plot structure and chapter goals**. Neither mode is ideal for players who want **mechanical stakes**: skill checks, resource tension, and outcomes that feel fairly adjudicated—not purely vibes-based.

Bolting dice mechanics onto Campaign would clutter the Director’s script. Bolting them onto Sandbox would fight the “no win condition” philosophy. The answer is a **third cartridge mode**: **RPG Mode**.

### Core Concept

RPG Mode is a prose-first interactive fiction engine **with an optional rules layer**. The LLM still writes cinematic paragraphs. The engine—not the LLM—resolves whether a risky action succeeds, using transparent stats and visible dice.

### Data Model: `character_stats.json`

Each RPG cartridge stores mechanical state separately from narrative `setup.json`, keeping prose configuration clean:

```json
{
  "ruleset": "tome_standard",
  "party_id": "default_party",
  "stats_schema": {
    "Strength": {"min": 1, "max": 20, "default": 10},
    "Agility": {"min": 1, "max": 20, "default": 10},
    "Arcana": {"min": 1, "max": 20, "default": 10},
    "Vitality": {"min": 1, "max": 20, "default": 10}
  },
  "characters": {
    "Hero": {
      "stats": {"Strength": 14, "Agility": 12, "Arcana": 8, "Vitality": 16},
      "modifiers": {"Agility": 2},
      "conditions": []
    }
  },
  "difficulty_classes": {
    "trivial": 5,
    "easy": 10,
    "moderate": 15,
    "hard": 20,
    "legendary": 25
  }
}
```

**Design notes:**

*   Stats live in a dedicated file so World Builder can expose a visual editor without polluting `plot_outline` or Sandbox lore fields.
*   `modifiers` stack from equipment, buffs, or temporary conditions—mirroring how inventory pills already track narrative state.
*   `ruleset` allows future presets (narrative-only checks vs. full combat) without breaking old cartridges.

### The LLM Contract: `[CHECK: …]` Tags

During RPG Mode, the system prompt instructs the model:

> When the player attempts something uncertain, emit a machine-readable check tag **before** the outcome prose. Do not roll dice yourself. Example: `[CHECK: AGILITY: 15 | REASON: leap the gap]`

The Fortress pipeline already sanitizes structured output. A new **Check Interceptor** runs after `validate_turn_schema`:

1. Parse `[CHECK: STAT: DC | REASON: …]` from `story_text` or a dedicated `mechanics` field.
2. Strip the tag from player-visible prose (or move it to metadata on the turn object).
3. Queue the check for engine resolution **before** the next turn is finalized.

If the model forgets a tag, gameplay continues as pure prose—RPG Mode degrades gracefully, never hard-crashes.

### Engine Resolution (Zero Extra VRAM)

Dice resolution is **pure Python**:

```
roll = random.randint(1, 20)  # or ruleset-specific dice
total = roll + stat + modifiers
success = total >= DC
```

The result is injected as a **hidden system message** on the next API call:

```
[MECHANICS RESOLVED]
Check: Agility vs DC 15
Roll: 14 + 2 (modifier) = 16
Outcome: SUCCESS
Instruction: Write the next paragraph assuming the character clears the gap. Do not contradict this outcome.
```

The player never sees the system message. They see:

1. Their action.
2. A brief dice overlay (see UI below).
3. AI prose that **must** honor the resolved outcome.

This pattern prevents the classic AI RPG failure mode: the model narrates success and failure in the same breath.

### UI: Dice Overlay in the Story Tab

When a check resolves, a **non-blocking overlay** appears on the active turn card:

*   Stat name and DC.
*   Animated die result (cosmetic—could be CSS-only, no GPU cost).
*   Success / Failure badge with color accessibility in mind (not red/green only).
*   Optional “Show math” expander for crunchy players.

The overlay dismisses automatically when the next turn loads. No modal traps. No second window.

### World Builder Integration

RPG cartridges gain a **Stats & Checks** sub-panel:

*   Toggle stats tracking per character.
*   Assign base stats and modifiers.
*   Define default DC bands for the adventure tone (horror = higher baseline tension).

Campaign’s **Chapter Outline** tab stays plot-focused. RPG Mode gets **Encounter Beats** (optional): suggested DC ranges per scene, not hard gates—preserving emergent play.

### Why It Works

| Concern | RPG Mode answer |
|---|---|
| VRAM | No second model. Dice math is local. |
| Latency | One extra system line in the *next* prompt—not a second full generation pass. |
| Architecture | Third mode cleanly separates concerns from Sandbox/Campaign. |
| Testing | Check parsing and resolution are unit-testable without an LLM. |

### Open Design Questions (to resolve during implementation)

*   Should critical success/failure (natural 20/1) be ruleset-dependent?
*   Should checks be logged in `memory.json` for RAG (“Sir Aldric failed the stealth check in Part 3”)?
*   Multi-character checks: which stat when the party acts together?

---

## 2. Tension Heatmap — Narrative Analytics

### The Problem Today

Authors and players have **no quantitative feedback on pacing**. RAG summaries tell you *what happened*, not *how it felt*. A fifty-turn stretch of low-stakes conversation reads fine turn-by-turn but kills a thriller. Users only notice when they export the novel and feel the sag.

### Core Concept

During existing **RAG compilation** (when the engine already asks the LLM to summarize a chunk), add **one additional structured question**:

> On a scale of 1–10, rate this chunk for:
> *   **Physical danger** (bodily harm, combat, environmental threat)
> *   **Emotional tension** (stakes, conflict, dread, relationship pressure)

Scores are stored as metadata—not injected into every turn prompt—so token cost stays negligible.

### Data Model: `pacing_ledger` in `memory.json`

```json
{
  "pacing_ledger": [
    {
      "chapter_number": 1,
      "part_index": 3,
      "start_turn": 21,
      "end_turn": 30,
      "physical_danger": 4,
      "emotional_tension": 7,
      "compiler_model": "optional audit field",
      "compiled_at": "ISO-8601 timestamp"
    }
  ]
}
```

**Integration with existing RAG:**

*   Compiled in the same background thread as Plot Ledger parts—**no new compile pass**.
*   Invalidated when timeline surgery affects the chapter (same rules as plot/chapter ledgers today).
*   Rebuilt via **Compile Missing History**—no separate maintenance workflow.

### UI: Analysis Tab

A new **Pacing** (or **Analytics**) tab in the Workspace:

*   **Line graph** with two series: Physical Danger (cool color) and Emotional Tension (warm color).
*   X-axis: turn number or chapter/part markers.
*   Hover tooltips: jump to that turn range in the Time Travel slider.
*   **Threshold guides**: optional horizontal bands (“recommended thriller band: tension ≥ 6 every 15 turns”).

This is read-only analytics. It never auto-writes prose or forces Director actions—avoiding the “AI knows better than you” trap.

### User Value Scenarios

| User type | How they use it |
|---|---|
| **Interactive fiction author** | Spot the “valley” before export; insert a confrontation or reveal. |
| **Campaign player** | Verify the AI is actually escalating toward chapter goals. |
| **Shared Universe maintainer** | Compare pacing profiles across threads in the same universe. |

### Why It Works

| Concern | Heatmap answer |
|---|---|
| VRAM | One extra JSON field per chunk during compile already hitting the LLM. |
| UX | Tab loads from disk; graph renders from cached ledger—no inference at open time. |
| Architecture | Extends RAG compiler, does not touch turn loop hot path. |
| Honesty | Scores are AI-estimated; UI should label them “compiler estimates,” not ground truth. |

### Open Design Questions

*   Should users be able to **manually override** a score after reading the chunk?
*   Export pacing charts to HTML storybook appendices?
*   Alert when both lines stay below N for M consecutive parts (gentle nudge, not popup spam)?

---

## 3. Party Management — Multi-POV Orchestration

### The Problem Today

`pov_character` in `setup.json` is **single-active-POV**. The Director dropdown allows **Force POV** as a one-off directive, but there is no persistent party roster, no quick switching, and no memory of who knows what from whose perspective.

Players running a “family of four” (Mage, Cleric, Rogue, Fighter) must manually remind the AI who is speaking every time they swap.

### Core Concept

Introduce a **`party_ledger`**: a structured roster of playable characters with portraits, voice tags (future TTS hook), and per-character RAG visibility rules. **One active POV** at a time; switching POV rewrites the effective system prompt slice—not the entire cartridge.

### Data Model

Stored in `setup.json` (or `party.json` if separation proves cleaner):

```json
{
  "party_ledger": [
    {
      "id": "elara_mage",
      "display_name": "Elara",
      "title": "Mage of the Silver Circle",
      "pov_voice": "first_person",
      "portrait": "assets/elara.png",
      "bio_short": "Cynical arcanist; afraid of deep water.",
      "default_location": "Party",
      "is_playable": true
    },
    {
      "id": "brother_marcus",
      "display_name": "Marcus",
      "title": "Itinerant Cleric",
      "pov_voice": "third_person_limited",
      "portrait": null,
      "bio_short": "Healer with a guilty past.",
      "is_playable": true
    }
  ],
  "active_pov_id": "elara_mage"
}
```

Entity RAG already tracks characters in `character_ledger`. Party members **link** to ledger entries by name or ID, reusing Universe Local/Global scope instead of duplicating lore.

### Engine Behavior on POV Switch

When the user clicks a portrait in the header:

1. Update `active_pov_id` in runtime state (persisted to `setup.json` or session state file).
2. Rebuild the **POV injection block** in `build_messages()`:

   ```
   ACTIVE POV: Elara the Mage (first person)
   Voice constraint: Write strictly from Elara's sensory perspective. Do not reveal other party members' private thoughts.
   Known to Elara: [subset of entity ledger filtered by POV knowledge rules — future refinement]
   ```

3. Set `pov_character` on the **next generated turn** to match; do not retroactively rewrite history.

Optional: record POV switches as low-noise events in the character ledger (“Elara took point in the catacombs, Turn 42”).

### UI: Party Strip in the Workspace Header

*   **Portrait chips** (or initials avatars when no image)—compact, horizontal strip near the story title.
*   Active POV: highlighted border + checkmark.
*   Click another member: confirm dialog if mid-scene (“Switch POV now? Next turn will use Marcus.”).
*   Long-press / right-click: quick bio tooltip from `bio_short`.

Campaign mode: party switching allowed unless a chapter goal explicitly locks POV (Director override).

Sandbox mode: fully free switching.

RPG Mode (future): each member’s stats block in `character_stats.json` keyed by `party_ledger.id`.

### Relationship to Shared Universes

Universe-global characters remain in **Global scope**. A party member who is also a universe NPC (e.g., recurring mentor) merges cleanly:

*   Global ledger supplies long-term lore.
*   Local party entry supplies **playable POV constraints** for this thread only.

This is the same Local Override pattern documented in [RAG.md](RAG.md)—extended from “entity stat override” to “who holds the camera.”

### Why It Works

| Concern | Party system answer |
|---|---|
| VRAM | Zero. Prompt text swap only. |
| UX | One-click POV vs. typing Force POV every time. |
| Architecture | Extends existing `pov_character` + entity ledger—not a parallel character system. |
| Future TTS | Each ledger entry’s `id` becomes the voice profile key (Feature 4). |

### Open Design Questions

*   Should inactive party members still receive **off-screen RAG updates** when mentioned in prose?
*   Split-party scenarios (two locations)—out of scope for v1 of this feature?
*   Co-op authoring: two humans alternating POV on one machine—workflow implications?

---

## 4. Voice of the Weaver — TTS Integration

### The Problem Today

TomeWeaver is **silent**. For many users, immersion jumps dramatically when prose is narrated—especially long export reads or slow, deliberate play styles. Image generation was deliberately **not** prioritized because it hogs VRAM and slows the loop. **Text-to-speech is the lighter sibling**: inference is smaller, can run on CPU, and can be entirely optional.

### Core Concept

Add **per-turn audio playback**: a Play button on each turn card (and optionally on Narrative Bridges) that reads `story_text` aloud using a user-configured TTS backend.

### Backend Strategy (User-Selectable)

| Backend | Tradeoff | Best for |
|---|---|---|
| **Piper / Kokoro (local)** | Free, private, CPU-friendly; voice quality varies | Offline players, low GPU headroom |
| **ElevenLabs (cloud)** | High quality, voice cloning; API cost + network | Audiobook-grade immersion |
| **System TTS (OS native)** | Zero setup fallback | Accessibility, quick tests |

**Critical rule:** TTS loads **lazily**. The LLM that generates story text must never wait on TTS initialization. Audio generation runs in a worker thread after the card is displayed.

### Configuration (`engine_config.json` extension)

```json
{
  "tts_enabled": false,
  "tts_provider": "piper",
  "tts_voice_id": "en_GB-alan-medium",
  "tts_auto_play": false,
  "tts_narrate_bridges": true,
  "elevenlabs_api_key": ""
}
```

Per-cartridge overrides in `setup.json`:

```json
{
  "tts_voice_profile": "gritty_narrator",
  "tts_read_pov_character": true
}
```

Party ledger (Feature 3) can map each character to a distinct voice for **dialogue lines** in a later phase; v1 focuses on **narrator reads full turn prose**.

### UI Behavior

*   **▶ Play / ⏸ Pause** on each turn card footer.
*   Global Settings: provider, voice picker (preview button), auto-play toggle.
*   **Cache audio** to `{adv_dir}/.tts_cache/turn_{n}.wav` so re-reading old turns does not re-synthesize.
*   Visual indicator when cache miss triggers generation (spinner on button only—not full-screen loader).

### Engine Integration

*   **No change to LLM prompts** in v1.
*   Optional future: `[SPEAKER: Elara]` tags in dialogue-heavy RPG Mode for multi-voice reads.
*   Export pipeline: optional “Generate audiobook chapter” batch job—post-export, not inline with gameplay.

### Accessibility & UX Notes

*   TTS benefits low-vision players and users who process audio better than wall-of-text UI.
*   Always provide **text first**; audio is enhancement, not replacement.
*   Respect mute: master volume in Settings + per-session mute hotkey.

### Why It Works

| Concern | TTS answer |
|---|---|
| VRAM | Local Piper/Kokoro runs CPU-side; does not compete with LLM GPU memory. |
| Latency | Async generation; gameplay never blocked. |
| Architecture | Orthogonal module—disable entirely with `tts_enabled: false`. |
| Value | Transforms long sessions into “premium audiobook” feel without image-gen bloat. |

### Open Design Questions

*   Ship Piper voices in-repo vs. download-on-first-use?
*   Legal/commercial voice cloning policies for ElevenLabs in Polyform Non-Commercial context?
*   Bridge prose: same narrator voice or softer “transition” profile?

---

## Explicitly Out of Scope (For Now)

To protect the v1.0 stabilization goal and the VRAM/UX budget, the following are **not** on this roadmap:

*   **In-engine image / comic panel generation** — competes with LLM for GPU memory; slow; inconsistent with prose-first identity.
*   **Real-time multiplayer / cloud sync** — state lives local by design ([Known Limitations](../README.md)).
*   **Autonomous AI agents debating plot** — multi-agent loops multiply token cost and failure modes.
*   **Full tactical combat grids** — belongs in dedicated RPG tools; RPG Mode targets narrative checks, not XCOM.

Revisiting these is possible **only** if they can be isolated optional processes—not bundled into the core turn loop.

---

## Suggested Implementation Phases

Phases assume **v1.0 stabilization ships first**. Order balances dependency chains and user-visible wins.

### Phase A — Foundation (post-v1.0)

1. Expand automated tests for any new interceptors (`[CHECK: …]` parser, pacing JSON schema).
2. Party ledger schema + header UI (read-only portraits, POV switch prompt injection).
3. TTS module skeleton: Play button, Piper local, disk cache—no auto-play yet.

### Phase B — Gameplay Depth

4. RPG Mode cartridge template + `character_stats.json` + dice overlay.
5. Tension Heatmap: compiler question + Pacing tab graph.
6. TTS provider plugins (ElevenLabs, system fallback).

### Phase C — Polish & Cross-Feature Glue

7. RPG checks logged into RAG event history.
8. Party member → TTS voice mapping.
9. Export appendices: pacing chart embed, optional audiobook batch.

---

## How to Influence This Roadmap

TomeWeaver is open to community direction **after** stability gates are met. If you are building on the engine:

*   **Stabilization first:** PRs that fix bugs, add tests, or improve Known Limitations beat feature creep.
*   **Design proposals:** Open a GitHub Discussion referencing this document with: user story, VRAM impact, and whether the feature belongs in Sandbox, Campaign, RPG, or global.
*   **Plugin boundaries:** Features that can live as optional modules (TTS, analytics tab) are easier to merge than core turn-loop rewrites.

---

## Summary Table

| Feature | Mode impact | VRAM / perf | Primary subsystem extended | Design note |
|---|---|---|---|---|
| **RPG Mode** | New third mode | None (local dice) | Fortress interceptor + new stats file | **Deterministic resolution** — the LLM proposes checks and narrates outcomes; the engine adjudicates rolls in Python |
| **Tension Heatmap** | All modes | +1 compile question per chunk | RAG compiler + new Analytics tab | Compiler-estimated pacing; read-only analytics |
| **Party Management** | All modes | None (prompt swap) | `setup.json` + header UI + POV block | Reuses entity ledger / Universe scope |
| **TTS Integration** | All modes (optional) | CPU or cloud; lazy load | Turn card UI + cache dir | Optional immersion layer; never blocks the turn loop |

### The Hybrid Engine Thesis

Much of the AI community is focused on **agentic** workflows—the model “thinks,” then “acts,” then “reflects,” often in the same pipeline. That pattern is powerful for open-ended agents, but it is a poor fit for fair mechanical adjudication: users cannot audit a dice roll that only existed inside the model’s hidden reasoning.

RPG Mode deliberately splits the labor:

*   **AI creativity** — prose, scene framing, when a check is warranted, and how success or failure *feels*.
*   **Code reliability** — deterministic Python logic for rolls, modifiers, and pass/fail outcomes fed back as explicit system facts.

That makes TomeWeaver a **hybrid engine**: not a chatbot pretending to be a game master, and not a rigid rules simulator with no soul—both layers doing what each does best.

---

**TomeWeaver** — *Play the game. Export the novel.*  
*The roadmap above is the path from a hardened v1.0 to a richer narrative IDE—without becoming the bloated “everything app” that breaks on real hardware.*
