# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
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
_DEVICE_TYPE_GUID = u"225bfe47-7336-4dbc-9419-4105a7c831fa"
_KNOWN_BUS_MASTERS = (u"Right_Expansion_Module", u"Modbus_COM", u"Left_Expansion_Module")
_SECONDARY_COM_DEVICE_RE = re.compile(ur"^.+_COM\d+$", re.IGNORECASE)

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


def _device_type_guid(obj):
    try:
        guid = getattr(obj, "type", None)
        if guid is None:
            return None
        gs = unicode(guid).lower().strip(u"{}")
        return gs
    except Exception:
        return None


def _is_exportable_device_tree_node(obj):
    """DEVICE guid mapping or known CODESYS device TypeGuid (e.g. Xinje COM ports)."""
    if get_object_type(obj) == ObjectType.DEVICE:
        return True
    return _device_type_guid(obj) == _DEVICE_TYPE_GUID


def _exportable_device_children(device_node):
    return [c for c in device_node.get_children() if _is_exportable_device_tree_node(c)]


def _find_device_tree_sibling(device_obj, name):
    """Match export scope: direct exportable device children of the PLC device."""
    for child in device_obj.get_children():
        if not _is_exportable_device_tree_node(child):
            continue
        if child.get_name() == name:
            return child
    return None


def _remove_child_device_by_name(parent_obj, base_name):
    """Remove only the device we are about to re-import (exact name)."""
    child = _find_child_device(parent_obj, base_name)
    if child is None:
        return
    safe_print(
        u"  Device replace: remove "
        + parent_obj.get_name()
        + u"/"
        + child.get_name()
    )
    child.remove()


def _import_device_xml_under_parent(full_path, parent_obj, host_device_obj, child_base):
    """Remove existing same-name child, then import_native under parent."""
    _remove_child_device_by_name(parent_obj, child_base)
    safe_print(
        u"  Device import: "
        + parent_obj.get_name()
        + u"/"
        + child_base
        + u".xml"
    )
    read_native_under_parent(full_path, parent_obj, host_device_obj)


def _find_child_device(parent_obj, name):
    for child in parent_obj.get_children():
        if child.get_name() == name and _is_exportable_device_tree_node(child):
            return child
    try:
        found = list(parent_obj.find(name, recursive=False))
    except Exception:
        found = []
    node = first_of_type_or_none(found, ObjectType.DEVICE)
    if node is not None:
        return node
    for obj in found:
        if _is_exportable_device_tree_node(obj):
            return obj
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
    for obj in found:
        if _is_exportable_device_tree_node(obj):
            return obj
    return first_or_none(found)


def _should_export_flat_parent_stub(device_node):
    """COM secondary devices (A15_COM1) need a flat XML stub importable under the PLC."""
    name = device_node.get_name()
    if name in _KNOWN_BUS_MASTERS:
        return False
    return _SECONDARY_COM_DEVICE_RE.match(name) is not None


def _device_tree_top_level_sort_key(entry_name):
    """Import bus masters before COM secondaries (A15_COM* depends on expansion tree)."""
    name = _as_unicode_name(entry_name)
    if name in _KNOWN_BUS_MASTERS:
        return (0, _natural_sort_key(name))
    if _SECONDARY_COM_DEVICE_RE.match(name):
        return (2, _natural_sort_key(name))
    return (1, _natural_sort_key(name))


def _flat_parent_stub_path(devices_folder, entry_name):
    return ensure_unicode_path(os.path.join(devices_folder, entry_name + u".xml"))


def _folder_parent_stub_path(folder_path, entry_name):
    return ensure_unicode_path(os.path.join(folder_path, entry_name + u".xml"))


def _import_flat_parent_stub(stub_path, plc_device_obj, host_device_obj):
    """Create/update a top-level device node (e.g. A15_COM1) under the PLC device."""
    stub_path = ensure_unicode_path(stub_path)
    if not os.path.isfile(stub_path):
        return False
    safe_print(
        u"  Device parent stub: "
        + os.path.basename(stub_path)
        + u" -> PLC"
    )
    read_native_under_parent(stub_path, plc_device_obj, host_device_obj)
    return True


def _ensure_device_tree_node(device_obj, host_device_obj, devices_folder, entry_name):
    """
    Resolve device by name; import flat/folder stub under PLC when the node
    is missing (typical for A15_COM* after template open).
    """
    node = _find_device_tree_node(device_obj, entry_name)
    if node is not None:
        return node

    flat_stub = _flat_parent_stub_path(devices_folder, entry_name)
    if _import_flat_parent_stub(flat_stub, device_obj, host_device_obj):
        return _find_device_tree_node(device_obj, entry_name)

    folder_stub = _folder_parent_stub_path(
        ensure_unicode_path(os.path.join(devices_folder, entry_name)),
        entry_name,
    )
    if _import_flat_parent_stub(folder_stub, device_obj, host_device_obj):
        return _find_device_tree_node(device_obj, entry_name)

    return None


def _should_skip_device_tree_export(child, application, communication):
    if not _is_exportable_device_tree_node(child):
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


def _export_nested_device_children(slot_device, node_folder, slot_name):
    """Export 2nd-level devices (e.g. A15/A15_COM1.xml) under a bus slot."""
    nested = _exportable_device_children(slot_device)
    if not nested:
        return 0

    slot_folder = os.path.join(node_folder, slot_name)
    slot_folder_bytes = ensure_unicode_path(slot_folder)
    if not os.path.isdir(slot_folder_bytes):
        os.mkdir(slot_folder_bytes)

    count = 0
    for nested_device in nested:
        nested_name = nested_device.get_name()
        export_path = os.path.join(slot_folder, nested_name + u".xml")
        export_path_bytes = ensure_unicode_path(export_path)
        write_native_preserving_io_maps(nested_device, export_path_bytes, recursive=True)
        # No per-device gc.collect() — see write_native success-path note.
        size = 0
        try:
            size = os.path.getsize(export_path_bytes)
        except (IOError, OSError):
            pass
        safe_print(
            u"  Device nested: "
            + slot_name
            + u"/"
            + nested_name
            + u" ("
            + unicode(size)
            + u" bytes)"
        )
        count += 1
    return count


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
    nested_count = 0
    for child_device in device_node.get_children():
        if not _is_exportable_device_tree_node(child_device):
            continue
        child_name = child_device.get_name()
        export_path = os.path.join(node_folder, child_name + u".xml")
        export_path_bytes = ensure_unicode_path(export_path)
        write_native_preserving_io_maps(child_device, export_path_bytes, recursive=True)
        # No per-device gc.collect() — see write_native success-path note.
        nested_count += _export_nested_device_children(child_device, node_folder, child_name)
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
    return exported, nested_count


def _export_device_flat(device_node, devices_folder):
    """Leaf top-level device: single ``devices/<name>.xml`` (recursive)."""
    child_name = device_node.get_name()
    export_path = os.path.join(devices_folder, child_name + u".xml")
    export_path_bytes = ensure_unicode_path(export_path)
    write_native(device_node, export_path_bytes, recursive=True)
    # No per-device gc.collect() — see write_native success-path note.
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
      Second-level devices (e.g. COM ports under A15) → ``devices/<parent>/<slot>/<name>.xml``.
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
        nested = _exportable_device_children(device_node)
        if nested:
            node_folder = os.path.join(devices_folder, device_node.get_name())
            # Stub flat XML so import can recreate the device under PLC before
            # importing its children from the subfolder.
            flat_path = os.path.join(devices_folder, device_node.get_name() + u".xml")
            write_native_preserving_io_maps(
                device_node, ensure_unicode_path(flat_path), recursive=False
            )
            # No per-device gc.collect() — see write_native success-path note.
            count, sub_count = _export_device_children_to_folder(device_node, node_folder)
            msg = (
                u"  Device tree folder: "
                + device_node.get_name()
                + u"/ ("
                + unicode(count)
                + u" nested"
            )
            if sub_count:
                msg += u", " + unicode(sub_count) + u" sub-devices"
            msg += u")"
            safe_print(msg)
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


def _import_entry_sort_key(folder_path, entry_name):
    """Import slot XML before subfolders (A15.xml before A15/)."""
    full_path = ensure_unicode_path(os.path.join(folder_path, entry_name))
    if os.path.isdir(full_path):
        return (1, _natural_sort_key(entry_name))
    return (0, _natural_sort_key(entry_name))


def _import_nested_device_xmls(folder_path, device_node, host_device_obj):
    """Import ``*.xml`` and optional subfolders (e.g. A15/A15_COM1.xml)."""
    folder_path = ensure_unicode_path(folder_path)
    entries = sorted(
        os.listdir(folder_path),
        key=lambda entry: _import_entry_sort_key(folder_path, entry),
    )
    for child_name in entries:
        try:
            if _as_unicode_name(child_name).lower().endswith(u".xml.st"):
                continue
        except Exception:
            pass

        full_path = ensure_unicode_path(os.path.join(folder_path, child_name))

        if os.path.isdir(full_path):
            slot_node = _find_child_device(device_node, _as_unicode_name(child_name))
            if slot_node is None:
                safe_print(
                    u"  Skipping device subfolder "
                    + device_node.get_name()
                    + u"/"
                    + _as_unicode_name(child_name)
                    + u"/ (no matching slot in project)"
                )
                continue
            safe_print(
                u"  Device subfolder import: "
                + device_node.get_name()
                + u"/"
                + _as_unicode_name(child_name)
                + u"/"
            )
            _import_nested_device_xmls(full_path, slot_node, host_device_obj)
            continue

        _, ext = os.path.splitext(child_name)
        if ext != u".xml":
            continue
        child_base = _as_unicode_name(os.path.splitext(child_name)[0])
        try:
            _import_device_xml_under_parent(
                full_path, device_node, host_device_obj, child_base
            )
        except Exception as e:
            safe_print(
                u"Warning: device import failed for "
                + device_node.get_name()
                + u"/"
                + _as_unicode_name(child_name)
                + u": "
                + unicode(e)
            )


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

    deferred = []
    for entry in sorted(os.listdir(devices_folder), key=_device_tree_top_level_sort_key):
        try:
            if not _import_one_device_tree_entry(
                host_obj, devices_folder, entry, device_obj
            ):
                deferred.append(entry)
        except Exception as e:
            safe_print(
                u"Warning: device-tree import failed for "
                + _as_unicode_name(entry)
                + u": "
                + unicode(e)
            )

    for _pass in range(4):
        if not deferred:
            break
        still_deferred = []
        for entry in deferred:
            try:
                if not _import_one_device_tree_entry(
                    host_obj, devices_folder, entry, device_obj
                ):
                    still_deferred.append(entry)
            except Exception as e:
                safe_print(
                    u"Warning: device-tree import failed for "
                    + _as_unicode_name(entry)
                    + u": "
                    + unicode(e)
                )
                still_deferred.append(entry)
        if len(still_deferred) == len(deferred):
            break
        deferred = still_deferred

    for entry in deferred:
        safe_print(
            u"Warning: device-tree entry not imported (no matching device): "
            + _as_unicode_name(entry)
        )


def _import_one_device_tree_entry(host_obj, devices_folder, entry, device_obj):
    """
    Remove children of one tracked parent, then re-import that entry.

    ``device_obj`` is used to find parents; ``host_obj`` is HostObjectGuid target.

    Returns True when the entry was imported, False when skipped (may succeed later).
    """
    try:
        if _as_unicode_name(entry).lower().endswith(u".xml.st"):
            return True
    except Exception:
        pass

    full_path = ensure_unicode_path(os.path.join(devices_folder, entry))

    if os.path.isdir(full_path):
        entry_name = _as_unicode_name(entry)
        device_node = _find_device_tree_node(device_obj, entry_name)
        if device_node is None:
            # Try to create via flat stub XML (e.g. A15_COM1.xml).
            flat_stub = _flat_parent_stub_path(devices_folder, entry_name)
            if os.path.isfile(ensure_unicode_path(flat_stub)):
                safe_print(u"  Device stub create: " + entry_name + u".xml -> PLC")
                read_native_under_parent(
                    ensure_unicode_path(flat_stub), device_obj, host_obj
                )
                device_node = _find_device_tree_node(device_obj, entry_name)
        if device_node is None:
            safe_print(
                u"Skipping device-tree folder "
                + entry_name
                + u"/ (no matching device in project)"
            )
            return False
        safe_print(u"  Device subfolder children import: " + device_node.get_name() + u"/")
        _import_nested_device_xmls(full_path, device_node, host_obj)
        return True

    base_name, ext = os.path.splitext(entry)
    if ext != u".xml":
        return True

    nested_folder = ensure_unicode_path(os.path.join(devices_folder, base_name))
    has_nested_folder = os.path.isdir(nested_folder)

    if has_nested_folder:
        # Flat XML exists alongside a folder: only used as a stub when the folder
        # import cannot find the node. Skip here — folder entry handles the children.
        return True

    # Leaf devices/<name>.xml: replace under the PLC, never import under itself.
    _import_device_xml_under_parent(
        full_path, device_obj, host_obj, _as_unicode_name(base_name)
    )
    return True


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
