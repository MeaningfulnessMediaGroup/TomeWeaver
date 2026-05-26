"""Dialogs for branch-pack export and import (run-tree sharing)."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import filedialog, messagebox


def show_cartridge_export_dialog(parent, folder_name: str, *, preselect_run_id: str | None = None):
    """Full cartridge vs selected run-tree branches."""
    from api import TomeWeaverAPI, get_adv_dir
    from branch_pack import export_branch_pack
    from run_tree import get_run_tree_rows, persist_active_run_to_snapshot

    adv_dir = get_adv_dir() / folder_name
    if not adv_dir.exists():
        messagebox.showerror("Export", "Story folder not found.", parent=parent)
        return

    persist_active_run_to_snapshot(adv_dir)
    rows, default_id = get_run_tree_rows(adv_dir)

    dialog = ctk.CTkToplevel(parent)
    dialog.title("Export Cartridge")
    dialog.geometry("620x520")
    dialog.transient(parent.winfo_toplevel())
    dialog.attributes("-topmost", True)
    dialog.grab_set()

    from ui.tooltip import center_window_on_parent

    center_window_on_parent(dialog, parent.winfo_toplevel())

    ctk.CTkLabel(dialog, text="Export Story", font=("Arial", 18, "bold")).pack(pady=(15, 5))
    ctk.CTkLabel(
        dialog,
        text="Share a full cartridge (setup + all files) or a branch pack (timelines only,\n"
        "for importing into the same story setup on another machine).",
        font=("Arial", 11),
        text_color="gray",
        justify="left",
        wraplength=560,
    ).pack(anchor="w", padx=20, pady=(0, 10))

    mode_var = ctk.StringVar(value="full")

    branch_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    check_vars: dict[str, ctk.BooleanVar] = {}
    shared_var = ctk.StringVar()

    rb_full = ctk.CTkRadioButton(
        dialog,
        text="Full cartridge — setup, prompts, memory, entire run tree",
        variable=mode_var,
        value="full",
        command=lambda: branch_frame.pack_forget(),
    )
    rb_full.pack(anchor="w", padx=20, pady=4)

    def show_branch_panel():
        branch_frame.pack(fill="both", expand=True, padx=20, pady=5)

    rb_branch = ctk.CTkRadioButton(
        dialog,
        text="Branch pack — selected timelines only (import into matching story)",
        variable=mode_var,
        value="branches",
        command=show_branch_panel,
    )
    rb_branch.pack(anchor="w", padx=20, pady=4)

    if rows:
        ctk.CTkLabel(branch_frame, text="Timelines to include (ancestors added automatically):", anchor="w").pack(
            fill="x", pady=(0, 4)
        )
        scroll = ctk.CTkScrollableFrame(branch_frame, fg_color="#2B2B2B", height=180)
        scroll.pack(fill="both", expand=True)

        preselect = preselect_run_id or default_id
        for row in rows:
            var = ctk.BooleanVar(value=bool(preselect and row["id"] == preselect))
            check_vars[row["id"]] = var
            ctk.CTkCheckBox(scroll, text=row["line"], variable=var, font=("Consolas", 11)).pack(
                anchor="w", padx=8, pady=2
            )

        btn_row = ctk.CTkFrame(branch_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=4)

        def select_all():
            for var in check_vars.values():
                var.set(True)

        def select_none():
            for var in check_vars.values():
                var.set(False)

        ctk.CTkButton(btn_row, text="Select all", width=90, command=select_all).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_row, text="Clear", width=70, fg_color="#4A4A4A", command=select_none).pack(side="left")

        ctk.CTkLabel(branch_frame, text="Shared by (optional):", anchor="w").pack(fill="x", pady=(8, 2))
        ctk.CTkEntry(branch_frame, textvariable=shared_var, placeholder_text="Your name or handle").pack(fill="x")
    else:
        ctk.CTkLabel(
            branch_frame,
            text="No run-tree timelines yet. Fork on the timeline or Restart with Save first.",
            text_color="gray",
            wraplength=520,
            justify="left",
        ).pack(anchor="w")

    if preselect_run_id and rows:
        mode_var.set("branches")
        show_branch_panel()

    btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=15)

    def on_export():
        if mode_var.get() == "full":
            path = filedialog.asksaveasfilename(
                parent=dialog,
                defaultextension=".zip",
                initialfile=f"{folder_name}.zip",
                filetypes=[("ZIP cartridges", "*.zip")],
            )
            if not path:
                return
            ok, msg = TomeWeaverAPI.export_to_zip(folder_name, path)
        else:
            if not rows:
                messagebox.showwarning("Export", "No timelines to export.", parent=dialog)
                return
            selected = [rid for rid, var in check_vars.items() if var.get()]
            if not selected:
                messagebox.showwarning("Export", "Select at least one timeline.", parent=dialog)
                return
            path = filedialog.asksaveasfilename(
                parent=dialog,
                defaultextension=".zip",
                initialfile=f"{folder_name}_branches.zip",
                filetypes=[("Branch packs", "*.zip")],
            )
            if not path:
                return
            ok, msg = export_branch_pack(
                adv_dir,
                selected,
                path,
                shared_by=shared_var.get().strip(),
            )

        if ok:
            messagebox.showinfo("Export Successful", msg, parent=parent)
            dialog.destroy()
        else:
            messagebox.showerror("Export Failed", msg, parent=dialog)

    ctk.CTkButton(btn_frame, text="Cancel", width=90, fg_color="#4A4A4A", command=dialog.destroy).pack(side="left")
    ctk.CTkButton(
        btn_frame,
        text="Export…",
        width=100,
        fg_color="#1F6AA5",
        hover_color="#144870",
        command=on_export,
    ).pack(side="right")


def show_branch_import_dialog(
    parent,
    zip_path: str,
    *,
    target_folder_name: str | None = None,
    on_success=None,
):
    """Import branch-pack timelines into an existing story."""
    from api import get_adv_dir
    from branch_pack import import_branch_pack, inspect_zip_cartridge, list_importable_stories

    kind, payload = inspect_zip_cartridge(zip_path)
    if kind != "branch_pack":
        messagebox.showerror("Import", payload if isinstance(payload, str) else "Not a branch pack.", parent=parent)
        return

    pack = payload
    fp = pack.get("setup_fingerprint") or {}
    stories = list_importable_stories(get_adv_dir(), fp)
    if not stories:
        messagebox.showerror("Import", "No stories found in your library.", parent=parent)
        return

    dialog = ctk.CTkToplevel(parent)
    dialog.title("Import Branch Pack")
    dialog.geometry("640x560")
    dialog.transient(parent.winfo_toplevel())
    dialog.attributes("-topmost", True)
    dialog.grab_set()

    from ui.tooltip import center_window_on_parent

    center_window_on_parent(dialog, parent.winfo_toplevel())

    ctk.CTkLabel(dialog, text="Import Timelines", font=("Arial", 18, "bold")).pack(pady=(15, 5))

    meta_lines = [
        f"From: {pack.get('source_title', 'Unknown story')}",
        f"Exported: {pack.get('exported_at', '?')}",
    ]
    if pack.get("shared_by"):
        meta_lines.append(f"Shared by: {pack['shared_by']}")
    ctk.CTkLabel(dialog, text="\n".join(meta_lines), font=("Arial", 11), text_color="gray", justify="left").pack(
        anchor="w", padx=20
    )

    ctk.CTkLabel(dialog, text="Import into story:", anchor="w", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=20, pady=(12, 4)
    )

    story_labels = []
    story_map: dict[str, str] = {}
    for s in stories:
        tag = " ✓ same setup" if s["compatible"] else " ⚠ different setup"
        label = f"{s['title']} ({s['folder_name']}){tag}"
        story_labels.append(label)
        story_map[label] = s["folder_name"]

    story_var = ctk.StringVar(value=story_labels[0] if story_labels else "")
    if target_folder_name:
        for lbl, fname in story_map.items():
            if fname == target_folder_name:
                story_var.set(lbl)
                break

    ctk.CTkOptionMenu(dialog, variable=story_var, values=story_labels, width=560).pack(padx=20, fill="x")

    ctk.CTkLabel(dialog, text="Label prefix for imported timelines:", anchor="w").pack(anchor="w", padx=20, pady=(10, 2))
    prefix_default = f"[{pack['shared_by']}] " if pack.get("shared_by") else "[Import] "
    prefix_var = ctk.StringVar(value=prefix_default)
    ctk.CTkEntry(dialog, textvariable=prefix_var).pack(fill="x", padx=20)

    ctk.CTkLabel(dialog, text="Timelines to import:", anchor="w", font=("Arial", 13, "bold")).pack(
        anchor="w", padx=20, pady=(10, 4)
    )

    scroll = ctk.CTkScrollableFrame(dialog, fg_color="#2B2B2B", height=160)
    scroll.pack(fill="both", expand=True, padx=20, pady=5)

    check_vars: dict[str, ctk.BooleanVar] = {}
    for node in pack.get("nodes") or []:
        export_id = node["export_id"]
        line = f"{node.get('label', export_id)}  ({node.get('turn_count', '?')} turns)"
        if node.get("fork_at_turn"):
            line += f"  fork @ {node['fork_at_turn']}"
        var = ctk.BooleanVar(value=True)
        check_vars[export_id] = var
        ctk.CTkCheckBox(scroll, text=line, variable=var, font=("Consolas", 11)).pack(anchor="w", padx=8, pady=2)

    btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=15)

    def on_import():
        folder = story_map.get(story_var.get())
        if not folder:
            messagebox.showwarning("Import", "Select a target story.", parent=dialog)
            return

        selected_story = next((s for s in stories if s["folder_name"] == folder), None)
        if selected_story and not selected_story["compatible"]:
            if not messagebox.askyesno(
                "Setup Mismatch",
                "This pack was exported from a story with a different setup fingerprint.\n\n"
                "Timelines may not align at fork points. Import anyway?",
                parent=dialog,
                icon="warning",
            ):
                return

        export_ids = [eid for eid, var in check_vars.items() if var.get()]
        if not export_ids:
            messagebox.showwarning("Import", "Select at least one timeline.", parent=dialog)
            return

        target_dir = get_adv_dir() / folder
        ok, msg = import_branch_pack(
            target_dir,
            zip_path,
            export_ids,
            label_prefix=prefix_var.get(),
        )
        if ok:
            messagebox.showinfo("Import Successful", msg, parent=parent)
            dialog.destroy()
            if on_success:
                on_success(folder)
        else:
            messagebox.showerror("Import Failed", msg, parent=dialog)

    ctk.CTkButton(btn_frame, text="Cancel", width=90, fg_color="#4A4A4A", command=dialog.destroy).pack(side="left")
    ctk.CTkButton(
        btn_frame,
        text="Import",
        width=100,
        fg_color="#2E7D32",
        hover_color="#1B5E20",
        command=on_import,
    ).pack(side="right")
