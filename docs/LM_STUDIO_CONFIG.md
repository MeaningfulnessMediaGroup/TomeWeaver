# LM Studio: Setup & Model Recommendations

TomeWeaver is designed to be played entirely locally, offline, and for free. To do this, we highly recommend using **LM Studio**, a powerful desktop application that runs Large Language Models (LLMs) on your own hardware and serves them through an OpenAI-compatible API.

This guide will show you how to configure LM Studio to work flawlessly with TomeWeaver, and which models yield the best results.

---

## 🛠️ Configuring LM Studio

1. **Download and Install:** Get the latest version from [lmstudio.ai](https://lmstudio.ai/).
2. **Download a Model:** Use the search bar to find and download a model (see our recommendations below).
3. **Open the Local Server:** On the left-hand sidebar, click the **Local Server** icon (it looks like a double-ended arrow `<->`).
4. **Load the Model:** At the top of the screen, select your downloaded model from the dropdown to load it into your RAM/VRAM.

### ⚠️ CRITICAL: Adjusting the Context Length
TomeWeaver sends massive amounts of data (World Lore, Character Bibles, and Recent History) to the AI every turn to ensure the story stays consistent. If your Context Length is too small, the engine will crash with an `Error 400: Bad Request`.

1. On the right-hand panel in the Local Server tab, look for **Hardware Settings** or **Context Length** (`n_ctx`).
2. By default, LM Studio often sets this to `8192`. 
3. **Change this to `32768`** (32K) or higher. 
4. *Note: Increasing context length uses more RAM/VRAM. If your computer runs out of memory, you may need to download a smaller model or lower the `context_window` setting in TomeWeaver's Global Settings.*

**Rule of thumb:** TomeWeaver's `context_window` (recent turns injected raw) plus RAG memory plus world lore must fit inside LM Studio's `n_ctx`. If you see HTTP 400 errors, raise `n_ctx` first; if VRAM maxes out, lower TomeWeaver's `context_window` or `memory_decay_threshold` instead.

### Start the Server
1. Ensure the **Server Port** is set to `1234` (This is TomeWeaver's default).
2. Enable **CORS** (Cross-Origin Resource Sharing) in the settings.
3. Click the green **Start Server** button. 
4. You can now launch TomeWeaver and begin generating!

### Linking LM Studio to TomeWeaver
1. Open TomeWeaver → Dashboard → **⚙ Settings**.
2. Set **Active API Profile** to `LM_Studio` (or create a custom profile pointing to `http://localhost:1234/v1/chat/completions`).
3. Ensure **Model** matches the identifier shown in LM Studio's server tab (often `loaded-model` for local servers).
4. Align **Context Window** in TomeWeaver Global Settings with your LM Studio `n_ctx` (see rule of thumb above).

---

## 🧠 Curated Model Recommendations

TomeWeaver requires models that are highly creative (for storytelling) but extremely disciplined (they MUST follow strict JSON schemas without breaking). 

Not all models are good at this. Here is our curated list of models, categorized by the hardware required to run them comfortably.

### Tier 1: The "Sweet Spot" (8GB - 12GB VRAM)
If you have a modern gaming graphics card (like an RTX 3060, 4060, or equivalent Mac M-series), these models offer the best balance of speed, creativity, and JSON discipline.

*   🏆 **Hermes 2 Pro - Llama-3 8B** *(NousResearch)*
    *   *Why we love it:* Hermes 2 Pro was explicitly trained on JSON schema formatting and function calling. It is incredibly obedient to TomeWeaver's internal engine rules while still writing rich, vivid prose. It rarely hallucinates syntax errors.
*   **Mistral Nemo 12B Instruct** *(Mistral AI)*
    *   *Why we love it:* It features a massive 128k native context window, meaning it practically never forgets details in long campaigns. Its prose is highly atmospheric.
*   **Prototype-X 12B** *(Various / Community Merge)*
    *   *Why we love it:* It is fully uncensored and unrestricted. If you are writing gritty cyberpunk, dark fantasy, or mature horror, mainstream models will sometimes refuse to generate violent or illicit scenes, breaking the game loop. Prototype-X never flinches and delivers raw, unrestricted storytelling.
	
### Tier 2: The "Heavyweights" (16GB - 24GB+ VRAM)
If you have a high-end setup (RTX 3090, 4090, or Mac Studio), you can run larger models that rival paid cloud APIs in reasoning and storytelling depth.

*   🏆 **Qwen2.5 32B Instruct** *(Qwen)*
    *   *Why we love it:* Qwen2.5 is currently one of the smartest open-weight models on the planet for logic and coding. It follows the Campaign Goal checklists flawlessly and writes highly detailed, intelligent plot progressions.
*   **Meta Llama 3.1 70B Instruct (Quantized)** *(Meta)*
    *   *Why we love it:* If you can fit a heavily compressed (Q4 or Q3) version of this model into your VRAM, it offers near GPT-4 levels of storytelling and character consistency.

### Tier 3: The "Lightweights" (Under 8GB VRAM / CPU Only)
If you are running on an older laptop or strictly using CPU RAM, you need heavily compressed, fast models.

*   **Meta Llama 3.1 8B Instruct** *(Meta)*
    *   *Why we love it:* It is fast, lightweight, and punches far above its weight class in storytelling. Note: You may occasionally experience JSON formatting errors with smaller models, but TomeWeaver's "Fortress" auto-healer will automatically catch and retry them for you.
*   **Qwen2.5 7B Instruct** *(Qwen)*
    *   *Why we love it:* Extremely fast and highly disciplined at following formatting rules. 

---

## 💡 Pro-Tips for Local Generation

*   **Watch the Developer Console:** In TomeWeaver's workspace, open the Developer Console tab. If you see the engine constantly applying "JSON Surgery" or retrying, the model you chose might be struggling with the schema. Try switching to a different model (like Hermes Pro).
*   **GPU Offload:** In LM Studio, make sure you enable **GPU Offload** and set it to "Max" (or input your layer count) to ensure the model runs on your graphics card instead of your CPU. It will be 10x to 20x faster.
*   **Disable `auto_polish` for local play** unless you have headroom— it doubles generation time and token load every turn.
*   **Quantization trade-offs:** Heavily quantized 70B models may follow JSON schemas poorly despite strong prose; prefer Hermes/Qwen tiers if you see frequent Fortress retries.

---

## ⚠️ Known Limitations (Local Inference)

*   **VRAM is the hard ceiling.** There is no software workaround if `n_ctx × model size` exceeds available GPU/RAM—you must shrink context, use a smaller quant, or switch models.
*   **CPU-only inference** is supported but turn generation may take minutes per response on long prompts; Auto-Play and Auto Narrative Bridge become impractical.
*   **Model refusals** on uncensored content vary by base model even when "uncensored merges" exist—Prototype-X tier models are recommended for mature themes.
*   **LM Studio must stay running** while TomeWeaver plays; closing the server mid-turn causes connection errors (recovered gracefully, but the turn may need a redo).
*   **Mac Apple Silicon** users should verify Metal GPU offload is active; otherwise context 32K+ may be unusably slow.
*   **TomeWeaver cannot raise LM Studio's `n_ctx` for you**— mismatched settings must be fixed manually in both apps.

See the full **Known Limitations** list in the [root README](../README.md).