import subprocess
import sys
from scanner import get_unused_packages

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"

def size_color(size):
    if size > 100 * 1024 * 1024:
        return RED
    if size > 10 * 1024 * 1024:
        return YELLOW
    return GREEN

def main():
    print(f"{BOLD}Scanning for unused packages...{RESET}\n")
    unused = get_unused_packages()

    if not unused:
        print(f"{GREEN}No unused packages found.{RESET}")
        return

    total_size = sum(pkg['size'] for pkg in unused)

    print(f"  {BLUE}{'#':>3}{RESET} | {BLUE}{'Package':25}{RESET} | {BLUE}{'Size':>10}{RESET} | {BLUE}{'Type':8}{RESET} | {BLUE}{'Description'}{RESET}")
    print(f"  {DIM}{'-'*78}{RESET}")
    for i, pkg in enumerate(unused):
        desc = pkg['desc']
        display_desc = (desc[:35] + '...') if len(desc) > 35 else desc
        size_str = format_size(pkg['size'])
        sz_color = size_color(pkg['size'])
        pkg_type = f"{RED}AUR{RESET}" if pkg['is_aur'] else f"{GREEN}repo{RESET}"
        print(f"  {i:3d} | {pkg['name']:25} | {sz_color}{size_str:>10}{RESET} | {pkg_type:8} | {display_desc}")
    print(f"\n  {BOLD}Total reclaimable:{RESET} {CYAN}{format_size(total_size)}{RESET}")
    print(f"  {DIM}({len(unused)} packages){RESET}")

    choice = input(f"\n{BOLD}Enter numbers to uninstall (e.g., 0, 2, 5) or 'n' to abort:{RESET} ")
    if choice.lower() == 'n':
        print(f"\n{YELLOW}Cleanup aborted.{RESET}")
        return

    try:
        indices = [int(i.strip()) for i in choice.split(',')]
        selected = [unused[i] for i in indices if 0 <= i < len(unused)]

        if not selected:
            print(f"{RED}No valid packages selected.{RESET}")
            return

        print(f"\n  {YELLOW}Packages to remove:{RESET}")
        sel_size = 0
        for pkg in selected:
            sel_size += pkg['size']
            badge = f"{RED}[aur]{RESET}" if pkg['is_aur'] else f"{GREEN}[repo]{RESET}"
            print(f"    {badge} {pkg['name']:25} {DIM}{format_size(pkg['size'])}{RESET}")
        print(f"    {DIM}Total: {format_size(sel_size)}{RESET}")

        confirm = input(f"\n{RED}Proceed with uninstall? (y/N):{RESET} ")
        if confirm.lower() != 'y':
            print(f"{YELLOW}Cleanup aborted.{RESET}")
            return

        names = [pkg['name'] for pkg in selected]
        subprocess.run(["sudo", "pacman", "-Rns", "--noconfirm"] + names, check=True)
        print(f"\n{GREEN}Cleanup complete.{RESET}")
    except subprocess.CalledProcessError:
        print(f"{RED}Failed to uninstall some packages.{RESET}")
    except ValueError:
        print(f"{RED}Invalid input. Cleanup aborted.{RESET}")

if __name__ == "__main__":
    main()
