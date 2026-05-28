"""Central Master Clock: keep history turn numbers and chapter bounds in sync."""

from __future__ import annotations


def coerce_turn(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def history_turn_numbers(history):
    return [coerce_turn(t.get("turn", idx), idx) for idx, t in enumerate(history or [])]


def max_history_turn(history):
    nums = history_turn_numbers(history)
    return max(nums) if nums else 0


def _remap_bound(value, turn_map):
    if value is None:
        return None
    try:
        key = int(value)
    except (TypeError, ValueError):
        return value
    return turn_map.get(key, key)


def _shift_bound_gte(value, pivot, delta):
    if value is None:
        return None
    try:
        num = int(value)
    except (TypeError, ValueError):
        return value
    if num >= pivot:
        return num + delta
    return num


def build_sequential_turn_map(history):
    """Map each distinct old turn number to its post-resync value (by first card index)."""
    if not history:
        return {}
    before = history_turn_numbers(history)
    anchor = before[0]
    turn_map = {}
    for idx, old in enumerate(before):
        new = anchor + idx
        if old not in turn_map:
            turn_map[old] = new
    return turn_map


def renumber_history_contiguous(history):
    """Force history cards to sequential turns from the first card's anchor."""
    if not history:
        return False
    before = history_turn_numbers(history)
    anchor = before[0]
    changed = False
    for idx, turn in enumerate(history):
        expected = anchor + idx
        if coerce_turn(turn.get("turn"), expected) != expected:
            turn["turn"] = expected
            changed = True
    return changed


def apply_turn_map_to_chapters(chapters, turn_map):
    for chapter in chapters:
        chapter["start_turn"] = _remap_bound(chapter.get("start_turn"), turn_map)
        chapter["end_turn"] = _remap_bound(chapter.get("end_turn"), turn_map)


def apply_turn_map_to_memory(memory, turn_map):
    if not memory or not turn_map:
        return

    for entry in memory.get("plot_ledger", []) or []:
        if isinstance(entry, dict):
            entry["start_turn"] = _remap_bound(entry.get("start_turn"), turn_map)
            entry["end_turn"] = _remap_bound(entry.get("end_turn"), turn_map)

    for ledger_key in ("character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"):
        ledger = memory.get(ledger_key, {})
        if not isinstance(ledger, dict):
            continue
        for scope in ("local", "global"):
            bucket = ledger.get(scope, {})
            if not isinstance(bucket, dict):
                continue
            for data in bucket.values():
                if isinstance(data, dict) and "last_seen_turn" in data:
                    data["last_seen_turn"] = _remap_bound(data.get("last_seen_turn"), turn_map)

    for state in (memory.get("global_states") or {}).values():
        if isinstance(state, dict) and "last_seen_turn" in state:
            state["last_seen_turn"] = _remap_bound(state.get("last_seen_turn"), turn_map)


def apply_turn_map(history, chapters, memory, turn_map):
    """Apply an old->new turn map to chapters and memory ledgers (history already updated)."""
    if not turn_map:
        return
    apply_turn_map_to_chapters(chapters, turn_map)
    apply_turn_map_to_memory(memory, turn_map)


def clamp_chapter_bounds_to_history(history, chapters):
    """Snap chapter bounds to valid Master Clock turns when refs drifted out of sync."""
    if not history:
        return False
    turns = history_turn_numbers(history)
    turn_set = set(turns)
    max_turn = max(turns)
    changed = False

    for chapter in chapters or []:
        start = chapter.get("start_turn")
        end = chapter.get("end_turn")

        if start is not None:
            start_val = coerce_turn(start)
            if start_val not in turn_set:
                replacement = next((t for t in turns if t >= start_val), turns[-1])
                if start_val != replacement:
                    chapter["start_turn"] = replacement
                    changed = True
                    start_val = replacement

        if end is not None:
            end_val = coerce_turn(end)
            if end_val > max_turn:
                chapter["end_turn"] = max_turn
                changed = True
            elif end_val not in turn_set:
                replacement = next((t for t in reversed(turns) if t <= end_val), turns[0])
                if end_val != replacement:
                    chapter["end_turn"] = replacement
                    changed = True

        start = chapter.get("start_turn")
        end = chapter.get("end_turn")
        if start is not None and end is not None:
            if coerce_turn(end) < coerce_turn(start):
                chapter["end_turn"] = coerce_turn(start)
                changed = True

    return changed


def resync_timeline(history, chapters, memory):
    """Renumber history sequentially and remap every chapter/ledger reference."""
    if not history:
        return False
    turn_map = build_sequential_turn_map(history)
    changed = renumber_history_contiguous(history)
    if turn_map:
        apply_turn_map(history, chapters, memory, turn_map)
        changed = True
    if clamp_chapter_bounds_to_history(history, chapters):
        changed = True
    return changed


def shift_timeline_right(history, chapters, memory, pivot_turn, amount=1):
    """Open a gap at ``pivot_turn``: cards and bounds at/after pivot shift up."""
    if amount <= 0:
        return set()

    pivot = coerce_turn(pivot_turn)
    for turn in history:
        if coerce_turn(turn.get("turn")) >= pivot:
            turn["turn"] = coerce_turn(turn.get("turn")) + amount

    affected = chapters_intersecting_range(chapters, pivot, pivot + amount - 1)

    for chapter in chapters:
        chapter["start_turn"] = _shift_bound_gte(chapter.get("start_turn"), pivot, amount)
        chapter["end_turn"] = _shift_bound_gte(chapter.get("end_turn"), pivot, amount)

    for entry in (memory or {}).get("plot_ledger", []) or []:
        if isinstance(entry, dict):
            entry["start_turn"] = _shift_bound_gte(entry.get("start_turn"), pivot, amount)
            entry["end_turn"] = _shift_bound_gte(entry.get("end_turn"), pivot, amount)

    _shift_entity_last_seen(memory, pivot, amount)
    return affected


def shift_timeline_left_after_delete(history, chapters, memory, deleted_turn, *, has_successor):
    """Close a gap after removing ``deleted_turn`` (history turns already decremented)."""
    deleted = coerce_turn(deleted_turn)
    affected = chapters_intersecting_range(chapters, deleted, deleted)

    for chapter in chapters:
        s_turn = chapter.get("start_turn")
        e_turn = chapter.get("end_turn")

        if s_turn == deleted:
            chapter["start_turn"] = deleted if has_successor else None
        elif s_turn is not None and coerce_turn(s_turn) > deleted:
            chapter["start_turn"] = coerce_turn(s_turn) - 1

        if e_turn is not None and coerce_turn(e_turn) >= deleted:
            if coerce_turn(e_turn) == deleted and coerce_turn(s_turn) == deleted:
                chapter["end_turn"] = None
                chapter["start_turn"] = None
            else:
                chapter["end_turn"] = coerce_turn(e_turn) - 1

    for entry in (memory or {}).get("plot_ledger", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("start_turn") is not None and coerce_turn(entry["start_turn"]) > deleted:
            entry["start_turn"] = coerce_turn(entry["start_turn"]) - 1
        if entry.get("end_turn") is not None and coerce_turn(entry["end_turn"]) >= deleted:
            entry["end_turn"] = coerce_turn(entry["end_turn"]) - 1

    _shift_entity_last_seen(memory, deleted + 1, -1, strict_gt=True)
    return affected


def decrement_history_turns_after(history, start_index):
    """Left-shift Master Clock on history cards from ``start_index`` onward."""
    for idx in range(start_index, len(history)):
        history[idx]["turn"] = coerce_turn(history[idx].get("turn")) - 1


def chapters_intersecting_range(chapters, range_start, range_end):
    """Chapter numbers whose bounds overlap the inclusive turn range."""
    affected = set()
    for chapter in chapters or []:
        s_turn = chapter.get("start_turn")
        e_turn = chapter.get("end_turn")
        if s_turn is None:
            continue
        s_val = coerce_turn(s_turn)
        e_val = coerce_turn(e_turn) if e_turn is not None else None
        if e_val is not None:
            if s_val <= range_end and e_val >= range_start:
                affected.add(chapter.get("chapter_number"))
        elif s_val <= range_end:
            affected.add(chapter.get("chapter_number"))
    return affected


def invalidate_plot_ledgers(memory, affected_chapter_numbers):
    if not memory or not affected_chapter_numbers:
        return
    nums = set(affected_chapter_numbers)
    memory["plot_ledger"] = [
        p for p in memory.get("plot_ledger", [])
        if p.get("chapter_number") not in nums
    ]
    memory["chapter_ledger"] = [
        cl for cl in memory.get("chapter_ledger", [])
        if cl.get("chapter_number") not in nums
    ]


def _shift_entity_last_seen(memory, pivot, delta, *, strict_gt=False):
    if not memory:
        return
    for ledger_key in ("character_ledger", "location_ledger", "artifact_ledger", "faction_ledger"):
        ledger = memory.get(ledger_key, {})
        if not isinstance(ledger, dict):
            continue
        for scope in ("local", "global"):
            bucket = ledger.get(scope, {})
            if not isinstance(bucket, dict):
                continue
            for data in bucket.values():
                if not isinstance(data, dict):
                    continue
                last_seen = data.get("last_seen_turn")
                if not isinstance(last_seen, (int, float)):
                    continue
                if strict_gt:
                    if last_seen > pivot:
                        data["last_seen_turn"] = int(last_seen) + delta
                elif last_seen >= pivot:
                    data["last_seen_turn"] = int(last_seen) + delta

    for state in (memory.get("global_states") or {}).values():
        if not isinstance(state, dict):
            continue
        last_seen = state.get("last_seen_turn")
        if not isinstance(last_seen, (int, float)):
            continue
        if strict_gt:
            if last_seen > pivot:
                state["last_seen_turn"] = int(last_seen) + delta
        elif last_seen >= pivot:
            state["last_seen_turn"] = int(last_seen) + delta


def chapter_end_turn_or_max(chapter, history):
    """Resolve open-ended chapter end to the current timeline tail turn."""
    end = chapter.get("end_turn")
    if end is not None:
        return coerce_turn(end)
    return max_history_turn(history)


def select_plot_ledger_for_prompt(memory, active_chapter, full_history_turns):
    """Pick plot-ledger chunks for the active chapter that are not superseded by full turns."""
    if not memory or not active_chapter:
        return []

    plot_ledger = memory.get("plot_ledger", []) or []
    chapter_ledger = memory.get("chapter_ledger", []) or []
    condensed_nums = {
        c.get("chapter_number")
        for c in chapter_ledger
        if c.get("chapter_number") is not None
    }

    active_ch_num = active_chapter.get("chapter_number")
    chapter_start = coerce_turn(active_chapter.get("start_turn"), 1)
    chapter_end_raw = active_chapter.get("end_turn")
    chapter_end = coerce_turn(chapter_end_raw) if chapter_end_raw is not None else None

    full_turns = {coerce_turn(t) for t in (full_history_turns or []) if t is not None}
    min_full = min(full_turns) if full_turns else None

    selected = []
    for entry in plot_ledger:
        if not isinstance(entry, dict):
            continue
        ch_num = entry.get("chapter_number")
        if ch_num in condensed_nums or ch_num != active_ch_num:
            continue

        start = coerce_turn(entry.get("start_turn"), 0)
        end = coerce_turn(entry.get("end_turn"), 0)
        if start < chapter_start:
            continue
        if chapter_end is not None and end > chapter_end:
            continue
        if min_full is not None and end < min_full:
            selected.append(entry)
        elif min_full is None:
            selected.append(entry)

    selected.sort(key=lambda p: (coerce_turn(p.get("start_turn"), 0), coerce_turn(p.get("end_turn"), 0)))
    return selected


def format_plot_ledger_section(selected, active_chapter):
    """Format selected plot-ledger chunks for injection into the LLM system prompt."""
    if not selected:
        return ""
    ch_num = active_chapter.get("chapter_number", "?")
    ch_title = active_chapter.get("title", "")
    lines = [
        f"PLOT PARTS (Chapter {ch_num}: {ch_title} — bridging summaries to full scenes):"
    ]
    for entry in selected:
        start = entry.get("start_turn", "?")
        end = entry.get("end_turn", "?")
        lines.append(f"- Turns {start}-{end}: {entry.get('summary', '')}")
    return "\n".join(lines)
