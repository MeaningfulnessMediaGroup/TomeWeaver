"""
TomeWeaver: Application Entry Point
-----------------------------------
Parses command-line arguments (used by the .bat shortcuts) and 
initializes the backend API. This file serves as the bridge between 
the operating system and your upcoming GUI.
"""

import sys
from pathlib import Path
from colorama import Fore, Style, init

from api import TomeWeaverAPI
from config import create_boilerplate_files

# Initialize colorama for Windows terminal support
init(autoreset=True)

if __name__ == "__main__":
    # --- LAUNCH ROUTING ---
    # If a path is provided via command line (e.g., from the .bat shortcut)
    if len(sys.argv) >= 2:
        adv_dir = Path(sys.argv[1]).resolve()
        adv_dir.mkdir(parents=True, exist_ok=True)
        folder_name = adv_dir.name
        
        setup_file = adv_dir / "setup.json"
        
        # --- THE BOILERPLATE SAFETY NET ---
        # Preserved from your original script: If the folder exists but has no setup.json, 
        # it means the user manually created a folder. We must initialize it.
        if not setup_file.exists():
            print(f"{Fore.CYAN}=== NEW ADVENTURE INITIALIZATION ===")
            print(f"{Fore.WHITE}Preparing workspace in: '{folder_name}'\n")
            print(f"{Fore.YELLOW}1. Sandbox Mode {Style.DIM}(Open-world, player-driven, manual chapters)")
            print(f"{Fore.YELLOW}2. Campaign Mode {Style.DIM}(Plot-driven, predefined goals, tracked inventory)\n")
            
            mode = "sandbox"
            while True:
                choice = input(f"{Fore.CYAN}Select a story mode (1-2): {Style.RESET_ALL}").strip()
                if choice == '1':
                    mode = 'sandbox'
                    break
                elif choice == '2':
                    mode = 'campaign'
                    break
                else:
                    print(f"{Fore.RED}Invalid choice. Please enter 1 or 2.")
                    
            create_boilerplate_files(adv_dir, mode)
            print(f"\n{Fore.GREEN}Success! Boilerplate files created for {mode.upper()} mode.")
            print(f"{Fore.YELLOW}Please open and edit '{folder_name}/setup.json' to build your world.")
            
            # The engine cannot run until the user configures the setup, so we exit safely.
            input(f"\n{Style.DIM}Press Enter to exit...{Style.RESET_ALL}")
            sys.exit(0)

        # --- ENGINE INITIALIZATION ---
        try:
            print(f"{Fore.CYAN}Booting TomeWeaver API for '{folder_name}'...")
            
            # 1. Instantiate the correct engine via the API
            engine = TomeWeaverAPI.load_engine(folder_name)
            
            # 2. Load the state (replaces the old engine.play() call)
            current_state = engine.initialize_game()
            
            print(f"{Fore.GREEN}Engine loaded successfully.{Style.RESET_ALL}")
            
            # ---------------------------------------------------------
            # GUI HANDOFF POINT
            # ---------------------------------------------------------
            # At this exact moment, the Python backend is fully initialized.
            # When you build your UI, you will pass the 'engine' object 
            # into your GUI framework here.
            #
            # Example: 
            # app = TomeWeaverGUI(engine)
            # app.mainloop()
            # ---------------------------------------------------------
            
        except Exception as e:
            print(f"{Fore.RED}\nFatal Error during engine boot: {e}{Style.RESET_ALL}")
            input("Press Enter to exit...")
            sys.exit(1)
            
    else:
        # If launched without a shortcut (e.g., just double-clicking main.py)
        # This will eventually launch your UI Dashboard.
        print(f"{Fore.CYAN}TomeWeaver API Backend Online.{Style.RESET_ALL}")
        print("Waiting for UI Dashboard implementation...")
        input("Press Enter to exit...")