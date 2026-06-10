"""
Needs to be run as administrator!
Use install.bat: Right click -> "Run as administrator"
"""

import ctypes
from pathlib import Path
import shutil

from typing import TypeVar


class TerminalColours:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_fail(msg: str):
    print(msg, end="\n\n")
    # print(TerminalColours.FAIL + msg + TerminalColours.ENDC)


def print_warning(msg: str):
    print(msg, end="\n\n")
    # print(TerminalColours.WARNING + msg + TerminalColours.ENDC)


def print_ok(msg: str):
    print(msg, end="\n\n")
    # print(TerminalColours.OKBLUE + msg + TerminalColours.ENDC)


T = TypeVar("T")


def select_option(options: list[T], *, none_msg: str, one_msg: str, many_msg: str) -> T:
    if len(options) < 1:
        print_fail(none_msg)
        exit(0)
    elif len(options) == 1:
        print_ok(one_msg.format(single_option=options[0]))
        return options[0]
    else:
        while True:
            print_ok(many_msg.format(num_options=len(options)))
            for i, option in enumerate(options):
                print(f"({i+1}) {str(option)}")
            selection = input("Selection: ")
            try:
                selection = int(selection) - 1
                if selection < 0:
                    raise ValueError()
                return options[selection]
            except (ValueError, IndexError):
                print_fail("Unknown selection!\n")


def find_repo_config_json(repo_path: Path) -> Path:
    config_json = repo_path / "config.json"
    if not config_json.exists():
        print_fail(f"ERROR: expecting to find config.json at {config_json}")
        exit(0)

    return config_json


def _looks_like_codesys_oem(name: str) -> bool:
    upper = name.upper()
    markers = (
        "CODESYS",
        "XS STUDIO",
        "XSS STUDIO",
        "XSSTUDIO",
        "XCP",
        "XINJE",
        "信捷",
    )
    return any(marker in upper for marker in markers)


def find_codesys_install_paths() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path).lower()
        if key in seen:
            return
        if path.is_dir():
            seen.add(key)
            roots.append(path)

    search_bases = [
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("D:/Program Files"),
    ]
    for base in search_bases:
        if not base.is_dir():
            continue
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and _looks_like_codesys_oem(child.name):
                add(child)

    return sorted(roots, key=lambda p: p.name.lower())


def resolve_codesys_root(install_root: Path) -> Path | None:
    """
    OEM-оболочки (CODESYS, XS Studio/xS Studio) обычно имеют подкаталог CODESYS.
    Иногда корень установки уже является CODESYS-каталогом.
    """
    if (install_root / "Common" / "CODESYS.exe").is_file():
        return install_root
    codesys_path = install_root / "CODESYS"
    if codesys_path.is_dir():
        return codesys_path
    if (install_root / "Script Commands").is_dir():
        return install_root
    return None


def get_or_create_script_path(install_root: Path) -> Path:
    codesys_path = resolve_codesys_root(install_root)
    if codesys_path is None:
        print_fail(f"ERROR: CODESYS/XS Studio layout not found under: {install_root}")
        exit(0)

    script_path = codesys_path / "Script Commands"
    if not script_path.exists():
        print_ok(f"Creating directory: {script_path}")
        script_path.mkdir(parents=True)

    if not script_path.is_dir():
        print_fail(f"ERROR: expected to be a directory: {script_path}")
        exit(0)

    return script_path


def rename_or_get_config_json_destination(script_path: Path) -> Path:
    config_json = script_path / "config.json"
    if config_json.exists():
        print_warning(f"WARNING: existing config found")
        success = False
        for i in range(100):
            try:
                backup_json = f"config.backup_{i}.json"
                backup_path = config_json.parent / backup_json
                config_json.rename(backup_path)
                print_ok(f"Renamed config.json to {backup_json}")
                success = True
                break
            except FileExistsError:
                pass

        if not success:
            print_fail(f"ERROR: file already exists: {backup_path}.")
            print_fail(f"Please remove some backups in {backup_path.parent}")
            exit(0)

    return config_json


def copy_config_json(repo_config: Path, config_destination: Path):
    try:
        shutil.copy(repo_config, config_destination)
    except Exception as e:
        print_fail(f"ERROR copying config json: {e}")
        exit(0)

    print_ok(f"SUCCESS: config written to {config_destination}")


def symlink_install_repo_folder(repo: Path, destination: Path):
    symlink_folder = destination / "codescribe"
    kdll = ctypes.windll.LoadLibrary("kernel32.dll")
    flag_is_a_directory = 1
    kdll.CreateSymbolicLinkW(str(symlink_folder), str(repo), flag_is_a_directory)


if __name__ == "__main__":
    try:
        print()
        repo_path = Path(__file__).parent
        repo_config_json = find_repo_config_json(repo_path)

        install_paths = find_codesys_install_paths()
        install_path = select_option(
            install_paths,
            none_msg="No CODESYS / XS Studio install paths found!",
            one_msg="IDE install path found: {single_option}",
            many_msg="{num_options} IDE install paths found (CODESYS / XS Studio):",
        )

        script_path = get_or_create_script_path(install_path)
        config_json_destination = rename_or_get_config_json_destination(script_path)

        symlink_install_repo_folder(repo_path, script_path)
        copy_config_json(repo_config_json, config_json_destination)
    except PermissionError:
        print_fail(f"Permission error! Are you running as administrator?")
        exit(0)
