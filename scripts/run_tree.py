"""
TomeWeaver: Run Tree (Phase 1–3)
-----------------------------------
Archives the active cartridge trio (history, chapters, memory) under
``runs/snapshots/<run_id>/`` and tracks metadata in ``runs/manifest.json``.

The cartridge root always holds the hot copy of the active timeline. Each run
node owns a snapshot folder that Switch updates in place (no new tree nodes).
Fork Here creates a parent archive plus a branch snapshot at fork time.
Restart → Save and Restore & Fork are the other paths that add nodes.

Phase 2 adds fork-at-turn archival metadata (``fork_at_turn`` on manifest
nodes); truncation/heal logic lives on :meth:`BaseEngine.fork_at_turn`.

Phase 3 adds :func:`restore_and_fork` and tree-ordered display helpers.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from config import load_json_safely, save_json_atomically

MANIFEST_VERSION = 1
ROOT_FILES = ("history.json", "chapters.json", "memory.json")
RUNS_DIR = "runs"
MANIFEST_REL = "runs/manifest.json"
SNAPSHOTS_REL = "runs/snapshots"


def _adv(adv_dir) -> Path:
    return Path(adv_dir)


def _manifest_path(adv_dir) -> Path:
    return _adv(adv_dir) / MANIFEST_REL


def _snapshot_dir(adv_dir, run_id: str) -> Path:
    return _adv(adv_dir) / SNAPSHOTS_REL / run_id


def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def empty_manifest() -> dict:
    return {"version": MANIFEST_VERSION, "active_run_id": None, "runs": {}}


def load_manifest(adv_dir) -> dict:
    """Load ``runs/manifest.json`` or return an empty in-memory manifest."""
    path = _manifest_path(adv_dir)
    if not path.exists():
        return empty_manifest()

    data = load_json_safely(path, "runs/manifest.json")
    if not isinstance(data, dict):
        return empty_manifest()

    data.setdefault("version", MANIFEST_VERSION)
    data.setdefault("active_run_id", None)
    if not isinstance(data.get("runs"), dict):
        data["runs"] = {}
    return data


def save_manifest(adv_dir, manifest: dict) -> None:
    path = _manifest_path(adv_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json_atomically(manifest, path)


def _load_history(adv_dir):
    history_file = _adv(adv_dir) / "history.json"
    if not history_file.exists():
        return []
    return load_json_safely(history_file, "history.json") or []


def turn_count_from_history(history) -> int:
    """Return the highest committed turn number in history."""
    if not history:
        return 0
    return max(int(t.get("turn", 0)) for t in history)


def auto_run_label(history) -> str:
    turn = turn_count_from_history(history)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"Run ending Turn {turn} — {ts}"


def auto_fork_archive_label(fork_turn: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"Original timeline (fork @ turn {fork_turn}) — {ts}"


def auto_branch_label(fork_turn: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"Branch (fork @ turn {fork_turn}) — {ts}"


LIVE_BRANCH_ROW_ID = "__live__"


def has_saveable_state(adv_dir) -> bool:
    return len(_load_history(adv_dir)) > 0


def copy_root_to_snapshot(adv_dir, snapshot_dir: Path) -> None:
    """Copy history/chapters/memory from cartridge root into a snapshot folder."""
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    root = _adv(adv_dir)

    for fname in ROOT_FILES:
        src = root / fname
        dst = snapshot_dir / fname
        if src.exists():
            shutil.copy2(src, dst)
        elif fname == "history.json":
            save_json_atomically([], dst)
        elif fname == "chapters.json":
            save_json_atomically([], dst)
        elif fname == "memory.json":
            save_json_atomically({}, dst)


def load_snapshot_to_root(adv_dir, snapshot_dir: Path) -> None:
    """Replace cartridge root trio with files from a snapshot folder."""
    snapshot_dir = Path(snapshot_dir)
    root = _adv(adv_dir)

    for fname in ROOT_FILES:
        src = snapshot_dir / fname
        dst = root / fname
        if not src.exists():
            raise FileNotFoundError(f"Snapshot missing required file: {fname}")
        shutil.copy2(src, dst)


def archive_current_run(
    adv_dir,
    label: str | None = None,
    *,
    parent_id: str | None = None,
    fork_at_turn: int | None = None,
    run_kind: str | None = None,
) -> tuple[str | None, str]:
    """Snapshot the current root state and register it in the manifest."""
    adv_dir = _adv(adv_dir)
    history = _load_history(adv_dir)
    if not history:
        return None, "Nothing to archive — no turns played yet."

    manifest = load_manifest(adv_dir)
    run_id = _new_run_id()
    label = (label or auto_run_label(history)).strip()
    if not label:
        label = auto_run_label(history)

    if run_kind is None:
        run_kind = "original" if fork_at_turn is not None else "snapshot"

    snap_rel = f"{SNAPSHOTS_REL}/{run_id}"
    snap_path = adv_dir / snap_rel
    copy_root_to_snapshot(adv_dir, snap_path)

    now = datetime.now().isoformat(timespec="seconds")
    node = {
        "id": run_id,
        "label": label,
        "parent_id": parent_id,
        "fork_at_turn": fork_at_turn,
        "run_kind": run_kind,
        "snapshot_path": snap_rel,
        "created_at": now,
        "updated_at": now,
        "turn_count": turn_count_from_history(history),
    }
    save_json_atomically(node, snap_path / "meta.json")

    manifest["runs"][run_id] = node
    save_manifest(adv_dir, manifest)
    return run_id, f"Saved run '{label}'."


def list_runs(adv_dir) -> tuple[list[dict], str | None]:
    """Return archived runs (newest first) and ``active_run_id``."""
    manifest = load_manifest(adv_dir)
    runs = list(manifest.get("runs", {}).values())
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs, manifest.get("active_run_id")


def runs_for_tree_display(adv_dir) -> list[dict]:
    """Return runs ordered for tree display (roots first, children nested by ``parent_id``)."""
    manifest = load_manifest(adv_dir)
    runs_by_id = manifest.get("runs", {})
    if not runs_by_id:
        return []

    children_map: dict[str | None, list[dict]] = {}
    for run in runs_by_id.values():
        parent = run.get("parent_id")
        if parent not in runs_by_id:
            parent = None
        children_map.setdefault(parent, []).append(run)

    for siblings in children_map.values():
        siblings.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    ordered: list[dict] = []

    def walk(parent_id, depth):
        for run in children_map.get(parent_id, []):
            ordered.append({**run, "_depth": depth})
            walk(run["id"], depth + 1)

    walk(None, 0)
    return ordered


def format_run_tree_line(run: dict, *, active_run_id: str | None = None) -> str:
    """Human-readable single line for Run Tree UI."""
    depth = int(run.get("_depth", 0))
    indent = "    " * depth + ("↳ " if depth else "")
    label = run.get("label", run.get("id", "Run"))
    turn_count = run.get("turn_count", 0)
    parts = [f"{indent}{label}  ({turn_count} turns)"]

    kind = run.get("run_kind")
    if run.get("id") == active_run_id:
        parts.append("● playing now")
    elif kind == "branch":
        parts.append("[alternate branch]")
    elif kind == "original":
        parts.append("[parent timeline]")
    elif kind == "snapshot":
        parts.append("[saved run]")
    return " ".join(parts)


def format_live_branch_line(live_branch: dict, turn_count: int) -> str:
    fork_turn = live_branch.get("forked_at_turn", "?")
    return (
        f"    ↳ ● Current branch (fork @ turn {fork_turn}, {turn_count} turns) — playing now"
    )


def set_active_run_id(adv_dir, run_id: str | None) -> None:
    """Point the cartridge root at manifest run ``run_id`` (``None`` = unlinked live line)."""
    manifest = load_manifest(adv_dir)
    manifest["active_run_id"] = run_id
    manifest.pop("live_branch", None)
    save_manifest(adv_dir, manifest)


def migrate_legacy_fork_state(adv_dir) -> None:
    """Upgrade old ``live_branch``-only saves to a real branch snapshot + ``active_run_id``."""
    manifest = load_manifest(adv_dir)
    live = manifest.get("live_branch")
    if not live:
        return

    fork_from = live.get("forked_from_run_id")
    fork_turn = live.get("forked_at_turn")
    if not fork_from or fork_turn is None:
        manifest.pop("live_branch", None)
        save_manifest(adv_dir, manifest)
        return

    fork_turn = int(fork_turn)
    for run in manifest.get("runs", {}).values():
        if (
            run.get("parent_id") == fork_from
            and run.get("run_kind") == "branch"
            and int(run.get("fork_at_turn", -1)) == fork_turn
        ):
            manifest["active_run_id"] = run["id"]
            manifest.pop("live_branch", None)
            save_manifest(adv_dir, manifest)
            return

    if not has_saveable_state(adv_dir):
        manifest.pop("live_branch", None)
        save_manifest(adv_dir, manifest)
        return

    branch_id, _ = archive_current_run(
        adv_dir,
        label=auto_branch_label(fork_turn),
        parent_id=fork_from,
        fork_at_turn=fork_turn,
        run_kind="branch",
    )
    if branch_id:
        manifest = load_manifest(adv_dir)
        manifest["active_run_id"] = branch_id
        manifest.pop("live_branch", None)
        save_manifest(adv_dir, manifest)


def persist_active_run_to_snapshot(adv_dir) -> tuple[bool, str]:
    """Overwrite the active run's snapshot from the cartridge root (no new manifest nodes)."""
    migrate_legacy_fork_state(adv_dir)
    adv_dir = _adv(adv_dir)
    if not has_saveable_state(adv_dir):
        return True, ""

    manifest = load_manifest(adv_dir)
    active_id = manifest.get("active_run_id")
    if not active_id:
        return True, ""

    node = manifest.get("runs", {}).get(active_id)
    if not node:
        return True, ""

    snap_path = adv_dir / node["snapshot_path"]
    copy_root_to_snapshot(adv_dir, snap_path)

    history = _load_history(adv_dir)
    now = datetime.now().isoformat(timespec="seconds")
    node["turn_count"] = turn_count_from_history(history)
    node["updated_at"] = now
    manifest["runs"][active_id] = node
    save_manifest(adv_dir, manifest)

    meta_path = snap_path / "meta.json"
    meta = load_json_safely(meta_path, "meta.json")
    if isinstance(meta, dict):
        meta["turn_count"] = node["turn_count"]
        meta["updated_at"] = now
        save_json_atomically(meta, meta_path)

    return True, ""


def get_active_playback_id(adv_dir) -> str | None:
    """Manifest run id for the timeline currently loaded at the cartridge root."""
    migrate_legacy_fork_state(adv_dir)
    return load_manifest(adv_dir).get("active_run_id")


def can_switch_to_run(adv_dir, run_id: str) -> tuple[bool, str]:
    """False when ``run_id`` is already the active timeline."""
    current = get_active_playback_id(adv_dir)
    if current and run_id == current:
        return False, "You are already playing this timeline."
    return True, ""


def get_run_tree_rows(adv_dir) -> tuple[list[dict], str | None]:
    """Rows for the Run Tree UI — one row per manifest run, active row highlighted."""
    migrate_legacy_fork_state(adv_dir)
    active_id = load_manifest(adv_dir).get("active_run_id")
    rows: list[dict] = []

    for run in runs_for_tree_display(adv_dir):
        is_active = run["id"] == active_id
        rows.append({
            "id": run["id"],
            "kind": "branch" if run.get("run_kind") == "branch" else "archive",
            "line": format_run_tree_line(run, active_run_id=active_id),
            "is_live": is_active,
        })

    default_id = active_id
    if default_id is None and rows:
        default_id = rows[0]["id"]
    return rows, default_id


def set_live_branch(adv_dir, *, forked_from_run_id: str, forked_at_turn: int) -> None:
    """Mark the cartridge root as a live fork branch spawned from an archived original."""
    manifest = load_manifest(adv_dir)
    manifest["live_branch"] = {
        "forked_from_run_id": forked_from_run_id,
        "forked_at_turn": int(forked_at_turn),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest["active_run_id"] = None
    save_manifest(adv_dir, manifest)


def clear_live_branch(adv_dir) -> None:
    path = _manifest_path(adv_dir)
    if not path.exists():
        return
    manifest = load_manifest(adv_dir)
    if "live_branch" in manifest:
        del manifest["live_branch"]
        save_manifest(adv_dir, manifest)


def stash_current_line(adv_dir, label: str | None = None) -> tuple[str | None, str]:
    """Archive the live root; link fork branches to their original timeline."""
    if not has_saveable_state(adv_dir):
        return None, "Nothing to archive — no turns played yet."

    manifest = load_manifest(adv_dir)
    live_branch = manifest.get("live_branch")
    if live_branch:
        fork_turn = int(live_branch["forked_at_turn"])
        label = label or auto_branch_label(fork_turn)
        run_id, msg = archive_current_run(
            adv_dir,
            label=label,
            parent_id=live_branch.get("forked_from_run_id"),
            fork_at_turn=fork_turn,
            run_kind="branch",
        )
    else:
        run_id, msg = archive_current_run(adv_dir, label=label)

    if run_id:
        clear_live_branch(adv_dir)
    return run_id, msg


def list_fork_points_for_run(adv_dir, run_id: str) -> tuple[bool, list[int] | str]:
    """Turn numbers in a snapshot where Restore & Fork is valid."""
    manifest = load_manifest(adv_dir)
    node = manifest.get("runs", {}).get(run_id)
    if not node:
        return False, "Run not found."

    hist_path = _adv(adv_dir) / node["snapshot_path"] / "history.json"
    if not hist_path.exists():
        return False, "Snapshot history missing."

    history = load_json_safely(hist_path, "history.json") or []
    points = []
    for i, turn in enumerate(history):
        if turn.get("player_choice") and i < len(history) - 1:
            points.append(int(turn.get("turn", i + 1)))
    return True, points


def restore_and_fork(adv_dir, run_id: str, fork_turn_number: int) -> tuple[bool, str]:
    """Load an archived run, then fork @ turn N in one step (persists active slot first)."""
    adv_dir = _adv(adv_dir)
    manifest = load_manifest(adv_dir)
    node = manifest.get("runs", {}).get(run_id)
    if not node:
        return False, "Run not found."

    snap = adv_dir / node["snapshot_path"]
    if not snap.exists():
        return False, "Snapshot files missing."

    ok_pts, pts_or_msg = list_fork_points_for_run(adv_dir, run_id)
    if not ok_pts:
        return False, str(pts_or_msg)
    if int(fork_turn_number) not in pts_or_msg:
        return False, f"Turn {fork_turn_number} is not a valid fork point for this run."

    ok_persist, persist_msg = persist_active_run_to_snapshot(adv_dir)
    if not ok_persist:
        return False, persist_msg

    load_snapshot_to_root(adv_dir, snap)
    set_active_run_id(adv_dir, run_id)

    from config import load_json_safely as _load_setup
    from sandbox import SandboxEngine
    from campaign import CampaignEngine

    setup = _load_setup(adv_dir / "setup.json", "setup.json")
    mode = str(setup.get("mode", "sandbox")).lower()
    if mode == "campaign":
        engine = CampaignEngine(adv_dir, setup)
    else:
        engine = SandboxEngine(adv_dir, setup)

    ok, msg, _ = engine.fork_at_turn(int(fork_turn_number))
    return ok, msg


def rename_run(adv_dir, run_id: str, new_label: str) -> tuple[bool, str]:
    new_label = new_label.strip()
    if not new_label:
        return False, "Label cannot be empty."

    manifest = load_manifest(adv_dir)
    node = manifest.get("runs", {}).get(run_id)
    if not node:
        return False, "Run not found."

    node["label"] = new_label
    node["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_manifest(adv_dir, manifest)

    meta_path = _adv(adv_dir) / node["snapshot_path"] / "meta.json"
    if meta_path.exists():
        meta = load_json_safely(meta_path, "meta.json")
        if isinstance(meta, dict):
            meta["label"] = new_label
            meta["updated_at"] = node["updated_at"]
            save_json_atomically(meta, meta_path)

    return True, "Run renamed."


def delete_run(adv_dir, run_id: str) -> tuple[bool, str]:
    manifest = load_manifest(adv_dir)
    node = manifest.get("runs", {}).pop(run_id, None)
    if not node:
        return False, "Run not found."

    if manifest.get("active_run_id") == run_id:
        manifest["active_run_id"] = None
    save_manifest(adv_dir, manifest)

    snap = _adv(adv_dir) / node.get("snapshot_path", "")
    if snap.exists() and snap.is_dir():
        shutil.rmtree(snap)

    return True, "Run deleted."


def clear_active_run_id(adv_dir) -> None:
    path = _manifest_path(adv_dir)
    if not path.exists():
        return
    manifest = load_manifest(adv_dir)
    manifest["active_run_id"] = None
    manifest.pop("live_branch", None)
    save_manifest(adv_dir, manifest)


def switch_run(adv_dir, run_id: str, *, stash_current: bool = False) -> tuple[bool, str]:
    """Persist the active timeline in place, then load ``run_id`` to the cartridge root."""
    adv_dir = _adv(adv_dir)
    ok, err = can_switch_to_run(adv_dir, run_id)
    if not ok:
        return False, err

    manifest = load_manifest(adv_dir)
    node = manifest.get("runs", {}).get(run_id)
    if not node:
        return False, "Run not found."

    snap = adv_dir / node["snapshot_path"]
    if not snap.exists():
        return False, "Snapshot files missing."

    if stash_current and has_saveable_state(adv_dir):
        stash_id, stash_msg = stash_current_line(adv_dir)
        if stash_id is None and "Nothing to archive" not in stash_msg:
            return False, stash_msg
        manifest = load_manifest(adv_dir)
        node = manifest["runs"].get(run_id)
        if not node:
            return False, "Run not found."
    else:
        ok_persist, persist_msg = persist_active_run_to_snapshot(adv_dir)
        if not ok_persist:
            return False, persist_msg

    load_snapshot_to_root(adv_dir, snap)
    set_active_run_id(adv_dir, run_id)

    _clear_session_log(adv_dir)
    return True, f"Switched to '{node['label']}'."


def _clear_session_log(adv_dir) -> None:
    log_file = _adv(adv_dir) / "session_log.txt"
    if log_file.exists():
        try:
            log_file.unlink()
        except OSError:
            pass


def headless_restart_wipe(adv_dir, setup_data: dict) -> None:
    """Reset history and chapters on disk (dashboard / API path). Does not touch memory."""
    target_dir = _adv(adv_dir)
    history_file = target_dir / "history.json"
    chapters_file = target_dir / "chapters.json"

    save_json_atomically([], history_file)

    mode = str(setup_data.get("mode", "sandbox")).lower()
    if mode == "campaign":
        outline = setup_data.get("plot_outline", [])
        if outline:
            first = outline[0]
            objs = []
            for i, o in enumerate(first.get("objectives", [])):
                o_copy = o.copy()
                o_copy["status"] = "ACTIVE" if i == 0 else "LOCKED"
                objs.append(o_copy)
            initial = [{
                "chapter_number": 1,
                "title": first.get("title", "Chapter 1"),
                "start_turn": 1,
                "end_turn": None,
                "objectives": objs,
            }]
        else:
            initial = [{
                "chapter_number": 1,
                "title": "Chapter 1",
                "start_turn": 1,
                "end_turn": None,
            }]
    else:
        initial = [{
            "chapter_number": 1,
            "title": setup_data.get("title", "Chapter 1"),
            "start_turn": 1,
            "end_turn": None,
        }]

    save_json_atomically(initial, chapters_file)
    _clear_session_log(adv_dir)


def prepare_restart(adv_dir, *, save_run: bool = True) -> tuple[bool, str]:
    """Optional archive + mark a fresh active line before wipe."""
    if save_run:
        run_id, msg = archive_current_run(adv_dir)
        if run_id is None and "Nothing to archive" not in msg:
            return False, msg
    clear_active_run_id(adv_dir)
    return True, "Ready to restart."
