"""
TomeWeaver: Main Application Entry Point
----------------------------------------
Launches the engine. If no adventure path is provided via command line, 
it launches the interactive Main Menu Wizard to select or create a story.
"""

import sys
import re
from pathlib import Path
from colorama import Fore, Style, init

from config import load_json_safely, create_boilerplate_files, clear_screen
from sandbox import SandboxEngine
from campaign import CampaignEngine

# Initialize colorama for Windows terminal support
init(autoreset=True)

def sanitize_foldername(name):
    """
    Strips illegal characters for Windows/Linux folder creation and 
    limits the length to prevent OS path-length errors.
    """
    # Remove illegal characters: \ / * ? " < > | :
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    # Limit to 60 characters to be safe
    return clean[:60].strip()

def main_menu_wizard():
    """
    Interactive terminal menu. Lists existing adventures and allows the 
    user to create a new one with a validated folder name.
    Automatically generates a 'Story - [Name].bat' shortcut in the root folder.
    """
    adv_base = Path("adventures")
    adv_base.mkdir(parents=True, exist_ok=True)
    
    # We need the project root to place the .bat file correctly
    root_dir = Path(__file__).resolve().parent.parent
    
    while True:
        clear_screen()
        print(f"{Fore.CYAN}===================================================")
        print(f"{Fore.CYAN}               TomeWeaver Engine                   ")
        print(f"{Fore.CYAN}===================================================\n")
        
        # Scan for existing adventure folders
        folders = [f for f in adv_base.iterdir() if f.is_dir()]
        folders.sort(key=lambda x: x.name)
        
        print(f"{Fore.WHITE}Available Adventures:")
        if not folders:
            print(f"{Style.DIM}  (No adventures found. Time to create one!){Style.RESET_ALL}")
            
        for i, f in enumerate(folders, 1):
            print(f"{Fore.YELLOW}{i}. {Fore.WHITE}{f.name}")
        
        new_opt = len(folders) + 1
        print(f"\n{Fore.GREEN}{new_opt}. [Start a New Story]")
        print(f"{Fore.RED}Q. Quit\n")
        
        choice = input(f"{Fore.CYAN}Select an option: {Style.RESET_ALL}").strip().lower()
        
        if choice == 'q' or choice == 'quit':
            sys.exit(0)
            
        try:
            idx = int(choice)
            if 1 <= idx <= len(folders):
                # Load an existing adventure
                return folders[idx - 1]
            elif idx == new_opt:
                # Create a new adventure
                while True:
                    print(f"\n{Fore.CYAN}Enter a title for your new adventure.")
                    print(f"{Style.DIM}(This will be used as the folder name. Max 60 characters.){Style.RESET_ALL}")
                    title = input(f"{Fore.YELLOW}> {Style.RESET_ALL}").strip()
                    
                    if not title:
                        continue
                        
                    safe_title = sanitize_foldername(title)
                    if not safe_title:
                        print(f"{Fore.RED}Invalid title. Please avoid special characters like \\ / : * ? \" < > |")
                        continue
                        
                    new_dir = adv_base / safe_title
                    if new_dir.exists():
                        print(f"{Fore.RED}An adventure folder named '{safe_title}' already exists! Choose another name.")
                        continue
                        
                    # Create the folder
                    new_dir.mkdir(parents=True)
                    
                    # --- AUTO-GENERATE THE .BAT SHORTCUT ---
                    bat_path = root_dir / f"Story - {safe_title}.bat"
                    bat_content = f"""@echo off
setlocal EnableDelayedExpansion

:: ---------------------------------------------------------
:: STORY SHORTCUT LAUNCHER
:: ---------------------------------------------------------
set "ADVENTURE_FOLDER={safe_title}"
 
title TomeWeaver: %ADVENTURE_FOLDER%

echo ===================================================
echo   Loading Adventure: %ADVENTURE_FOLDER%
echo ===================================================
echo.

if exist "venv\\Scripts\\activate.bat" (
    call venv\\Scripts\\activate.bat
)

python scripts/tome_weaver.py "adventures\\%ADVENTURE_FOLDER%"

if %errorlevel% neq 0 (
    echo.
    echo [SYSTEM] The engine exited with an error.
    pause
) else (
    timeout /t 2 >nul
)

exit /b 0
"""
                    try:
                        with open(bat_path, "w", encoding="utf-8") as f:
                            f.write(bat_content)
                        print(f"{Fore.GREEN}Created launcher: {bat_path.name}")
                    except Exception as e:
                        print(f"{Fore.RED}Failed to create .bat launcher: {e}")
                        
                    return new_dir
        except ValueError:
            continue

if __name__ == "__main__":
    # --- LAUNCH ROUTING ---
    # If a path is provided via command line (Power-user mode), use it.
    # Otherwise, launch the Main Menu Wizard.
    if len(sys.argv) >= 2:
        adv_dir = Path(sys.argv[1]).resolve()
        adv_dir.mkdir(parents=True, exist_ok=True)
    else:
        adv_dir = main_menu_wizard().resolve()
    
    setup_file = adv_dir / "setup.json"
    
    # --- THE NEW ADVENTURE BOILERPLATE WIZARD ---
    # If the folder was just created, it won't have a setup.json.
    if not setup_file.exists():
        clear_screen()
        print(f"{Fore.CYAN}=== NEW ADVENTURE INITIALIZATION ===")
        print(f"{Fore.WHITE}Preparing workspace in: '{adv_dir.name}'\n")
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
        print(f"{Fore.YELLOW}Please open and edit '{adv_dir.name}/setup.json' to build your world.")
        print(f"{Fore.YELLOW}Once you are ready, run the engine again to start playing!")
        
        # Pause so the user can read the success message before the terminal closes
        input(f"\n{Style.DIM}Press Enter to exit...{Style.RESET_ALL}")
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