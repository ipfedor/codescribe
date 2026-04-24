# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import io
import os

from communication_import_export import import_communication
from entrypoint import find_application, find_communication, get_device_entrypoints, get_src_folder
from import_export import *
from util import *


def first_word_of_line_iter(f):
    for line in f.readlines():
        # line уже будет unicode, если файл открыт с encoding='utf-8'
        words = line.strip().split()
        if len(words) > 0:
            yield words[0]


def import_directory(dir_path, dir_parent_obj):
    # dir_path может быть unicode, os.listdir вернёт unicode, если путь unicode
    children = os.listdir(dir_path)
    # this is a naughty way to ensure parent POU's are created before their children
    for child in sorted(children, key=lambda x: x.count(".")):
        import_directory_child(child, dir_path, dir_parent_obj)


def import_directory_child(child, dir_path, dir_parent_obj):
    # Extra converter artifacts (sidecar ST for exported XML) must not be imported into CODESYS.
    # Example: `Something.xml.st`
    try:
        if child.lower().endswith(".xml.st"):
            return
    except Exception:
        pass

    full_path = os.path.join(dir_path, child)
    filename, ext = os.path.splitext(child)

    if os.path.isdir(full_path):
        import_folder(child, dir_path, dir_parent_obj, import_directory)

    if filename.endswith(".gvl"):
        if ext == ".xml":
            # this is just here to point out that the xml is imported alongside the st file
            pass
        if ext == ".st":
            import_gvl(child, dir_path, dir_parent_obj, import_directory)
    elif "." in filename:
        # . means some sort of sub POU
        if ext == ".xml":
            import_sub_pou(child, dir_path, dir_parent_obj, import_directory)
        if ext == ".st":
            # currently only methods are exported as ST if possible
            import_method_st(child, dir_path, dir_parent_obj, import_directory)
    else:
        if ext == ".xml":
            import_native(child, dir_path, dir_parent_obj, import_directory)
        if ext == ".st":
            # Have to check for keywords to determine if POU or DUT
            # Используем io.open для корректного чтения UTF-8 файлов
            with io.open(full_path, "r", encoding='utf-8') as f:
                for word in first_word_of_line_iter(f):
                    if word == u"TYPE":
                        import_dut(child, dir_path, dir_parent_obj, import_directory)
                        break  # Нашли тип, дальше не ищем
                    if word in [u"PROGRAM", u"FUNCTION_BLOCK", u"FUNCTION"]:
                        import_pou_st(child, dir_path, dir_parent_obj, import_directory)
                        break


def import_from_files(project):
    src_folder = get_src_folder(project)
    safe_print("Reading from: " + src_folder)
    # Преобразуем путь в байтовую строку для проверки существования
    src_folder_bytes = ensure_unicode_path(src_folder)
    assert_path_exists(src_folder_bytes)

    for device_obj in get_device_entrypoints(project):
        device_folder = os.path.join(src_folder, device_obj.get_name())
        device_folder_bytes = ensure_unicode_path(device_folder)
        assert_path_exists(device_folder_bytes)

        application = find_application(device_obj)
        application_folder = os.path.join(device_folder, "application")
        remove_tracked_objects(application.get_children())
        import_directory(application_folder, application)

        communication = find_communication(device_obj)
        if communication is not None:
            import_communication(communication, device_folder)