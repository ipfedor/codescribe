# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import gc
import os
import re

from import_export import (
    read_native_under_parent,
    write_native,
    write_native_preserving_io_maps,
)
from object_type import ObjectType
from util import *

NO_EXPORT_FOLDER_NAME = u"_NO_EXPORT"


def _natural_sort_key(name):
    parts = re.split(ur"(\d+)", name)
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return key


def no_export_folder_exists(communication_obj):
    return first_of_type_or_none(communication_obj.find(NO_EXPORT_FOLDER_NAME), ObjectType.FOLDER) is not None


def export_communication(communication_obj, device_folder):
    """
    Export communication is hardcoded to create folders for the top level devices inside the communication object, and
    then do a native recursive export for any devices under those top level devices.
    """
    if no_export_folder_exists(communication_obj):
        return

    communication_folder = os.path.join(device_folder, "communication")
    communication_folder_bytes = ensure_unicode_path(communication_folder)
    os.mkdir(communication_folder_bytes)

    for top_level_device in communication_obj.get_children():
        top_level_device_folder = os.path.join(communication_folder, top_level_device.get_name())
        top_level_device_folder_bytes = ensure_unicode_path(top_level_device_folder)
        os.mkdir(top_level_device_folder_bytes)
        for child_device in top_level_device.get_children():
            child_name = child_device.get_name()
            # child_name может быть unicode, но write_native ожидает путь как строку
            # преобразуем в байтовую строку, если необходимо
            export_path = os.path.join(top_level_device_folder, child_name + u".xml")
            export_path_bytes = ensure_unicode_path(export_path)
            write_native_preserving_io_maps(
                child_device, export_path_bytes, recursive=True
            )
            gc.collect()


def import_communication(communication_obj, device_folder, host_device_obj=None):
    """
    Re-import communication children. ``host_device_obj`` is the PLC device used
    as HostObjectGuid for I/O mappings (optional; falls back to communication parent).
    """
    communication_folder = os.path.join(device_folder, "communication")
    communication_folder_bytes = ensure_unicode_path(communication_folder)
    if not os.path.exists(communication_folder_bytes):
        return

    if no_export_folder_exists(communication_obj):
        return

    if host_device_obj is None:
        try:
            host_device_obj = communication_obj.get_parent()
        except Exception:
            host_device_obj = None

    # Per-parent clear+import (same isolation as device-tree siblings).
    for name in sorted(os.listdir(communication_folder_bytes), key=_natural_sort_key):
        full_path = ensure_unicode_path(os.path.join(communication_folder_bytes, name))
        if not os.path.isdir(full_path):
            continue

        top_level_device = first_of_type_or_none(
            communication_obj.find(name), ObjectType.DEVICE
        )
        if top_level_device is None:
            top_level_device = first_or_none(communication_obj.find(name))
        if top_level_device is None:
            safe_print(
                u"Skipping communication folder "
                + name
                + u"/ (no matching device in project)"
            )
            continue

        safe_print(u"  Communication clear+import: " + name + u"/")
        for child in list(top_level_device.get_children()):
            child.remove()

        try:
            for child_name in sorted(os.listdir(full_path), key=_natural_sort_key):
                _, ext = os.path.splitext(child_name)
                if ext != u".xml":
                    continue
                import_file_path = ensure_unicode_path(os.path.join(full_path, child_name))
                safe_print(
                    u"  Communication import: "
                    + name
                    + u"/"
                    + child_name
                )
                read_native_under_parent(
                    import_file_path, top_level_device, host_device_obj
                )
        except Exception as e:
            safe_print(
                u"Warning: communication import failed for "
                + name
                + u": "
                + unicode(e)
            )


def remove_tracked_communication_devices(communication_obj):
    if no_export_folder_exists(communication_obj):
        return

    # remove all children from top level devices
    for top_level_device in communication_obj.get_children():
        for child in list(top_level_device.get_children()):
            child.remove()
