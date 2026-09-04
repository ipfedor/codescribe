# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
from __future__ import print_function

import gc
import os

import scriptengine  # type: ignore

from communication_import_export import export_communication
from device_tree_import_export import export_device_tree_siblings
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
    staging_folder = begin_export_folder(src_folder)
    safe_print("Writing to: " + staging_folder)

    for device_obj in get_device_entrypoints(scriptengine.projects.primary):
        device_name = device_obj.get_name()
        safe_print(u"Device: " + device_name)
        # device_name может быть unicode
        device_folder = ensure_unicode_path(os.path.join(staging_folder, device_name))
        os.mkdir(device_folder)

        application = find_application(device_obj)
        application_folder = ensure_unicode_path(os.path.join(device_folder, "application"))
        os.mkdir(application_folder)

        for child_obj in application.get_children():
            safe_print(u"  Exporting: " + child_obj.get_name())
            # No per-child gc.collect(): was slowing export; one collect at end is enough.
            export_child(child_obj, application, application_folder)

        communication = find_communication(device_obj)
        if communication is not None:
            export_communication(communication, device_folder)

        device_tree_exported = export_device_tree_siblings(
            device_obj, device_folder, application, communication
        )

        if communication is None and not device_tree_exported:
            print(
                "Warning: No Communication object and no exportable device-tree siblings "
                "(Ethernet/Modbus/...) for device " + device_obj.get_name()
            )

    # Дополнительная обработка XML (если подключён внешний конвертер).
    # Важно: запускать после того, как все XML уже записаны на диск.
    finalize_export_folder(src_folder, staging_folder)
    # Single GC after all native exports (not after every object).
    gc.collect()
    try_run_codesys_export_converter(src_folder)
    safe_print("Export folder: " + src_folder)
except ExportFolderLockedError:
    raise
except Exception as e:
    # Безопасный вывод исключения
    try:
        print(e)
    except UnicodeEncodeError:
        print(unicode(e).encode('utf-8'))
    raise e

safe_print("Done!")