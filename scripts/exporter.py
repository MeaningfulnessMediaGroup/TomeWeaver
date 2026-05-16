import html
import re

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

    chapter_content = []
    for c in chapters:
        if c["start_turn"] is None: continue 
        end = c["end_turn"] if c.get("end_turn") is not None else len(history)
        
        c_beats = []
        for t in history:
            if c["start_turn"] <= t["turn"] <= end:
                # 1. Add the AI's story text
                if t.get("story_text"):
                    paragraphs = [p.strip() for p in t["story_text"].replace("\\n", "\n").split('\n') if p.strip()]
                    for p in paragraphs:
                        c_beats.append({"type": "story", "text": p})
                
                # 2. Add the Player's choice as a narrative bridge
                choice = t.get("player_choice")
                if choice and not any(ui in str(choice) for ui in ui_commands):
                    c_beats.append({"type": "action", "text": choice})
        
        chapter_content.append({
            "num": c["chapter_number"], 
            "title": c["title"], 
            "beats": c_beats
        })

    # --- EXPORT FORMATTING: TEXT ---
    if export_type == 1: 
        ext = ".txt"
        lines = [f"===============\n-==   {title}   ==-\n===============\n"]
        for c in chapter_content:
            lines.extend([f"Chapter {c['num']}: {c['title']}", "-" * 10])
            for beat in c['beats']:
                if beat["type"] == "action":
                    lines.append(f"\n[ {beat['text']} ]\n")
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