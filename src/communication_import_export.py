# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import os

from import_export import write_native
from object_type import ObjectType
from util import *

NO_EXPORT_FOLDER_NAME = u"_NO_EXPORT"


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
            write_native(
                child_device, export_path_bytes, recursive=True
            )


def import_communication(communication_obj, device_folder):
    communication_folder = os.path.join(device_folder, "communication")
    communication_folder_bytes = ensure_unicode_path(communication_folder)
    if not os.path.exists(communication_folder_bytes):
        return

    remove_tracked_communication_devices(communication_obj)

    # for top level folders inside the communcation folder, do a native import on the corresponding communication device
    # os.listdir вернёт unicode, если путь unicode
    for name in os.listdir(communication_folder):
        full_path = os.path.join(communication_folder, name)
        full_path_bytes = ensure_unicode_path(full_path)
        if not os.path.isdir(full_path_bytes):
            continue

        top_level_device = first_of_type_or_error(
            communication_obj.find(name), ObjectType.DEVICE,
            u"Cannot find communication device with name " + name
        )
        for child_name in os.listdir(full_path):
            _, ext = os.path.splitext(child_name)
            if ext == u".xml":
                import_file_path = os.path.join(full_path, child_name)
                import_file_path_bytes = ensure_unicode_path(import_file_path)
                top_level_device.import_native(import_file_path_bytes)


def remove_tracked_communication_devices(communication_obj):
    if no_export_folder_exists(communication_obj):
        return

    # remove all children from top level devices
    for top_level_device in communication_obj.get_children():
        for child in top_level_device.get_children():
            child.remove()