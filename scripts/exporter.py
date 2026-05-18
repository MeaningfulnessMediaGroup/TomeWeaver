"""
TomeWeaver: Story Exporter Module
---------------------------------
Compiles the chronological game ledger (history.json) into a human-readable 
novel format (TXT, MD, or HTML). Weaves player choices into seamless prose 
using AI-generated string bridges. Includes a Debug Mode to print both actions and bridges.
"""

import html
import re
from config import ENGINE_CONFIG

def export_story(adv_dir, setup_data, history, chapters, export_type, use_novelization=True, custom_path=None):
    title = setup_data.get("title", "The Adventure")
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    
    ui_commands = ["Start Chapter:", "Conclude the Story", "Restart", "Export", "Undo", "Quit", "Cheat Death"]

    # --- 1. COMPILE NARRATIVE BEATS ---
    chapter_content = []
    for c in chapters:
        if c.get("start_turn") is None: continue 
        
        end = c["end_turn"] if c.get("end_turn") is not None else len(history)
        
        c_beats = []
        for i, t in enumerate(history):
            if c["start_turn"] <= t["turn"] <= end:
                
                # Add the AI's story text paragraphs
                story_text = t.get("story_text", "")
                if story_text:
                    paragraphs = [p.strip() for p in story_text.replace("\\n", "\n").split('\n') if p.strip()]
                    for p in paragraphs:
                        c_beats.append({"type": "story", "text": p})
                
                # Handle the transition to the next turn
                choice = t.get("player_choice")
                if choice and not any(ui in str(choice) for ui in ui_commands):
                    
                    next_bridge = None
                    if use_novelization and i + 1 < len(history) and "narrative_bridge" in history[i+1]:
                        next_bridge = history[i+1]["narrative_bridge"]
                        
                        # NORMAL NOVELIZED MODE: Show only the generated bridge
                        if next_bridge and next_bridge not in ["[OK]", "[FAILED]"]:
                            c_beats.append({"type": "bridge", "text": next_bridge.strip()})
                        # If [OK], [FAILED], or empty, do nothing
                    else:
                        # Interactive Mode / Un-novelized fallback: Show the raw player action
                        c_beats.append({"type": "choice", "text": str(choice)})
        
        if c_beats:
            chapter_content.append({"num": c["chapter_number"], "title": c["title"], "beats": c_beats})

    # --- 2. FILE FORMATTING (TXT, MD, HTML) ---
    if export_type == 1: 
        ext = ".txt"
        lines = [f"===============\n-==   {title}   ==-\n===============\n"]
        for c in chapter_content:
            lines.extend([f"Chapter {c['num']}: {c['title']}", "-" * 10])
            for beat in c['beats']:
                if beat["type"] == "choice": lines.append(f"\n[ Action: {beat['text']} ]\n")
                elif beat["type"] == "bridge": lines.append(f"\n{beat['text']}\n")
                else: lines.append(beat["text"] + "\n")
            lines.append("\n")
        output = "\n".join(lines)
        
    elif export_type == 2:  
        ext = ".md"
        lines = [f"# {title}\n"]
        for c in chapter_content:
            lines.append(f"## Chapter {c['num']}: {c['title']}\n")
            for beat in c['beats']:
                if beat["type"] == "choice": lines.append(f"\n**[ Action: {beat['text']} ]**\n\n")
                elif beat["type"] == "bridge": lines.append(f"*{beat['text']}*\n\n")
                else: lines.append(beat["text"] + "\n\n")
        output = "\n".join(lines)
        
    elif export_type == 3:  
        ext = ".html"
        html_parts = [
            f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><title>{html.escape(title)}</title>",
            "<style>",
            "body{max-width:800px;margin:40px auto;font-family:'Georgia',serif;line-height:1.8;padding:0 20px;color:#222;}",
            "h1{text-align:center;border-bottom:2px solid #222;padding-bottom:10px;}",
            ".toc{background:#f9f9f9;padding:20px;border-radius:8px;margin-bottom:40px;}",
            "p{text-indent:1.5em;margin-bottom:15px;text-align:justify;}",
            ".choice{text-align:center;font-weight:bold;margin:30px 0;color:#555;}",
            ".bridge{font-style:italic;margin-bottom:15px;text-indent:1.5em;color:#1e40af;}",
            "</style></head><body>",
            f"<h1>{html.escape(title)}</h1>"
        ]
        
        if len(chapter_content) > 1:
            html_parts.append("<div class=\"toc\"><h3>Table of Contents</h3><ul>")
            html_parts.extend([f"<li><a href=\"#chapter-{c['num']}\">Chapter {c['num']}: {html.escape(c['title'])}</a></li>" for c in chapter_content])
            html_parts.append("</ul></div>")
            
        for c in chapter_content:
            html_parts.append(f"<h2 id=\"chapter-{c['num']}\">Chapter {c['num']}: {html.escape(c['title'])}</h2>")
            for beat in c['beats']:
                if beat["type"] == "choice": html_parts.append(f"<div class=\"choice\">[ Action: {html.escape(beat['text'])} ]</div>")
                elif beat["type"] == "bridge": html_parts.append(f"<p class=\"bridge\">{html.escape(beat['text'])}</p>")
                else: html_parts.append(f"<p>{html.escape(beat['text'])}</p>")
        
        html_parts.append("</body></html>")
        output = "\n".join(html_parts)
        
    # Use custom path if provided (from the Save Dialog), otherwise default to adventure folder
    file_path = custom_path if custom_path else adv_dir / f"{safe_title}{ext}"
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(output)
    return file_path