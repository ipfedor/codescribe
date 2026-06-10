# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import gc
import os

from import_export import read_native, write_native
from object_type import ObjectType, get_object_type
from util import *

from communication_import_export import NO_EXPORT_FOLDER_NAME

DEVICE_TREE_FOLDER_NAME = u"devices"


def no_export_device_tree(device_obj):
    """Disable device-tree export when `_NO_EXPORT` is a direct child of the PLC device."""
    for child in device_obj.get_children():
        if get_object_type(child) == ObjectType.FOLDER and child.get_name() == NO_EXPORT_FOLDER_NAME:
            return True
    return False


def _subtree_contains(root, target):
    if root == target:
        return True
    for ch in root.get_children():
        if _subtree_contains(ch, target):
            return True
    return False


def _find_device_tree_sibling(device_obj, name):
    """Match export scope: only direct DEVICE children of the PLC device."""
    for child in device_obj.get_children():
        if get_object_type(child) != ObjectType.DEVICE:
            continue
        if child.get_name() == name:
            return child
    return None


def _should_skip_device_tree_export(child, application, communication):
    if get_object_type(child) != ObjectType.DEVICE:
        return True
    if communication is not None and child == communication:
        return True
    if _subtree_contains(child, application):
        return True
    return False


def export_device_tree_siblings(device_obj, device_folder, application, communication=None):
    """
    Export fieldbus / Ethernet / Modbus devices that sit next to PLC Logic in the device tree.

    Each top-level DEVICE sibling of the Application branch is written as
    ``<device_folder>/devices/<name>.xml`` (native export, recursive).
    """
    if no_export_device_tree(device_obj):
        return False

    to_export = []
    for child in device_obj.get_children():
        if _should_skip_device_tree_export(child, application, communication):
            continue
        to_export.append(child)

    if not to_export:
        return False

    devices_folder = os.path.join(device_folder, DEVICE_TREE_FOLDER_NAME)
    devices_folder_bytes = ensure_unicode_path(devices_folder)
    os.mkdir(devices_folder_bytes)

    for child in to_export:
        child_name = child.get_name()
        export_path = os.path.join(devices_folder, child_name + u".xml")
        export_path_bytes = ensure_unicode_path(export_path)
        write_native(child, export_path_bytes, recursive=True)
        gc.collect()

    return True


def import_device_tree_siblings(device_obj, device_folder):
    devices_folder = os.path.join(device_folder, DEVICE_TREE_FOLDER_NAME)
    devices_folder_bytes = ensure_unicode_path(devices_folder)
    if not os.path.exists(devices_folder_bytes):
        return

    if no_export_device_tree(device_obj):
        return

    remove_tracked_device_tree_devices(device_obj, device_folder)

    for child_name in sorted(os.listdir(devices_folder)):
        try:
            if child_name.lower().endswith(u".xml.st"):
                continue
        except Exception:
            pass
        base_name, ext = os.path.splitext(child_name)
        if ext != u".xml":
            continue
        device_node = _find_device_tree_sibling(device_obj, base_name)
        if device_node is None:
            raise ValueError(
                u"Cannot find top-level device-tree device with name " + base_name
            )
        import_file_path = os.path.join(devices_folder, child_name)
        read_native(import_file_path, device_node)


def remove_tracked_device_tree_devices(device_obj, device_folder):
    if no_export_device_tree(device_obj):
        return

    devices_folder = os.path.join(device_folder, DEVICE_TREE_FOLDER_NAME)
    devices_folder_bytes = ensure_unicode_path(devices_folder)
    if not os.path.exists(devices_folder_bytes):
        return

    for child_name in os.listdir(devices_folder):
        base_name, ext = os.path.splitext(child_name)
        if ext != u".xml":
            continue
        device_node = _find_device_tree_sibling(device_obj, base_name)
        if device_node is None:
            continue
        for child in list(device_node.get_children()):
            child.remove()
