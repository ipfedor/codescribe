# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import gc
import io
import os
import re

from import_export import (
    count_io_variable_mappings,
    read_native_under_parent,
    write_native,
    write_native_preserving_io_maps,
)
from object_type import ObjectType, get_object_type
from util import *

from communication_import_export import NO_EXPORT_FOLDER_NAME

DEVICE_TREE_FOLDER_NAME = u"devices"

# Native export stubs with empty EntryList are ~311 bytes on XS Studio / CODESYS.
_EMPTY_NATIVE_EXPORT_MAX_BYTES = 512


def _as_unicode_name(name):
    if isinstance(name, unicode):
        return name
    try:
        return name.decode("utf-8")
    except Exception:
        try:
            return name.decode("mbcs")
        except Exception:
            return unicode(name)


def _natural_sort_key(name):
    """A1, A2, … A10 (not lexicographic A1, A10, A2) — bus slot order."""
    name = _as_unicode_name(name)
    parts = re.split(ur"(\d+)", name)
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return key


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
    """Match export scope: direct DEVICE children of the PLC device."""
    for child in device_obj.get_children():
        if get_object_type(child) != ObjectType.DEVICE:
            continue
        if child.get_name() == name:
            return child
    return None


def _find_device_tree_node(device_obj, name):
    """
    Resolve the live parent for a devices/<name>/ folder or devices/<name>.xml.

    Prefer direct PLC siblings (export scope). Fall back to recursive find so
    orphaned folders (e.g. A15_COM*) do not hard-abort the whole import after
    other parents were already cleared.
    """
    sibling = _find_device_tree_sibling(device_obj, name)
    if sibling is not None:
        return sibling

    # Direct child by name even if type Guid mapping missed DEVICE.
    for child in device_obj.get_children():
        if child.get_name() == name:
            return child

    try:
        found = list(device_obj.find(name, recursive=True))
    except Exception:
        found = []
    node = first_of_type_or_none(found, ObjectType.DEVICE)
    if node is not None:
        return node
    return first_or_none(found)


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

    Per-child export_native on XS Studio often strips IoMapping Variable rows;
    preserve mappings from a previous file when the new export is empty.
    """
    node_folder_bytes = ensure_unicode_path(node_folder)
    if not os.path.isdir(node_folder_bytes):
        os.mkdir(node_folder_bytes)

    exported = 0
    for child_device in device_node.get_children():
        child_name = child_device.get_name()
        export_path = os.path.join(node_folder, child_name + u".xml")
        export_path_bytes = ensure_unicode_path(export_path)
        write_native_preserving_io_maps(child_device, export_path_bytes, recursive=True)
        gc.collect()
        size = 0
        map_count = 0
        try:
            size = os.path.getsize(export_path_bytes)
            with io.open(export_path_bytes, u"r", encoding=u"utf-8") as f:
                map_count = count_io_variable_mappings(f.read())
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
                + u" bytes, "
                + unicode(map_count)
                + u" I/O vars)"
            )
            if map_count == 0:
                safe_print(
                    u"  Warning: no I/O Variable mappings in "
                    + child_name
                    + u".xml — re-export from a project that still has bindings, "
                    u"or keep a previously mapped XML"
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
    devices_folder = ensure_unicode_path(devices_folder)
    for entry in os.listdir(devices_folder):
        full_path = ensure_unicode_path(os.path.join(devices_folder, entry))
        if os.path.isdir(full_path):
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


def _import_nested_device_xmls(folder_path, device_node, host_device_obj):
    """Import ``*.xml`` children under device_node (natural order, Guid rewrite)."""
    folder_path = ensure_unicode_path(folder_path)
    for child_name in sorted(os.listdir(folder_path), key=_natural_sort_key):
        try:
            if _as_unicode_name(child_name).lower().endswith(u".xml.st"):
                continue
        except Exception:
            pass
        _, ext = os.path.splitext(child_name)
        if ext != u".xml":
            continue
        import_file_path = ensure_unicode_path(os.path.join(folder_path, child_name))
        safe_print(
            u"  Device import: "
            + device_node.get_name()
            + u"/"
            + _as_unicode_name(child_name)
        )
        read_native_under_parent(import_file_path, device_node, host_device_obj)


def _clear_device_children(device_node):
    for child in list(device_node.get_children()):
        child.remove()


def import_device_tree_siblings(device_obj, device_folder, application=None):
    """
    Re-import fieldbus / expansion / Modbus devices next to PLC Logic.

    ``device_obj`` is the PLC device (HostObjectGuid target for I/O mappings).
    Falls back to ``application`` Guid if the PLC device Guid is unreadable.
    Nested XMLs are imported under the matching top-level bus device with
    ParentGuid + HostObjectGuid rewritten to the live project.

    Each tracked parent is cleared and re-imported independently so one bad
    folder cannot abort the rest after a global remove.
    """
    devices_folder = ensure_unicode_path(os.path.join(device_folder, DEVICE_TREE_FOLDER_NAME))
    if not os.path.exists(devices_folder):
        return

    if no_export_device_tree(device_obj):
        return

    from import_export import _object_guid

    host_obj = device_obj
    if application is not None and _object_guid(device_obj) is None:
        if _object_guid(application) is not None:
            safe_print(
                u"Warning: PLC device Guid unreadable; using Application as "
                u"HostObjectGuid for I/O mappings"
            )
            host_obj = application

    for entry in sorted(os.listdir(devices_folder), key=_natural_sort_key):
        try:
            _import_one_device_tree_entry(host_obj, devices_folder, entry, device_obj)
        except Exception as e:
            safe_print(
                u"Warning: device-tree import failed for "
                + _as_unicode_name(entry)
                + u": "
                + unicode(e)
            )


def _import_one_device_tree_entry(host_obj, devices_folder, entry, device_obj):
    """
    Remove children of one tracked parent, then re-import that entry.

    ``device_obj`` is used to find parents; ``host_obj`` is HostObjectGuid target.
    """
    try:
        if _as_unicode_name(entry).lower().endswith(u".xml.st"):
            return
    except Exception:
        pass

    full_path = ensure_unicode_path(os.path.join(devices_folder, entry))

    if os.path.isdir(full_path):
        device_node = _find_device_tree_node(device_obj, entry)
        if device_node is None:
            safe_print(
                u"Skipping device-tree folder "
                + _as_unicode_name(entry)
                + u"/ (no matching device in project)"
            )
            return
        safe_print(u"  Device tree clear+import: " + device_node.get_name() + u"/")
        _clear_device_children(device_node)
        _import_nested_device_xmls(full_path, device_node, host_obj)
        return

    base_name, ext = os.path.splitext(entry)
    if ext != u".xml":
        return

    # Prefer nested folder when both legacy flat XML and folder exist.
    nested_folder = ensure_unicode_path(os.path.join(devices_folder, base_name))
    if os.path.isdir(nested_folder):
        safe_print(
            u"Skipping flat "
            + _as_unicode_name(entry)
            + u" (nested folder "
            + _as_unicode_name(base_name)
            + u"/ takes precedence)"
        )
        return

    device_node = _find_device_tree_node(device_obj, base_name)
    if device_node is None:
        safe_print(
            u"Skipping device-tree file "
            + _as_unicode_name(entry)
            + u" (no matching device in project)"
        )
        return

    safe_print(u"  Device tree clear+import: " + device_node.get_name())
    _clear_device_children(device_node)
    safe_print(u"  Device import: " + _as_unicode_name(entry))
    read_native_under_parent(full_path, device_node, host_obj)


def remove_tracked_device_tree_devices(device_obj, device_folder):
    """
    Clear children of tracked device-tree parents.

    Prefer ``import_device_tree_siblings`` (per-parent clear+import). This remains
    for callers that only need cleanup.
    """
    if no_export_device_tree(device_obj):
        return

    devices_folder = os.path.join(device_folder, DEVICE_TREE_FOLDER_NAME)
    devices_folder_bytes = ensure_unicode_path(devices_folder)
    if not os.path.exists(devices_folder_bytes):
        return

    for name in _tracked_device_names(devices_folder):
        device_node = _find_device_tree_node(device_obj, name)
        if device_node is None:
            continue
        _clear_device_children(device_node)
