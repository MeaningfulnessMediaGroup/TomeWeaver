"""
    TomeWeaver: Root Application
    ----------------------------
    The top-level window manager for the application. Controls window scaling,
    saved geometries, and handles switching between the Dashboard and Active Workspaces.
"""
import json
import customtkinter as ctk
from tkinter import messagebox
from pathlib import Path
from api import TomeWeaverAPI
from config import create_boilerplate_files, ENGINE_CONFIG, INSTANCE_CONFIG, ROOT_DIR
from ui.dashboard import DashboardFrame


class TomeWeaverApp(ctk.CTk):

    """
    Root Application
    """
    def __init__(self, startup_story=None):
        super().__init__()

        self.title("TomeWeaver")
        self.minsize(900, 600)
        
        # Apply modern typing shortcuts globally to all Text and Entry widgets
        from ui.tooltip import apply_global_text_bindings
        apply_global_text_bindings(self)
        
        # --- RESTORE SAVED WINDOW GEOMETRY ---
        saved_geom = INSTANCE_CONFIG.get("window_geometry", "1100x750")
        saved_state = INSTANCE_CONFIG.get("window_state", "normal")
        
        # Apply Width, Height, and X/Y Screen Coordinates
        self.geometry(saved_geom)
        
        # Apply Maximized state safely (Cross-platform compatibility)
        if saved_state == "zoomed":
            try:
                self.state("zoomed") # Windows
            except Exception:
                try:
                    self.attributes("-zoomed", True) # Linux X11
                except Exception:
                    pass

        # Hook the OS 'X' close button to our custom save method
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self.active_frame = None
        self.last_dashboard_dir = "" # CRITICAL FIX: The app remembers where the user was looking

        if startup_story:
            self.open_workspace(startup_story)
        else:
            # Auto-Resume last played session
            last_story = INSTANCE_CONFIG.get("last_active_story", "")
            if last_story and (Path("adventures") / last_story).exists():
                self.open_workspace(last_story)
            else:
                self.open_dashboard()

    def _save_config_silently(self):
        """Helper to safely dump global config to disk."""
        try:
            with open(ROOT_DIR / "configs" / "engine_config.json", "w", encoding="utf-8") as f:
                json.dump(ENGINE_CONFIG, f, indent=4)
        except Exception:
            pass
    def _save_instance_config_silently(self):
        """Helper to safely dump volatile session settings to disk."""
        try:
            with open(ROOT_DIR / "configs" / "instance_config.json", "w", encoding="utf-8") as f:
                json.dump(INSTANCE_CONFIG, f, indent=4)
        except Exception:
            pass
            
    def _on_closing(self):
        """Fires exactly when the user clicks the X to close the app. Saves window state."""
        current_state = self.state()
        
        if current_state == "iconic":
            current_state = "normal"
            
        INSTANCE_CONFIG["window_state"] = current_state
        INSTANCE_CONFIG["window_geometry"] = self.geometry()
        
        self._save_instance_config_silently()
        self.destroy()
        
    def clear_container(self):
        """Destroys the current active view to make room for a new one."""
        if self.active_frame is not None:
            self.active_frame.destroy()

    def open_dashboard(self):
        """Loads the Screen 1: Dashboard, instantly restoring the previous directory state."""
        self.clear_container()
        
        # Retrieve the safely stored memory, defaulting to root if the app just booted
        restore_dir = getattr(self, 'last_dashboard_dir', "")
            
        from ui.dashboard import DashboardFrame
        self.active_frame = DashboardFrame(self.container, self, initial_dir=restore_dir)
        self.active_frame.pack(fill="both", expand=True)

    def open_workspace(self, folder_name, target_tab=None):
        """Loads the Screen 2: Workspace for a specific story."""
        
        if hasattr(self, 'active_frame') and self.active_frame.__class__.__name__ == "DashboardFrame":
            self.last_dashboard_dir = self.active_frame.current_dir
            
        setup_file = Path("adventures") / folder_name / "setup.json"
        
        if not setup_file.exists():
            self._prompt_boilerplate_initialization(folder_name)
            return

        # --- 1. ORPHAN RECOVERY CHECK ---
        from config import find_universe_root, load_json_safely
        univ_root_check = find_universe_root(setup_file.parent)
        setup_data_check = load_json_safely(setup_file, "setup.json")
        
        if not univ_root_check and setup_data_check.get("is_universe_thread", False):
            messagebox.showwarning("Orphaned Thread Detected", "This story was moved out of its Universe.\n\nIt will be converted back to a standalone story. Please run 'Compile Missing History' in the Memory tab to securely rebuild its local Lore Bible.")
            setup_data_check["is_universe_thread"] = False
            from config import save_json_atomically
            save_json_atomically(setup_data_check, setup_file)

        # --- 2. MIGRATION WIZARD INTERCEPTOR ---
        needs_migration, univ_root, conflicts = TomeWeaverAPI.analyze_migration(folder_name)
        if needs_migration:
            self._show_migration_wizard(folder_name, univ_root, conflicts, target_tab)
            return

        # --- 3. STANDARD BOOT SEQUENCE ---
        try:
            engine = TomeWeaverAPI.load_engine(folder_name)
            
            if hasattr(self, 'active_frame') and self.active_frame.__class__.__name__ == "WorkspaceFrame":
                if hasattr(self.active_frame, 'console_tab'):
                    self.active_frame.console_tab.restore_stdout()
                    
            self.clear_container()
            
            from ui.workspace import WorkspaceFrame
            self.active_frame = WorkspaceFrame(self.container, self, engine, folder_name=folder_name)
            self.active_frame.pack(fill="both", expand=True)
            
            if target_tab:
                try: self.active_frame.tabs.set(target_tab)
                except ValueError: pass 
            
            from config import INSTANCE_CONFIG
            INSTANCE_CONFIG["last_active_story"] = folder_name
            self._save_instance_config_silently()
            
        except Exception as e:
            from config import INSTANCE_CONFIG
            INSTANCE_CONFIG["last_active_story"] = ""
            self._save_instance_config_silently()
            messagebox.showerror("Engine Error", f"Failed to load story: {e}")
            self.open_dashboard()


    def _show_migration_wizard(self, folder_name, univ_root, conflicts, target_tab):
        """Spawns an in-memory wizard to securely merge a standalone story into a Universe."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Universe Integration Wizard")
        dialog.geometry("750x580") # Made slightly wider to comfortably fit the 4th option text
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        from ui.tooltip import center_window_on_parent
        center_window_on_parent(dialog, self)

        main_container = ctk.CTkFrame(dialog, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        steps = []
        current_step = [0]
        
        # --- Step 0: Welcome & Lore Strategy ---
        f0 = ctk.CTkFrame(main_container, fg_color="transparent")
        ctk.CTkLabel(f0, text="Welcome to the Universe", font=("Arial", 20, "bold"), text_color="#B39DDB").pack(pady=(0, 10))
        ctk.CTkLabel(f0, text="This story was moved inside a Shared Universe. To make it playable, we must merge its local memory into the Global World Bible.", wraplength=650, text_color="gray").pack(pady=(0, 20))
        
        ctk.CTkLabel(f0, text="How should we handle Global Rules & Lore?", font=("Arial", 14, "bold")).pack(anchor="w", pady=(10, 2))
        ctk.CTkLabel(f0, text="Tip: Because LLMs read top-to-bottom, rules placed at the bottom often carry more 'weight' (Recency Bias).", font=("Arial", 12, "italic"), text_color="gray").pack(anchor="w", padx=20, pady=(0, 15))
        
        # Default to Genesis if the universe is blank, otherwise default to Prepend
        from config import load_json_safely
        master_setup = load_json_safely(univ_root / "master_setup.json", "master_setup.json")
        is_blank_universe = master_setup.get("lore_and_rules", "").strip() == ""
        
        v_lore = ctk.StringVar(value="genesis" if is_blank_universe else "prepend")
        
        ctk.CTkRadioButton(f0, text="Merge (Local Priority): Universe rules at the top, Local rules at the bottom.", variable=v_lore, value="prepend").pack(anchor="w", padx=20, pady=8)
        ctk.CTkRadioButton(f0, text="Merge (Universe Priority): Local rules at the top, Universe rules at the bottom.", variable=v_lore, value="append").pack(anchor="w", padx=20, pady=8)
        ctk.CTkRadioButton(f0, text="Overwrite Local: Discard Local rules completely and use only Universe rules.", variable=v_lore, value="overwrite").pack(anchor="w", padx=20, pady=8)
        ctk.CTkRadioButton(f0, text="Overwrite Universe (Genesis): Discard Universe rules and replace them with this story's local rules.", variable=v_lore, value="genesis").pack(anchor="w", padx=20, pady=8)
        
        steps.append(f0)
        
        # --- Step 1: Conflict Resolution ---
        f1 = ctk.CTkFrame(main_container, fg_color="transparent")
        
        if not conflicts:
            ctk.CTkLabel(f1, text="Collision Detection", font=("Arial", 18, "bold"), text_color="#4CAF50").pack(pady=(0, 10))
            ctk.CTkLabel(f1, text="Scanning local and global memories for duplicate entities...", wraplength=650, text_color="gray").pack(pady=(0, 10))
        else:
            ctk.CTkLabel(f1, text="Name Collisions Detected", font=("Arial", 18, "bold"), text_color="#F57C00").pack(pady=(0, 10))
            ctk.CTkLabel(f1, text="The following entities in your story have the exact same name as an entity that already exists in the Universe. How do you want to handle them?", wraplength=650, text_color="gray").pack(pady=(0, 10))
        
        scroll = ctk.CTkScrollableFrame(f1, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        resolutions = {} # To hold the Tkinter Vars
        
        if not conflicts:
            ctk.CTkLabel(scroll, text="No collisions found. You are clear to migrate!", font=("Arial", 14, "italic"), text_color="#4CAF50").pack(pady=40)
        else:
            for c in conflicts:
                c_key = f"{c['ledger']}::{c['entity']}"
                row = ctk.CTkFrame(scroll, fg_color="#2B2B2B", corner_radius=6)
                row.pack(fill="x", pady=5)
                
                # Friendly Name
                l_name = "Character" if "char" in c['ledger'] else ("Location" if "loc" in c['ledger'] else ("Artifact" if "art" in c['ledger'] else "Faction"))
                ctk.CTkLabel(row, text=f"{l_name}: {c['entity']}", font=("Arial", 14, "bold")).pack(side="left", padx=10, pady=10)
                
                # Action Choice
                a_var = ctk.StringVar(value="Merge")
                n_var = ctk.StringVar(value=f"{c['entity']} (Local)")
                
                entry = ctk.CTkEntry(row, textvariable=n_var, font=("Arial", 12), width=150)
                
                def on_action_change(val, e_widget=entry):
                    if val == "Rename Local": e_widget.pack(side="right", padx=10)
                    else: e_widget.pack_forget()
                    
                menu = ctk.CTkOptionMenu(row, variable=a_var, values=["Merge", "Rename Local"], width=130, command=on_action_change)
                menu.pack(side="right", padx=10, pady=10)
                
                resolutions[c_key] = {"action_var": a_var, "name_var": n_var}
                
        steps.append(f1)
        
        # --- Navigation Footer ---
        nav_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        nav_frame.pack(fill="x", side="bottom", padx=20, pady=20)
        
        btn_back = ctk.CTkButton(nav_frame, text="< Back", width=100, fg_color="#4A4A4A", hover_color="#333333")
        btn_back.pack(side="left")
        
        btn_next = ctk.CTkButton(nav_frame, text="Next >", width=100, fg_color="#1F6AA5", hover_color="#144870")
        btn_next.pack(side="right")
        
        def update_view():
            idx = current_step[0]
            for f in steps: f.pack_forget()
            steps[idx].pack(fill="both", expand=True)
            
            btn_back.configure(state="normal" if idx > 0 else "disabled")
            
            if idx == len(steps) - 1:
                btn_next.configure(text="Confirm & Migrate", fg_color="#2E7D32", hover_color="#1B5E20")
            else:
                btn_next.configure(text="Next >", fg_color="#1F6AA5", hover_color="#144870")
                
        def go_next():
            idx = current_step[0]
            if idx < len(steps) - 1:
                current_step[0] += 1
                update_view()
            else:
                on_finish()
                
        def go_back():
            idx = current_step[0]
            if idx > 0:
                current_step[0] -= 1
                update_view()
                
        btn_next.configure(command=go_next)
        btn_back.configure(command=go_back)
        
        def on_finish():
            # Build the final dict of string values to pass to the API
            final_res = {}
            for k, vars_dict in resolutions.items():
                act = "rename" if vars_dict["action_var"].get() == "Rename Local" else "merge"
                final_res[k] = {"action": act, "new_name": vars_dict["name_var"].get().strip()}
                
            success, msg = TomeWeaverAPI.commit_migration(folder_name, univ_root, v_lore.get(), final_res)
            
            if success:
                dialog.destroy()
                # Boot the workspace successfully
                self.open_workspace(folder_name, target_tab)
            else:
                messagebox.showerror("Migration Error", f"Failed to migrate story: {msg}")

        update_view()

        
    def _prompt_boilerplate_initialization(self, folder_name):
        """GUI replacement for the console-based setup wizard in main.py."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Initialize New Folder")
        dialog.geometry("400x250")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=f"Folder '{folder_name}' is empty.\nHow would you like to initialize it?", font=("Arial", 14)).pack(pady=20)
        
        mode_var = ctk.StringVar(value="sandbox")
        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack()
        ctk.CTkRadioButton(frame, text="Sandbox (Open-World)", variable=mode_var, value="sandbox").pack(side="left", padx=10)
        ctk.CTkRadioButton(frame, text="Campaign (Plot-Driven)", variable=mode_var, value="campaign").pack(side="left", padx=10)

        def on_init():
            create_boilerplate_files(Path("adventures") / folder_name, mode_var.get())
            dialog.destroy()
            messagebox.showinfo("Success", "Files created! Please edit setup.json before playing.")
            self.open_dashboard()

        ctk.CTkButton(dialog, text="Initialize", command=on_init).pack(pady=30)