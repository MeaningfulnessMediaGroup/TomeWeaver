"""
TomeWeaver: Story Exporter Module
---------------------------------
Compiles the chronological game ledger (history.json) into a human-readable 
novel format (TXT, MD, or HTML). If 'narrative bridges' have been generated, 
this module acts as a compiler, applying the surgical prose patches to 
create a seamless reading experience.
"""

import html
import re

# ---------------------------------------------------------
# EXPORTER COMPILER
# ---------------------------------------------------------

def export_story(adv_dir, setup_data, history, chapters, export_type):
    """
    Exports the adventure history into a readable format.
    Includes player choices as narrative bridges, while filtering out 
    mechanical UI choices (like 'Start Chapter' or 'Restart').
    """
    title = setup_data.get("title", "The Adventure")
    # Clean title for filename compatibility
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    
    # List of mechanical choices that should NOT appear in a narrative book
    ui_commands = [
        "Start Chapter:", "Conclude the Story", "Restart", 
        "Export", "Undo", "Quit", "Cheat Death"
    ]

    # --- 1. COMPILE NARRATIVE BEATS ---
    chapter_content = []
    for c in chapters:
        if c["start_turn"] is None: continue 
        end = c["end_turn"] if c.get("end_turn") is not None else len(history)
        
        c_beats = []
        for i, t in enumerate(history):
            if c["start_turn"] <= t["turn"] <= end:
                
                story_text = t.get("story_text", "")
                bridge = t.get("narrative_bridge")
                
                # Apply Intro Patch (if previous turn generated a bridge)
                if bridge and bridge.get("intro_patch"):
                    patch = bridge["intro_patch"]
                    if story_text.strip().startswith(patch["remove"]) and patch["remove"]:
                        story_text = patch["replace"] + story_text.lstrip()[len(patch["remove"]):]

                # Add the AI's story text paragraphs
                if story_text:
                    paragraphs = [p.strip() for p in story_text.replace("\\n", "\n").split('\n') if p.strip()]
                    for p in paragraphs:
                        c_beats.append({"type": "story", "text": p})
                
                # Look ahead to the next turn to check for an Outro Patch and Action Bridge
                choice = t.get("player_choice")
                if choice and not any(ui in str(choice) for ui in ui_commands):
                    
                    next_bridge = None
                    if i + 1 < len(history):
                        next_bridge = history[i+1].get("narrative_bridge")
                        
                    # If the AI generated a seamless prose bridge
                    if next_bridge and next_bridge.get("action_text"):
                        # Apply Outro Patch to the LAST story beat we just added
                        patch = next_bridge.get("outro_patch")
                        if patch and c_beats and c_beats[-1]["text"].endswith(patch["remove"]) and patch["remove"]:
                            c_beats[-1]["text"] = c_beats[-1]["text"].rstrip()[:-len(patch["remove"])] + patch["replace"]
                        
                        # Add the seamless Action Bridge
                        c_beats.append({"type": "action", "text": next_bridge["action_text"]})
                        
                    # Fallback to the classic "Game Log" bracketed format
                    else:
                        c_beats.append({"type": "action", "text": f"[ {choice} ]"})
        
        chapter_content.append({
            "num": c["chapter_number"], 
            "title": c["title"], 
            "beats": c_beats
        })

    # ---------------------------------------------------------
    # 2. FORMAT AND WRITE TO DISK
    # ---------------------------------------------------------

    # --- EXPORT FORMATTING: TEXT ---
    if export_type == 1: 
        ext = ".txt"
        lines = [f"===============\n-==   {title}   ==-\n===============\n"]
        for c in chapter_content:
            lines.extend([f"Chapter {c['num']}: {c['title']}", "-" * 10])
            for beat in c['beats']:
                if beat["type"] == "action":
                    lines.append(f"\n{beat['text']}\n") if "narrative_bridge" in history[0] else lines.append(f"\n[ {beat['text']} ]\n")
                else:
                    lines.append(beat["text"] + "\n")
            lines.append("\n")
        output = "\n".join(lines)
        
    # --- EXPORT FORMATTING: MARKDOWN ---
    elif export_type == 2:  
        ext = ".md"
        lines = [f"# {title}\n"]
        for c in chapter_content:
            lines.append(f"## Chapter {c['num']}: {c['title']}\n")
            for beat in c['beats']:
                if beat["type"] == "action":
                    # Bold Italic centered-look for the action bridge
                    lines.append(f"\n*** {beat['text']} ***\n\n")
                else:
                    lines.append(beat["text"] + "\n\n")
        output = "\n".join(lines)
        
    # --- EXPORT FORMATTING: HTML ---
    elif export_type == 3:  
        ext = ".html"
        html_parts = [
            f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><title>{html.escape(title)}</title>",
            "<style>",
            "body{max-width:800px;margin:40px auto;font-family:'Georgia',serif;line-height:1.8;padding:0 20px;color:#222;}",
            "h1{text-align:center;border-bottom:2px solid #222;padding-bottom:10px;}",
            ".toc{background:#f9f9f9;padding:20px;border-radius:8px;margin-bottom:40px;}",
            "p{text-indent:1.5em;margin-bottom:15px;text-align:justify;}",
            ".action{text-align:center;font-style:italic;font-weight:bold;margin:30px 0;color:#555;}",
            ".action::before, .action::after { content: ' — '; }",
            "</style></head><body>",
            f"<h1>{html.escape(title)}</h1>"
        ]
        
        # Add Table of Contents
        if len(chapter_content) > 1:
            html_parts.append("<div class=\"toc\"><h3>Table of Contents</h3><ul>")
            html_parts.extend([f"<li><a href=\"#chapter-{c['num']}\">Chapter {c['num']}: {html.escape(c['title'])}</a></li>" for c in chapter_content])
            html_parts.append("</ul></div>")
            
        for c in chapter_content:
            html_parts.append(f"<h2 id=\"chapter-{c['num']}\">Chapter {c['num']}: {html.escape(c['title'])}</h2>")
            for beat in c['beats']:
                if beat["type"] == "action":
                    html_parts.append(f"<div class=\"action\">{html.escape(beat['text'])}</div>")
                else:
                    html_parts.append(f"<p>{html.escape(beat['text'])}</p>")
        
        html_parts.append("</body></html>")
        output = "\n".join(html_parts)
        
    file_path = adv_dir / f"{safe_title}{ext}"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(output)
    return file_path