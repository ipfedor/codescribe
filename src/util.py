# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import os
import subprocess
import sys

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
                return p
        except Exception:
            pass
    return None


def try_run_codesys_export_converter(xml_root_folder):
    """
    Пытается запустить внешний конвертер XML->ST (Python 3) по папке экспорта.
    Если репозиторий конвертера не подключён/не найден — ничего не делает.
    """
    script_path = _find_codesys_export_converter_script()
    if script_path is None:
        safe_print(u"Info: codesys-export-converter not connected; skipping extra XML processing")
        return

    xml_root_folder = ensure_unicode_path(xml_root_folder)

    # Варианты запуска Python 3 на Windows:
    # - `py -3` (предпочтительно)
    # - `python` (если python3 стоит по умолчанию в PATH)
    cmd_candidates = [
        ["py", "-3", script_path, xml_root_folder, "--inplace", "--dst-suffix", ".xml.st"],
        ["python", script_path, xml_root_folder, "--inplace", "--dst-suffix", ".xml.st"],
    ]

    for cmd in cmd_candidates:
        try:
            safe_print(u"Running extra XML converter: " + u" ".join([unicode(c) for c in cmd]))
            rc = subprocess.call(cmd)
            if rc == 0:
                safe_print(u"Extra XML conversion done")
                return
            safe_print(u"Warning: converter returned non-zero code: " + unicode(rc))
        except Exception as e:
            try:
                safe_print(u"Warning: failed to run converter: " + unicode(e))
            except Exception:
                safe_print(u"Warning: failed to run converter")

    safe_print(u"Warning: could not run codesys-export-converter (python3 not found?)")
