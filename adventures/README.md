# 📚 TomeWeaver Adventures

This directory is the "Cartridge Slot" for TomeWeaver. Every folder inside here represents a unique, isolated story world containing its own configurations, characters, and save data.

We have included two sample adventures to demonstrate the flexibility of the dual-mode engine.

---

## 🐈 Mallow the Cat (Sandbox Mode)

**Mode:** Sandbox | **Tone:** Whimsical, Comedic, Cozy | **Mortality:** Disabled

**Overview:** 
You are Mallow, a slightly overweight, highly judgmental marshmallow-white ragdoll cat. Your kingdom is the eccentric Hawthorne Estate. 

**Why play this sample?**
This adventure demonstrates the power of **Sandbox Mode**. There is no strict plot outline and no automatic chapter progression. It showcases how the engine handles persistent world simulation, custom AI directives, and open-ended "What if?" exploration. Try using the `chapter` command to manually time-jump or change scenes when you get bored of the Sitting Room!

---

## 💀 The Tomb of the Sunken King (Campaign Mode)

**Mode:** Campaign | **Tone:** Dark Fantasy, Gritty, Tense | **Mortality:** Enabled

**Overview:** 
You are Kaelen, a mortal thief attempting to break into a cursed, ancient ruin to steal a legendary artifact. You must rely on your wits and the items in your backpack to survive.

**Why play this sample?**
This adventure demonstrates the strict logic of **Campaign Mode**. It utilizes a predefined `plot_outline` with specific goals and obstacles. You will see the AI meticulously track your inventory (Rope, Dagger, Torch) and use "Chain of Thought" reasoning to verify if you have met the active chapter goal before allowing you to progress. Be careful: mortality is enabled, meaning the AI is allowed to kill you if you make a fatal mistake.

---

## 🚀 How to Play

To launch either of these adventures, use the desktop shortcuts generated in the root TomeWeaver directory:

1. Double-click **`Story - Mallow the Cat.bat`**
2. Or double-click **`Story - The Tomb of the Sunken King.bat`**

*(Mac/Linux users: Run `python scripts/tome_weaver.py` to open the Main Menu and select your story from the list).*

---

## 🏗️ Creating Your Own

To start a brand new adventure, you **do not** need to create folders manually. 

1. Double-click the **`Start_TomeWeaver.bat`** file in the root folder.
2. Select **[Start a New Story]** from the menu.
3. Type your title. 

The engine will automatically generate the folder here, create a brand new `.bat` shortcut for your desktop, and build the boilerplate `setup.json` so you can start world-building immediately!