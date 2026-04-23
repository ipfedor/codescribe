# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
from __future__ import print_function

import os
import shutil

import scriptengine  # type: ignore

from communication_import_export import export_communication
from entrypoint import find_application, find_communication, get_device_entrypoints, get_src_folder
from import_export import OBJECT_TYPE_TO_EXPORT_FUNCTION, write_native
from object_type import ObjectType, get_object_type
from util import *


def export_child(child_obj, parent_obj, parent_folder_path):
    child_obj_type = get_object_type(child_obj)
    export_fn = OBJECT_TYPE_TO_EXPORT_FUNCTION.get(child_obj_type)
    if export_fn is not None:
        export_fn(child_obj, parent_obj, parent_folder_path, export_child)
        return

    if child_obj_type == ObjectType.UNKNOWN:
        try:
            name = child_obj.get_name()
            if isinstance(name, str) and not isinstance(name, unicode):
                name = fix_encoding(name)
            export_path = os.path.join(parent_folder_path, name + u".xml")
            write_native(child_obj, export_path, recursive=False)
        except Exception:
            pass

    for c in child_obj.get_children():
        export_child(c, child_obj, parent_folder_path)


try:
    print_python_version()
    assert_project_open()

    src_folder = get_src_folder(scriptengine.projects.primary)
    safe_print("Writing to: " + src_folder)

    # Безопасное удаление и создание папки
    src_folder_bytes = ensure_unicode_path(src_folder)
    if os.path.exists(src_folder_bytes):
        shutil.rmtree(src_folder_bytes)
    os.mkdir(src_folder_bytes)

    for device_obj in get_device_entrypoints(scriptengine.projects.primary):
        device_name = device_obj.get_name()
        # device_name может быть unicode
        device_folder = os.path.join(src_folder, device_name)
        device_folder_bytes = ensure_unicode_path(device_folder)
        os.mkdir(device_folder_bytes)

        application = find_application(device_obj)
        application_folder = os.path.join(device_folder, "application")
        application_folder_bytes = ensure_unicode_path(application_folder)
        os.mkdir(application_folder_bytes)

        for child_obj in application.get_children():
            export_child(child_obj, application, application_folder)

        communication = find_communication(device_obj)
        if communication is not None:
            export_communication(communication, device_folder)
        else:
            print("Warning: No Communication object found for device " + device_obj.get_name())

    # Дополнительная обработка XML (если подключён внешний конвертер).
    # Важно: запускать после того, как все XML уже записаны на диск.
    try_run_codesys_export_converter(src_folder)
except Exception as e:
    # Безопасный вывод исключения
    try:
        print(e)
    except UnicodeEncodeError:
        print(unicode(e).encode('utf-8'))
    raise e

safe_print("Done!")