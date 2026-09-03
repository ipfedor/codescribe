# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import gc
import os

from import_export import read_native, write_native
from object_type import ObjectType, get_object_type
from util import *

from communication_import_export import NO_EXPORT_FOLDER_NAME

DEVICE_TREE_FOLDER_NAME = u"devices"

# Native export stubs with empty EntryList are ~311 bytes on XS Studio / CODESYS.
_EMPTY_NATIVE_EXPORT_MAX_BYTES = 512


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


def _is_probably_empty_native_export(path_bytes):
    try:
        return os.path.getsize(path_bytes) <= _EMPTY_NATIVE_EXPORT_MAX_BYTES
    except (IOError, OSError):
        return True


def _export_device_children_to_folder(device_node, node_folder):
    """
    Export nested devices the same way as IFM ``communication/``:
    one recursive native XML per direct child under ``devices/<parent>/``.
    """
    node_folder_bytes = ensure_unicode_path(node_folder)
    os.mkdir(node_folder_bytes)

    exported = 0
    for child_device in device_node.get_children():
        child_name = child_device.get_name()
        export_path = os.path.join(node_folder, child_name + u".xml")
        export_path_bytes = ensure_unicode_path(export_path)
        write_native(child_device, export_path_bytes, recursive=True)
        gc.collect()
        size = 0
        try:
            size = os.path.getsize(export_path_bytes)
        except (IOError, OSError):
            pass
        if _is_probably_empty_native_export(export_path_bytes):
            safe_print(
                u"  Warning: empty native export for nested device "
                + device_node.get_name()
                + u"/"
                + child_name
                + u" ("
                + unicode(size)
                + u" bytes)"
            )
        else:
            safe_print(
                u"  Device nested: "
                + device_node.get_name()
                + u"/"
                + child_name
                + u" ("
                + unicode(size)
                + u" bytes)"
            )
        exported += 1
    return exported


def _export_device_flat(device_node, devices_folder):
    """Leaf top-level device: single ``devices/<name>.xml`` (recursive)."""
    child_name = device_node.get_name()
    export_path = os.path.join(devices_folder, child_name + u".xml")
    export_path_bytes = ensure_unicode_path(export_path)
    write_native(device_node, export_path_bytes, recursive=True)
    gc.collect()
    size = 0
    try:
        size = os.path.getsize(export_path_bytes)
    except (IOError, OSError):
        pass
    if _is_probably_empty_native_export(export_path_bytes):
        safe_print(
            u"  Warning: empty native export for device "
            + child_name
            + u" ("
            + unicode(size)
            + u" bytes)"
        )
    else:
        safe_print(u"  Device: " + child_name + u" (" + unicode(size) + u" bytes)")
    return True


def export_device_tree_siblings(device_obj, device_folder, application, communication=None):
    """
    Export fieldbus / Ethernet / Modbus devices that sit next to PLC Logic.

    Layout (mirrors proven ``communication/`` nesting):

    * Parent with children → ``devices/<parent>/<child>.xml`` (recursive per child).
      Parent-only ``export_native(recursive=True)`` often yields an empty EntryList
      stub on XS Studio for Modbus / bus-expansion masters; child export keeps slaves
      and modules.
    * Leaf top-level device → ``devices/<name>.xml`` (recursive).

    Legacy flat ``devices/<parent>.xml`` files that already contain a full subtree
    remain importable.
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

    for device_node in to_export:
        nested = list(device_node.get_children())
        if nested:
            node_folder = os.path.join(devices_folder, device_node.get_name())
            count = _export_device_children_to_folder(device_node, node_folder)
            safe_print(
                u"  Device tree folder: "
                + device_node.get_name()
                + u"/ ("
                + unicode(count)
                + u" nested)"
            )
        else:
            _export_device_flat(device_node, devices_folder)

    return True


def _tracked_device_names(devices_folder):
    """Unique top-level device names from flat XML files and/or nested folders."""
    names = []
    seen = set()
    for entry in os.listdir(devices_folder):
        full_path = os.path.join(devices_folder, entry)
        full_path_bytes = ensure_unicode_path(full_path)
        if os.path.isdir(full_path_bytes):
            name = entry
        else:
            base_name, ext = os.path.splitext(entry)
            if ext != u".xml":
                continue
            name = base_name
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def import_device_tree_siblings(device_obj, device_folder):
    devices_folder = os.path.join(device_folder, DEVICE_TREE_FOLDER_NAME)
    devices_folder_bytes = ensure_unicode_path(devices_folder)
    if not os.path.exists(devices_folder_bytes):
        return

    if no_export_device_tree(device_obj):
        return

    remove_tracked_device_tree_devices(device_obj, device_folder)

    for entry in sorted(os.listdir(devices_folder)):
        try:
            if entry.lower().endswith(u".xml.st"):
                continue
        except Exception:
            pass

        full_path = os.path.join(devices_folder, entry)
        full_path_bytes = ensure_unicode_path(full_path)

        if os.path.isdir(full_path_bytes):
            device_node = _find_device_tree_sibling(device_obj, entry)
            if device_node is None:
                raise ValueError(
                    u"Cannot find top-level device-tree device with name " + entry
                )
            for child_name in sorted(os.listdir(full_path)):
                try:
                    if child_name.lower().endswith(u".xml.st"):
                        continue
                except Exception:
                    pass
                _, ext = os.path.splitext(child_name)
                if ext != u".xml":
                    continue
                import_file_path = os.path.join(full_path, child_name)
                read_native(import_file_path, device_node)
            continue

        base_name, ext = os.path.splitext(entry)
        if ext != u".xml":
            continue
        device_node = _find_device_tree_sibling(device_obj, base_name)
        if device_node is None:
            raise ValueError(
                u"Cannot find top-level device-tree device with name " + base_name
            )
        # Prefer nested folder when both legacy flat XML and folder exist.
        nested_folder = os.path.join(devices_folder, base_name)
        nested_folder_bytes = ensure_unicode_path(nested_folder)
        if os.path.isdir(nested_folder_bytes):
            safe_print(
                u"Skipping flat "
                + entry
                + u" (nested folder "
                + base_name
                + u"/ takes precedence)"
            )
            continue
        read_native(full_path, device_node)


def remove_tracked_device_tree_devices(device_obj, device_folder):
    if no_export_device_tree(device_obj):
        return

    devices_folder = os.path.join(device_folder, DEVICE_TREE_FOLDER_NAME)
    devices_folder_bytes = ensure_unicode_path(devices_folder)
    if not os.path.exists(devices_folder_bytes):
        return

    for name in _tracked_device_names(devices_folder):
        device_node = _find_device_tree_sibling(device_obj, name)
        if device_node is None:
            continue
        for child in list(device_node.get_children()):
            child.remove()
