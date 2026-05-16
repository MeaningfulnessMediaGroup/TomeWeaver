import sys
from pathlib import Path
from colorama import Fore, Style, init

from config import load_json_safely, create_boilerplate_files, clear_screen
from sandbox import SandboxEngine
from campaign import CampaignEngine

init(autoreset=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"{Fore.RED}Usage: python scripts/tome_weaver.py <adventure_folder_path>")
        sys.exit(1)
        
    adv_dir = Path(sys.argv[1]).resolve()
    adv_dir.mkdir(parents=True, exist_ok=True)
    
    setup_file = adv_dir / "setup.json"
    
    # --- THE NEW INTERACTIVE SETUP WIZARD ---
    if not setup_file.exists():
        clear_screen()
        print(f"{Fore.CYAN}=== NEW ADVENTURE FOUND ===")
        print(f"{Fore.WHITE}It looks like you are starting a new story in '{adv_dir.name}'.\n")
        print(f"{Fore.YELLOW}1. Sandbox Mode {Style.DIM}(Never-ending, player-driven, manual chapters)")
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
        print(f"{Fore.YELLOW}Please open and edit the new '{adv_dir.name}/setup.json' to build your world.")
        print(f"{Fore.YELLOW}Once you are ready, run this script again to start playing!")
        sys.exit(0)

    # --- NORMAL GAME LAUNCH ---
    setup_data = load_json_safely(setup_file, "setup.json")
    mode = setup_data.get("mode", "sandbox").lower()
    
    try:
        if mode == "campaign":
            engine = CampaignEngine(adv_dir, setup_data)
            engine.play()
        else:
            engine = SandboxEngine(adv_dir, setup_data)
            engine.play()
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user. Progress safely stored. Goodbye!")
        sys.exit(0)