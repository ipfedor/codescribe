# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import os
import shutil
import subprocess
import sys
import time

import scriptengine  # type: ignore

from object_type import get_object_type


def print_python_version():
    print("Python version: " + sys.version)


def assert_project_open():
    if scriptengine.projects.primary is None:
        raise ValueError("You must have a project open!")


def assert_path_exists(path):
    # В Python 2.7 os.path.exists корректно работает с unicode-строками,
    # но для надёжности явно преобразуем в байтовую строку, если это unicode
    if isinstance(path, unicode):
        path = path.encode('utf-8')
    if not os.path.exists(path):
        raise ValueError("Path " + path + " does not exist")


def first_or_none(lst):
    return next(iter(lst), None)


def first_of_type_or_error(lst, obj_type, err):
    for obj in lst:
        if get_object_type(obj) == obj_type:
            return obj
    raise ValueError(err)


def first_of_type_or_none(lst, obj_type):
    for obj in lst:
        if get_object_type(obj) == obj_type:
            return obj
    return None


def first_or_error(lst, err):
    try:
        return next(iter(lst))
    except StopIteration:
        raise ValueError(err)

def safe_print(msg):
    """Безопасная печать строки с поддержкой UTF-8 в Python 2.7"""
    if isinstance(msg, unicode):
        msg = msg.encode('utf-8')
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.decode('utf-8').encode('utf-8'))

def fix_encoding(name):
    """
    Исправляет Mojibake: если name — это байтовая строка, которая выглядит как
    UTF-8, но ошибочно интерпретируется как Latin-1, преобразует в правильную Unicode.
    """
    if isinstance(name, unicode):
        return name
    # Пытаемся перекодировать из Latin-1 в UTF-8
    try:
        # Сначала декодируем как Latin-1 (получаем искажённые символы), затем кодируем в UTF-8 и декодируем в Unicode
        return name.decode('latin-1').encode('utf-8').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # Если не получилось, возвращаем как есть
        return name.decode('utf-8', errors='replace')

def ensure_unicode_path(path):
    """Преобразует байтовый путь в unicode с исправлением кодировки"""
    if isinstance(path, str) and not isinstance(path, unicode):
        path = fix_encoding(path)
    return path


EXPORT_STAGING_SUFFIX = u".codescribe_export_staging"
EXPORT_DISCARD_PREFIX = u".codescribe_discard_"
EXPORT_BACKUP_PREFIX = u".codescribe_backup_"


class ExportFolderLockedError(EnvironmentError):
    """Target export directory could not be replaced (often locked on Windows)."""


def _rmtree_onerror(func, path, exc_info):
    # Help shutil.rmtree with read-only files (common in git checkouts on Windows).
    import stat

    exc = exc_info[1]
    if isinstance(exc, EnvironmentError) and os.path.exists(path):
        os.chmod(path, stat.S_IWRITE)
        func(path)
        return
    raise exc


def _rmtree_retry(path, retries=3, delay_sec=0.5):
    path = ensure_unicode_path(path)
    last_err = None
    for attempt in range(retries):
        try:
            if os.path.exists(path):
                shutil.rmtree(path, onerror=_rmtree_onerror)
            return
        except (OSError, IOError) as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(delay_sec)
    raise last_err


def _export_dir_timestamp():
    return time.strftime("%Y%m%d%H%M%S")


def _rename_aside_existing_dir(path, label_prefix, allow_rmtree_fallback=True):
    """
    Move an existing directory aside instead of deleting it.

    Mass delete (shutil.rmtree) on large exports from inside CodeSYS often triggers
    System.OutOfMemoryException in the .NET host.
    """
    path = ensure_unicode_path(path)
    if not os.path.exists(path):
        return None
    aside = path + label_prefix + _export_dir_timestamp()
    try:
        os.rename(path, aside)
        safe_print(u"Moved aside: " + aside)
        return aside
    except (OSError, IOError):
        if not allow_rmtree_fallback:
            raise
        safe_print(u"Warning: rename failed, falling back to rmtree for: " + path)
        _rmtree_retry(path)
        return None


def begin_export_folder(target_folder):
    """
    Prepare a writable staging directory for export.

    Export scripts write here first; finalize_export_folder() swaps it into
    target_folder when possible. This avoids losing the whole export when the
    destination folder is locked (Explorer, IDE, git, antivirus, etc.).
    """
    target = ensure_unicode_path(target_folder)
    staging = target + EXPORT_STAGING_SUFFIX
    _rename_aside_existing_dir(staging, EXPORT_DISCARD_PREFIX)
    os.mkdir(staging)
    return staging


def _export_locked_message(target, staging, err):
    return (
        u"Cannot replace export folder (it may be locked by another program):\n"
        u"  Target: " + target + u"\n"
        u"  Completed export saved at: " + staging + u"\n"
        u"  Error: " + unicode(err) + u"\n\n"
        u"Close programs using the target folder (Explorer window, IDE, git client, "
        u"antivirus scan), then either re-run export or manually replace the target "
        u"folder with the staging folder above."
    )


def finalize_export_folder(target_folder, staging_folder):
    """Move a finished staging export into the target folder."""
    target = ensure_unicode_path(target_folder)
    staging = ensure_unicode_path(staging_folder)
    if not os.path.isdir(staging):
        raise ValueError(u"Staging export folder does not exist: " + staging)
    if os.path.exists(target):
        try:
            _rename_aside_existing_dir(target, EXPORT_BACKUP_PREFIX, allow_rmtree_fallback=False)
        except (OSError, IOError) as e:
            raise ExportFolderLockedError(_export_locked_message(target, staging, e))
    try:
        os.rename(staging, target)
    except (OSError, IOError) as e:
        raise ExportFolderLockedError(_export_locked_message(target, staging, e))


def _find_codesys_export_converter_script():
    """
    Возвращает путь до `codesys_export_to_st.py`, если репозиторий/модуль подключён рядом с codescribe.
    Если не найден — возвращает None.
    """
    # `.../codescribe/src/util.py` -> repo root `.../codescribe`
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)

    candidates = [
        os.path.normpath(os.path.join(repo_root, "..", "codesys-export-converter", "codesys_export_to_st.py")),
        os.path.normpath(os.path.join(repo_root, "codesys-export-converter", "codesys_export_to_st.py")),
        os.path.normpath(os.path.join(repo_root, "vendor", "codesys-export-converter", "codesys_export_to_st.py")),
        os.path.normpath(os.path.join(repo_root, "external", "codesys-export-converter", "codesys_export_to_st.py")),
    ]

    for p in candidates:
        try:
            if os.path.exists(p):
                return ensure_unicode_path(p)
        except Exception:
            pass
    return None


def _argv_for_subprocess(argv):
    """
    Python 2.7 on Windows: subprocess requires byte/str args, not unicode (EINVAL / errno 22).
    """
    out = []
    for arg in argv:
        if isinstance(arg, unicode):
            try:
                arg = arg.encode("mbcs")
            except UnicodeEncodeError:
                arg = arg.encode("utf-8")
        elif not isinstance(arg, str):
            arg = str(arg)
        out.append(arg)
    return out


def _cmdline_for_shell(argv):
    parts = []
    for arg in _argv_for_subprocess(argv):
        if " " in arg or '"' in arg:
            parts.append('"' + arg.replace('"', '""') + '"')
        else:
            parts.append(arg)
    return " ".join(parts)


def _run_external_command(argv):
    """
    Run a child process from CodeSYS (Py2.7). Tries argv list first, then shell fallback.
    """
    argv_bytes = _argv_for_subprocess(argv)
    try:
        return subprocess.call(argv_bytes)
    except (OSError, IOError) as e:
        if getattr(e, "errno", None) != 22:
            raise
    return subprocess.call(_cmdline_for_shell(argv), shell=True)


def _discover_python3_executables():
    found = []
    seen = set()

    def add(exe):
        exe = ensure_unicode_path(exe)
        key = exe.lower()
        if key in seen:
            return
        if os.path.isfile(exe):
            seen.add(key)
            found.append(exe)

    windir = os.environ.get("WINDIR", r"C:\Windows")
    add(os.path.join(windir, "py.exe"))

    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        py_root = os.path.join(base, "Programs", "Python")
        if not os.path.isdir(py_root):
            continue
        try:
            versions = sorted(os.listdir(py_root), reverse=True)
        except Exception:
            continue
        for ver in versions:
            add(os.path.join(py_root, ver, "python.exe"))

    return found


def _converter_command_candidates(script_path, xml_root_folder):
    tail = [script_path, xml_root_folder, "--inplace", "--dst-suffix", ".xml.st"]
    prefixes = [
        ["py", "-3"],
        ["python3"],
        ["python"],
    ]
    for exe in _discover_python3_executables():
        exe_l = exe.lower()
        if exe_l.endswith(os.path.sep + "py.exe"):
            prefixes.append([exe, "-3"])
        else:
            prefixes.append([exe])

    seen = set()
    for prefix in prefixes:
        key = tuple(prefix)
        if key in seen:
            continue
        seen.add(key)
        yield prefix + tail


def try_run_codesys_export_converter(xml_root_folder):
    """
    Пытается запустить внешний конвертер XML->ST (Python 3) по папке экспорта.
    Если репозиторий конвертера не подключён/не найден — ничего не делает.
    """
    if os.environ.get("CODESCRIBE_SKIP_XML_CONVERTER", "").strip().lower() in ("1", "true", "yes"):
        safe_print(u"Info: XML converter skipped (CODESCRIBE_SKIP_XML_CONVERTER is set)")
        return

    script_path = _find_codesys_export_converter_script()
    if script_path is None:
        safe_print(u"Info: codesys-export-converter not connected; skipping extra XML processing")
        return

    xml_root_folder = ensure_unicode_path(xml_root_folder)

    for cmd in _converter_command_candidates(script_path, xml_root_folder):
        try:
            safe_print(u"Running extra XML converter: " + u" ".join([unicode(c) for c in cmd]))
            rc = _run_external_command(cmd)
            if rc == 0:
                safe_print(u"Extra XML conversion done")
                return
            safe_print(u"Warning: converter returned non-zero code: " + unicode(rc))
        except Exception as e:
            try:
                safe_print(u"Warning: failed to run converter: " + unicode(e))
            except Exception:
                safe_print(u"Warning: failed to run converter")

    safe_print(
        u"Warning: could not run codesys-export-converter. "
        u"Install Python 3 (py -3) or run manually:\n  py -3 \"" + script_path + u"\" \"" + xml_root_folder + u"\" --inplace --dst-suffix .xml.st"
    )
