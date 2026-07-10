# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import errno
import io
import os
import shutil
import subprocess
import sys
import time
import warnings

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message="sys.exc_clear",
)

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

def _try_utf8_mojibake_unicode(text):
    """UTF-8 байты, ошибочно прочитанные как Latin-1 (типичный вывод CODESYS в лог)."""
    if not isinstance(text, unicode):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _to_unicode_path(path):
    if isinstance(path, unicode):
        return path
    if isinstance(path, str):
        try:
            return path.decode("mbcs")
        except UnicodeDecodeError:
            pass
        return fix_encoding(path)
    return path


def resolve_export_folder(path):
    """
    Возвращает путь к папке экспорта так, как она реально существует на диске.
    Исправляет mojibake и расхождение unicode/str из project.path.
    """
    path = _to_unicode_path(path)
    if os.path.isdir(path):
        return path

    fixed = _try_utf8_mojibake_unicode(path)
    if fixed != path and os.path.isdir(fixed):
        return fixed

    parent = os.path.dirname(path)
    base = os.path.basename(path)
    if not os.path.isdir(parent):
        return path

    try:
        entries = os.listdir(parent)
    except Exception:
        return path

    if base in entries and os.path.isdir(os.path.join(parent, base)):
        return os.path.join(parent, base)

    fixed_base = _try_utf8_mojibake_unicode(base)
    candidate = os.path.join(parent, fixed_base)
    if os.path.isdir(candidate):
        return candidate

    for name in entries:
        full = os.path.join(parent, name)
        if not os.path.isdir(full):
            continue
        if _try_utf8_mojibake_unicode(name) == fixed_base or name == fixed_base:
            return full

    return path


def ensure_unicode_path(path):
    """Преобразует байтовый путь в unicode с исправлением кодировки"""
    return resolve_export_folder(path)


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


def _copy_file(src, dst):
    # Copy with overwrite. Keep simple to reduce memory pressure.
    src = ensure_unicode_path(src)
    dst = ensure_unicode_path(dst)
    parent = os.path.dirname(dst)
    if parent and (not os.path.exists(parent)):
        os.makedirs(parent)
    with open(src, "rb") as rf:
        with open(dst, "wb") as wf:
            while True:
                chunk = rf.read(1024 * 1024)
                if not chunk:
                    break
                wf.write(chunk)


def _sync_tree_overwrite(src_root, dst_root):
    """
    Best-effort sync: overwrite/create files from src_root into dst_root.
    Does NOT delete files that disappeared from src_root.
    """
    src_root = ensure_unicode_path(src_root)
    dst_root = ensure_unicode_path(dst_root)
    for root, _dirs, files in os.walk(src_root):
        rel = os.path.relpath(root, src_root)
        dst_dir = dst_root if rel == "." else os.path.join(dst_root, rel)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        for fn in files:
            _copy_file(os.path.join(root, fn), os.path.join(dst_dir, fn))


def finalize_export_folder(target_folder, staging_folder):
    """Move a finished staging export into the target folder."""
    target = ensure_unicode_path(target_folder)
    staging = ensure_unicode_path(staging_folder)
    if not os.path.isdir(staging):
        raise ValueError(u"Staging export folder does not exist: " + staging)
    if os.path.exists(target):
        try:
            _rename_aside_existing_dir(
                target, EXPORT_BACKUP_PREFIX, allow_rmtree_fallback=False
            )
        except (OSError, IOError) as e:
            # Target folder is likely locked. Fallback: sync files into it.
            try:
                safe_print(u"Warning: target locked, attempting file sync overwrite")
                _sync_tree_overwrite(staging, target)
                safe_print(u"Export synced into locked target: " + target)
                return
            except Exception:
                raise ExportFolderLockedError(_export_locked_message(target, staging, e))

    try:
        os.rename(staging, target)
        return
    except (OSError, IOError) as e:
        # Rename denied can still allow file writes (Explorer open, indexers, etc.)
        try:
            safe_print(u"Warning: rename failed, attempting file sync overwrite")
            if not os.path.exists(target):
                os.makedirs(target)
            _sync_tree_overwrite(staging, target)
            safe_print(u"Export synced into target: " + target)
            return
        except Exception:
            raise ExportFolderLockedError(_export_locked_message(target, staging, e))


def _codescribe_repo_roots():
    """
    Корни репозитория codescribe. realpath нужен, когда CODESYS запускает скрипт
    через symlink в Program Files (abspath остаётся в C:\\Program Files\\...).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    roots = []
    for candidate in (os.path.dirname(here),):
        if candidate and candidate not in roots:
            roots.append(candidate)
    try:
        real_here = os.path.dirname(os.path.realpath(__file__))
        real_root = os.path.dirname(real_here)
        if real_root and real_root not in roots:
            roots.append(real_root)
    except Exception:
        pass
    return roots


def _read_converter_path_file(repo_root):
    path_file = os.path.join(repo_root, "converter.path")
    if not os.path.isfile(path_file):
        return None
    try:
        with io.open(path_file, "r", encoding="utf-8") as f:
            line = f.read().strip()
        if line and os.path.isfile(line):
            return ensure_unicode_path(line)
    except Exception:
        pass
    return None


def _converter_script_candidates(repo_root):
    return [
        os.path.normpath(os.path.join(repo_root, "..", "codesys-export-converter", "codesys_export_to_st.py")),
        os.path.normpath(os.path.join(repo_root, "codesys-export-converter", "codesys_export_to_st.py")),
        os.path.normpath(os.path.join(repo_root, "vendor", "codesys-export-converter", "codesys_export_to_st.py")),
        os.path.normpath(os.path.join(repo_root, "external", "codesys-export-converter", "codesys_export_to_st.py")),
    ]


def _find_codesys_export_converter_script():
    """
    Возвращает путь до `codesys_export_to_st.py`, если репозиторий/модуль подключён рядом с codescribe.
    Если не найден — возвращает None.
    """
    env_script = os.environ.get("CODESCRIBE_CONVERTER_SCRIPT", "").strip()
    if env_script:
        try:
            if os.path.isfile(env_script):
                return ensure_unicode_path(env_script)
        except Exception:
            pass

    for repo_root in _codescribe_repo_roots():
        from_file = _read_converter_path_file(repo_root)
        if from_file is not None:
            return from_file

        for p in _converter_script_candidates(repo_root):
            try:
                if os.path.exists(p):
                    return ensure_unicode_path(p)
            except Exception:
                pass
    return None


def _find_converter_launcher_cmd():
    for repo_root in _codescribe_repo_roots():
        bat = os.path.join(repo_root, "run_xml_converter.cmd")
        try:
            if os.path.isfile(bat):
                return ensure_unicode_path(bat)
        except Exception:
            pass
    return None


def _converter_diag_log_path(xml_root_folder):
    return os.path.join(ensure_unicode_path(xml_root_folder), u".codescribe-converter.log")


def _converter_diag_log(xml_root_folder, msg):
    try:
        with io.open(_converter_diag_log_path(xml_root_folder), "a", encoding="utf-8") as f:
            f.write(ensure_unicode_path(msg) + u"\n")
    except Exception:
        pass


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


def _subprocess_env():
    """PATH у GUI-приложений (CODESYS) часто урезан — добавляем типичные пути Python."""
    env = dict(os.environ)
    extra = []
    windir = env.get("WINDIR", r"C:\Windows")
    extra.append(windir)
    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        base = env.get(env_name)
        if not base:
            continue
        py_root = os.path.join(base, "Programs", "Python")
        if os.path.isdir(py_root):
            try:
                for ver in os.listdir(py_root):
                    extra.append(os.path.join(py_root, ver))
                    extra.append(os.path.join(py_root, ver, "Scripts"))
            except Exception:
                pass
    path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(extra) + os.pathsep + path
    return env


def _run_external_command(argv, use_shell=False, via_cmd=False):
    """
    Run a child process from CodeSYS (Py2.7). Tries argv list first, then shell fallback.
  via_cmd: запуск .cmd через cmd.exe /c (надёжнее, чем shell=True из IronPython).
    """
    env = _subprocess_env()
    if via_cmd:
        comspec = env.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        cmd_argv = [comspec, "/c"] + list(argv)
        argv_bytes = _argv_for_subprocess(cmd_argv)
        return subprocess.call(argv_bytes, shell=False, env=env)

    argv_bytes = _argv_for_subprocess(argv)
    if use_shell:
        return subprocess.call(_cmdline_for_shell(argv), shell=True, env=env)
    try:
        return subprocess.call(argv_bytes, shell=False, env=env)
    except (OSError, IOError) as e:
        if getattr(e, "errno", None) != 22:
            raise
    return subprocess.call(_cmdline_for_shell(argv), shell=True, env=env)


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


def _is_ascii_path(path):
    try:
        _to_unicode_path(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _ensure_dir(path):
    path = _to_unicode_path(path)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _converter_sidecar_dir():
    """
    Writable ASCII-only directory for converter sidecar files.
    Avoids tempfile.mkstemp on drive roots (e.g. D:\\) which fails in IronPython.
    """
    env = os.environ.get("CODESCRIBE_TEMP", "").strip()
    if env and _is_ascii_path(env):
        try:
            return _ensure_dir(env)
        except (OSError, IOError):
            pass

    for repo in _codescribe_repo_roots():
        if _is_ascii_path(repo):
            try:
                return _ensure_dir(os.path.join(repo, ".codescribe_tmp"))
            except (OSError, IOError):
                pass

    for env_name in ("TEMP", "TMP"):
        base = os.environ.get(env_name, "")
        if base and _is_ascii_path(base):
            try:
                return _ensure_dir(os.path.join(base, "codescribe"))
            except (OSError, IOError):
                pass

    windir = os.environ.get("WINDIR", r"C:\Windows")
    return _ensure_dir(os.path.join(windir, "Temp", "codescribe"))


def _write_converter_input_path_file(folder_path):
    """
    Записывает unicode-путь экспорта в UTF-8 sidecar-файл в ASCII-каталоге.
    """
    folder_path = ensure_unicode_path(folder_path)
    sidecar_dir = _converter_sidecar_dir()
    base = os.path.join(
        sidecar_dir,
        "codescribe_xml_in_%d_%d" % (os.getpid(), int(time.time() * 1000000)),
    )
    for i in range(100):
        path = base + ("" if i == 0 else "_%d" % i) + ".path"
        if os.path.exists(path):
            continue
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(folder_path)
        return path
    raise IOError(errno.EEXIST, "No usable temporary filename found")


def _env_truthy(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _codescribe_flag_file(filename):
    for root in _codescribe_repo_roots():
        flag = os.path.join(root, filename)
        try:
            if os.path.isfile(flag):
                return True, flag
        except Exception:
            pass
    return False, None


def _converter_extra_args():
    extra = []
    if _should_skip_ld_cfc_in_converter():
        extra.append(u"--skip-ld-cfc")
    return extra


def _converter_command_candidates(script_path, input_path_file, launcher_cmd=None, extra_args=None):
    if extra_args is None:
        extra_args = []
    if script_path is None:
        if launcher_cmd is not None:
            yield [launcher_cmd, input_path_file], "cmd"
        return

    tail = (
        [script_path, "--input-path-file", input_path_file, "--inplace", "--dst-suffix", ".xml.st"]
        + list(extra_args)
    )
    prefixes = []
    for exe in _discover_python3_executables():
        exe_l = exe.lower()
        if exe_l.endswith(os.path.sep + "py.exe"):
            prefixes.append([exe, "-3"])
        else:
            prefixes.append([exe])
    prefixes.extend([["py", "-3"], ["python3"], ["python"]])

    seen = set()
    for prefix in prefixes:
        key = tuple(prefix)
        if key in seen:
            continue
        seen.add(key)
        yield prefix + tail, "exe"

    if launcher_cmd is not None:
        yield [launcher_cmd, input_path_file], "cmd"


def _converter_output_log_path(xml_root_folder):
    return os.path.join(ensure_unicode_path(xml_root_folder), u".codesys-export-converter.log")


def _is_xs_studio_host():
    """
    XS Studio — OEM CODESYS; PDM Kaspersky часто блокирует subprocess из IDE.
    """
    try:
        exe = sys.executable
        if isinstance(exe, str) and not isinstance(exe, unicode):
            try:
                exe = exe.decode("mbcs")
            except UnicodeDecodeError:
                exe = exe.decode("utf-8", "replace")
        if u"xs studio" in exe.lower():
            return True
    except Exception:
        pass
    try:
        for root in _codescribe_repo_roots():
            if u"xs studio" in root.lower():
                return True
    except Exception:
        pass
    return False


def _should_skip_external_converter():
    if _env_truthy("CODESCRIBE_SKIP_XML_CONVERTER"):
        return True, u"CODESCRIBE_SKIP_XML_CONVERTER is set"
    if _env_truthy("CODESCRIBE_FORCE_XML_CONVERTER"):
        return False, u""
    found, path = _codescribe_flag_file(u"skip_external_converter")
    if found:
        return True, u"skip_external_converter flag in " + path
    if _is_xs_studio_host():
        if _env_truthy("CODESCRIBE_SKIP_XML_CONVERTER_ON_XS_STUDIO"):
            return True, u"CODESCRIBE_SKIP_XML_CONVERTER_ON_XS_STUDIO is set (full converter skip)"
        found, path = _codescribe_flag_file(u"skip_xml_converter_xs_studio")
        if found:
            return True, u"skip_xml_converter_xs_studio flag in " + path
    return False, u""


def _should_skip_ld_cfc_in_converter():
    """
    Opt-in: skip XML->ST only for LD/CFC diagrams when export runs inside XS Studio.
    Disabled by default; enable with CODESCRIBE_SKIP_LD_CFC_XS_STUDIO=1 or
    skip_ld_cfc_xs_studio flag file in the codescribe repo root.
    """
    if not _is_xs_studio_host():
        return False
    if _env_truthy("CODESCRIBE_SKIP_LD_CFC_XS_STUDIO"):
        return True
    found, _ = _codescribe_flag_file(u"skip_ld_cfc_xs_studio")
    return found


def _write_manual_converter_launcher(xml_root_folder, script_path):
    """
    Создаёт RUN_XML_CONVERTER.cmd в папке экспорта — запускать вручную вне IDE.
    """
    xml_root_folder = ensure_unicode_path(xml_root_folder)
    path_marker = os.path.join(xml_root_folder, u".codescribe_export_path.txt")
    with io.open(path_marker, "w", encoding="utf-8") as f:
        f.write(xml_root_folder)

    bat_path = os.path.join(xml_root_folder, u"RUN_XML_CONVERTER.cmd")
    script_path = ensure_unicode_path(script_path)
    lines = [
        u"@echo off",
        u"setlocal",
        u'cd /d "%~dp0"',
        u'set "PF=%~dp0.codescribe_export_path.txt"',
        u'if not exist "%PF%" (echo Missing .codescribe_export_path.txt & pause & exit /b 1)',
    ]
    if script_path:
        lines.extend(
            [
                u'if exist "%WINDIR%\\py.exe" (',
                u'  "%WINDIR%\\py.exe" -3 "' + script_path + u'" --input-path-file "%PF%" --inplace --dst-suffix .xml.st',
                u"  goto :done",
                u")",
                u'python "' + script_path + u'" --input-path-file "%PF%" --inplace --dst-suffix .xml.st',
                u":done",
            ]
        )
    else:
        lines.append(u"echo Converter script not found. Set converter.path in codescribe.")
    lines.extend([u"echo.", u"pause"])
    with io.open(bat_path, "w", encoding="utf-8") as f:
        f.write(u"\r\n".join(lines) + u"\r\n")
    return bat_path


def _verify_converter_output(xml_root_folder):
    log_path = _converter_output_log_path(xml_root_folder)
    if not os.path.isfile(log_path):
        return False, u"missing .codesys-export-converter.log (converter did not run)"

    xml_st_count = 0
    try:
        for dp, _, files in os.walk(xml_root_folder):
            for fn in files:
                if fn.lower().endswith(u".xml.st"):
                    xml_st_count += 1
    except Exception as e:
        return False, u"walk failed: " + unicode(e)

    if xml_st_count < 1:
        return False, u"no .xml.st files produced"
    return True, u"xml.st count: " + unicode(xml_st_count)


def try_run_codesys_export_converter(xml_root_folder):
    """
    Пытается запустить внешний конвертер XML->ST (Python 3) по папке экспорта.
    Если репозиторий конвертера не подключён/не найден — ничего не делает.
    """
    xml_root_folder = ensure_unicode_path(xml_root_folder)
    try:
        with io.open(_converter_diag_log_path(xml_root_folder), "w", encoding="utf-8") as f:
            f.write(u"codescribe XML converter log\n")
    except Exception:
        pass

    skip_external, skip_reason = _should_skip_external_converter()
    script_path = _find_codesys_export_converter_script()
    launcher_cmd = _find_converter_launcher_cmd()

    if skip_external:
        msg = u"Info: external XML converter skipped — " + skip_reason
        safe_print(msg)
        _converter_diag_log(xml_root_folder, msg)
        if script_path is not None:
            bat = _write_manual_converter_launcher(xml_root_folder, script_path)
            hint = u"Run manually outside XS Studio: " + bat
            safe_print(hint)
            _converter_diag_log(xml_root_folder, hint)
        return

    if script_path is None and launcher_cmd is None:
        msg = u"Info: codesys-export-converter not connected; skipping extra XML processing"
        safe_print(msg)
        _converter_diag_log(xml_root_folder, msg)
        _converter_diag_log(xml_root_folder, u"repo roots: " + u", ".join(_codescribe_repo_roots()))
        return

    _converter_diag_log(xml_root_folder, u"export folder: " + xml_root_folder)
    if script_path is not None:
        _converter_diag_log(xml_root_folder, u"converter script: " + script_path)
    if launcher_cmd is not None:
        _converter_diag_log(xml_root_folder, u"launcher cmd: " + launcher_cmd)

    input_path_file = None
    converter_extra = _converter_extra_args()
    if converter_extra:
        _converter_diag_log(
            xml_root_folder,
            u"converter args: " + u" ".join(converter_extra),
        )
    try:
        try:
            input_path_file = _write_converter_input_path_file(xml_root_folder)
        except (OSError, IOError) as e:
            err = unicode(e)
            safe_print(u"Warning: could not create converter input path file: " + err)
            _converter_diag_log(xml_root_folder, u"ERROR: " + err)
            return
        _converter_diag_log(xml_root_folder, u"input path file: " + ensure_unicode_path(input_path_file))

        for cmd, launch_mode in _converter_command_candidates(
            script_path, input_path_file, launcher_cmd, converter_extra
        ):
            try:
                cmd_line = u" ".join([unicode(c) for c in cmd])
                safe_print(u"Running extra XML converter: " + cmd_line)
                _converter_diag_log(xml_root_folder, u"RUN: " + cmd_line)
                if launch_mode == "cmd":
                    rc = _run_external_command(cmd, via_cmd=True)
                else:
                    rc = _run_external_command(cmd, use_shell=False)
                    if rc != 0:
                        _converter_diag_log(xml_root_folder, u"retry via shell")
                        rc = _run_external_command(cmd, use_shell=True)
                _converter_diag_log(xml_root_folder, u"exit code: " + unicode(rc))
                if rc != 0:
                    safe_print(u"Warning: converter returned non-zero code: " + unicode(rc))
                    continue
                ok, detail = _verify_converter_output(xml_root_folder)
                _converter_diag_log(xml_root_folder, detail)
                if ok:
                    safe_print(u"Extra XML conversion done (" + detail + u")")
                    _converter_diag_log(xml_root_folder, u"OK")
                    return
                safe_print(u"Warning: converter reported success but " + detail)
                _converter_diag_log(xml_root_folder, u"VERIFY FAILED: " + detail)
            except Exception as e:
                try:
                    err = unicode(e)
                except Exception:
                    err = u"unknown error"
                safe_print(u"Warning: failed to run converter: " + err)
                _converter_diag_log(xml_root_folder, u"ERROR: " + err)
    finally:
        if input_path_file:
            try:
                os.remove(input_path_file)
            except Exception:
                pass

    safe_print(
        u"Warning: could not run codesys-export-converter. "
        u"See .codescribe-converter.log in the export folder."
    )
    _converter_diag_log(xml_root_folder, u"FAILED: all launch attempts exhausted")
