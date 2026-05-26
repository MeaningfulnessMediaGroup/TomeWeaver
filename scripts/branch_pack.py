"""
TomeWeaver: Branch Pack export / import
---------------------------------------
Portable ``.zip`` packs that share run-tree timelines between copies of the
same story setup. Full cartridges remain separate (``export_to_zip``).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from config import load_json_safely, save_json_atomically

PACK_VERSION = 1
PACK_TYPE = "tome_branch_pack"
PACK_MANIFEST = "branch_pack.json"
BRANCHES_PREFIX = "branches"

SETUP_FINGERPRINT_KEYS = ("title", "mode", "main_character", "goal", "setting")


def compute_setup_fingerprint(setup_data: dict) -> dict:
    """Stable fingerprint so importers can warn when setups differ."""
    subset = {k: setup_data.get(k) for k in SETUP_FINGERPRINT_KEYS}
    mode = str(setup_data.get("mode", "sandbox")).lower()
    if mode == "campaign":
        outline = setup_data.get("plot_outline") or []
        subset["plot_chapters"] = [c.get("title") for c in outline]
    canonical = json.dumps(subset, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return {
        "title": setup_data.get("title", "Untitled"),
        "mode": mode,
        "digest": digest,
    }


def inspect_zip_cartridge(zip_path) -> tuple[str, dict | str]:
    """Return ``('branch_pack', manifest)``, ``('full', {})``, or ``('invalid', message)``."""
    zip_path = Path(zip_path)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if PACK_MANIFEST in names:
                raw = zf.read(PACK_MANIFEST).decode("utf-8")
                manifest = json.loads(raw)
                if manifest.get("pack_type") != PACK_TYPE:
                    return "invalid", "Unrecognized branch pack format."
                return "branch_pack", manifest

            has_setup = any(f.endswith("setup.json") for f in names)
            has_prompt = any(f.endswith("system_prompt.txt") for f in names)
            if has_setup and has_prompt:
                return "full", {}
            return "invalid", "Invalid cartridge: missing setup.json or system_prompt.txt."
    except zipfile.BadZipFile:
        return "invalid", "Invalid or corrupted zip file."
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        return "invalid", str(exc)


def collect_run_closure(adv_dir, run_ids: list[str]) -> list[str]:
    """Selected runs plus manifest ancestors, in tree-display order."""
    from run_tree import load_manifest, runs_for_tree_display

    manifest = load_manifest(adv_dir)
    runs = manifest.get("runs", {})
    closure: set[str] = set()
    for rid in run_ids:
        cur = rid
        while cur and cur in runs:
            closure.add(cur)
            cur = runs[cur].get("parent_id")

    return [r["id"] for r in runs_for_tree_display(adv_dir) if r["id"] in closure]


def export_branch_pack(
    adv_dir,
    run_ids: list[str],
    target_zip_path,
    *,
    shared_by: str = "",
) -> tuple[bool, str]:
    """Write a branch pack zip containing ``run_ids`` and their ancestor nodes."""
    from run_tree import load_manifest, persist_active_run_to_snapshot

    adv_dir = Path(adv_dir)
    if not run_ids:
        return False, "Select at least one timeline to export."

    ok, msg = persist_active_run_to_snapshot(adv_dir)
    if not ok:
        return False, msg

    setup_path = adv_dir / "setup.json"
    if not setup_path.exists():
        return False, "setup.json not found."

    setup = load_json_safely(setup_path, "setup.json") or {}
    fingerprint = compute_setup_fingerprint(setup)
    manifest = load_manifest(adv_dir)
    runs = manifest.get("runs", {})

    closure = collect_run_closure(adv_dir, run_ids)
    if not closure:
        return False, "No valid timelines selected."

    export_id_for_run: dict[str, str] = {}
    nodes = []
    for run_id in closure:
        node = runs.get(run_id)
        if not node:
            continue
        export_id = f"exp_{run_id.replace('run_', '')[:12]}"
        export_id_for_run[run_id] = export_id
        parent_run = node.get("parent_id")
        parent_export = export_id_for_run.get(parent_run) if parent_run in closure else None
        nodes.append({
            "export_id": export_id,
            "source_run_id": run_id,
            "parent_export_id": parent_export,
            "label": node.get("label", run_id),
            "fork_at_turn": node.get("fork_at_turn"),
            "run_kind": node.get("run_kind"),
            "turn_count": node.get("turn_count", 0),
        })

    pack = {
        "pack_version": PACK_VERSION,
        "pack_type": PACK_TYPE,
        "source_title": fingerprint.get("title"),
        "setup_fingerprint": fingerprint,
        "shared_by": (shared_by or "").strip(),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "nodes": nodes,
    }

    try:
        target_zip_path = Path(target_zip_path)
        with zipfile.ZipFile(target_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(PACK_MANIFEST, json.dumps(pack, indent=2, ensure_ascii=False))
            for run_id in closure:
                node = runs[run_id]
                export_id = export_id_for_run[run_id]
                snap = adv_dir / node["snapshot_path"]
                if not snap.is_dir():
                    return False, f"Snapshot missing for '{node.get('label', run_id)}'."
                for fname in ("history.json", "chapters.json", "memory.json", "meta.json"):
                    src = snap / fname
                    if src.exists():
                        arc = f"{BRANCHES_PREFIX}/{export_id}/{fname}"
                        zf.write(src, arc)
        return True, f"Exported {len(closure)} timeline(s)."
    except OSError as exc:
        return False, str(exc)


def list_importable_stories(adventures_dir, pack_fingerprint: dict) -> list[dict]:
    """Scan ``adventures/`` for stories that can receive a branch pack."""
    adventures_dir = Path(adventures_dir)
    target_digest = pack_fingerprint.get("digest")
    stories = []

    if not adventures_dir.exists():
        return stories

    for entry in sorted(adventures_dir.iterdir()):
        if not entry.is_dir():
            continue
        setup_path = entry / "setup.json"
        if not setup_path.exists():
            continue
        setup = load_json_safely(setup_path, "setup.json") or {}
        fp = compute_setup_fingerprint(setup)
        stories.append({
            "folder_name": entry.name,
            "title": fp.get("title") or entry.name,
            "compatible": fp.get("digest") == target_digest,
            "fingerprint": fp,
        })
    stories.sort(key=lambda s: (not s["compatible"], s["title"].lower()))
    return stories


def import_branch_pack(
    adv_dir,
    zip_path,
    export_ids: list[str] | None = None,
    *,
    label_prefix: str = "",
) -> tuple[bool, str]:
    """Merge selected branch pack nodes into an existing story manifest."""
    from run_tree import ROOT_FILES, _new_run_id, load_manifest, save_manifest, turn_count_from_history

    adv_dir = Path(adv_dir)
    zip_path = Path(zip_path)
    label_prefix = label_prefix.strip()

    kind, payload = inspect_zip_cartridge(zip_path)
    if kind != "branch_pack":
        return False, payload if isinstance(payload, str) else "Not a branch pack."

    pack = payload
    all_nodes = pack.get("nodes") or []
    if not all_nodes:
        return False, "Branch pack contains no timelines."

    selected = set(export_ids) if export_ids else {n["export_id"] for n in all_nodes}
    nodes = [n for n in all_nodes if n["export_id"] in selected]
    if not nodes:
        return False, "No timelines selected for import."

    selected_ids = {n["export_id"] for n in nodes}
    id_map: dict[str, str] = {}
    manifest = load_manifest(adv_dir)
    now = datetime.now().isoformat(timespec="seconds")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for node in nodes:
                export_id = node["export_id"]
                new_id = _new_run_id()
                id_map[export_id] = new_id

                snap_rel = f"runs/snapshots/{new_id}"
                snap_dir = adv_dir / snap_rel
                snap_dir.mkdir(parents=True, exist_ok=True)

                prefix = f"{BRANCHES_PREFIX}/{export_id}/"
                found_any = False
                for fname in ROOT_FILES + ("meta.json",):
                    arc = f"{prefix}{fname}"
                    if arc not in zf.namelist():
                        continue
                    found_any = True
                    target = snap_dir / fname
                    with zf.open(arc) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                if not found_any:
                    return False, f"Pack missing snapshot files for '{node.get('label', export_id)}'."

                parent_export = node.get("parent_export_id")
                parent_id = id_map.get(parent_export) if parent_export in selected_ids else None

                label = node.get("label") or export_id
                if label_prefix:
                    label = f"{label_prefix}{label}"

                history = load_json_safely(snap_dir / "history.json", "history.json") or []
                entry = {
                    "id": new_id,
                    "label": label,
                    "parent_id": parent_id,
                    "fork_at_turn": node.get("fork_at_turn"),
                    "run_kind": node.get("run_kind") or "snapshot",
                    "snapshot_path": snap_rel,
                    "created_at": now,
                    "updated_at": now,
                    "turn_count": turn_count_from_history(history),
                    "imported_from": {
                        "export_id": export_id,
                        "source_run_id": node.get("source_run_id"),
                        "shared_by": pack.get("shared_by", ""),
                        "exported_at": pack.get("exported_at"),
                    },
                }
                manifest["runs"][new_id] = entry

                meta_path = snap_dir / "meta.json"
                meta = load_json_safely(meta_path, "meta.json")
                if not isinstance(meta, dict):
                    meta = {}
                meta.update({
                    "id": new_id,
                    "label": label,
                    "turn_count": entry["turn_count"],
                    "updated_at": now,
                    "imported_from": entry["imported_from"],
                })
                save_json_atomically(meta, meta_path)

        save_manifest(adv_dir, manifest)
        return True, f"Imported {len(nodes)} timeline(s). Open Run Tree to switch or compare."
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        return False, str(exc)
