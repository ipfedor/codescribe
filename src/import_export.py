# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import gc
import io
import os
import re
import time

from object_type import ObjectType, get_object_type
from util import *

IMPLEMENTATION_DELIMITER_SPLIT = u"// --- BEGIN IMPLEMENTATION ---"
IMPLEMENTATION_DELIMITER_INSERT = u"\n" + IMPLEMENTATION_DELIMITER_SPLIT + u"\n\n"


def write_st(obj, f):
    f.write(obj.textual_declaration.text)
    f.write(IMPLEMENTATION_DELIMITER_INSERT)
    f.write(obj.textual_implementation.text)


def write_st_decl_only(obj, f):
    f.write(obj.textual_declaration.text)


def import_st(f, obj):
    f.seek(0)
    content = f.read()  # уже unicode, если файл открыт с encoding='utf-8'
    declaration, implementation = content.split(IMPLEMENTATION_DELIMITER_SPLIT)
    obj.textual_declaration.replace(declaration.strip() + u"\n")
    obj.textual_implementation.replace(implementation.strip() + u"\n")


def import_st_decl_only(f, obj):
    f.seek(0)
    content = f.read()
    obj.textual_declaration.replace(content.strip() + u"\n")


_TIMESTAMP_LINE_RE = re.compile(
    ur'^(?P<prefix>.+<Single Name="(?:Timestamp)" Type="long">).+(?P<suffix></Single>)$',
    re.MULTILINE,
)


def _normalize_export_timestamps_once(path_bytes):
    try:
        size = os.path.getsize(path_bytes)
    except OSError:
        return

    # Very large native exports: skip post-processing to limit peak memory in CodeSYS.
    if size > 8 * 1024 * 1024:
        return

    tmp_path = path_bytes + u".codescribe_ts_tmp"
    with io.open(path_bytes, "r", encoding="utf-8") as src:
        with io.open(tmp_path, "w", encoding="utf-8") as dst:
            if size > 512 * 1024:
                for line in src:
                    m = _TIMESTAMP_LINE_RE.match(line.rstrip(u"\r\n"))
                    if m:
                        dst.write(m.group("prefix") + u"0" + m.group("suffix") + u"\n")
                    else:
                        dst.write(line)
            else:
                lines = src.read()
                dst.write(
                    _TIMESTAMP_LINE_RE.sub(
                        lambda m: m.group("prefix") + u"0" + m.group("suffix"),
                        lines,
                    )
                )
    os.remove(path_bytes)
    os.rename(tmp_path, path_bytes)


def _normalize_export_timestamps(path_bytes, retries=8, delay_sec=0.15):
    path_bytes = ensure_unicode_path(path_bytes)
    last_err = None
    for attempt in range(retries):
        try:
            _normalize_export_timestamps_once(path_bytes)
            return
        except (IOError, OSError) as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(delay_sec)
                gc.collect()
    safe_print(
        u"Warning: could not normalize timestamps for "
        + path_bytes
        + u": "
        + unicode(last_err)
    )


def write_native(obj, path, recursive=False):
    # path может быть байтовой строкой или unicode; для export_native нужно передать str в Python 2.7?
    # obj.export_native ожидает, вероятно, байтовую строку. Преобразуем в bytes.
    path_bytes = ensure_unicode_path(path)
    last_err = None
    for attempt in range(8):
        try:
            if os.path.exists(path_bytes):
                try:
                    os.remove(path_bytes)
                except (IOError, OSError):
                    pass
            obj.export_native(path_bytes, recursive=recursive)
            break
        except (IOError, OSError) as e:
            last_err = e
            if attempt + 1 < 8:
                time.sleep(0.15)
                gc.collect()
            else:
                raise
    gc.collect()
    time.sleep(0.05)
    _normalize_export_timestamps(path_bytes)


def read_native(f, obj):
    # f - это путь (строка) или файловый объект? По контексту - путь.
    # В вызовах read_native(os.path.join(...), dir_parent_obj) - передаётся путь.
    # Преобразуем в байтовую строку для import_native.
    path_bytes = ensure_unicode_path(f)
    obj.import_native(path_bytes)


def export_folder(child_obj, parent_obj, parent_folder_path, export_child_fn):
    child_obj_folder = os.path.join(parent_folder_path, child_obj.get_name())
    child_obj_folder_bytes = ensure_unicode_path(child_obj_folder)
    os.mkdir(child_obj_folder_bytes)
    for c in child_obj.get_children():
        export_child_fn(c, child_obj, child_obj_folder)


def import_folder(child, dir_path, dir_parent_obj, import_dir_fn, application_obj=None):
    dir_parent_obj.create_folder(child)
    folder_obj = first_of_type_or_error(
        dir_parent_obj.find(child),
        ObjectType.FOLDER,
        u"Folder of name " + child + u" should have been created, but cannot be found",
    )
    if application_obj is None:
        application_obj = dir_parent_obj
    import_dir_fn(os.path.join(dir_path, child), folder_obj, application_obj)


def ensure_folder(dir_parent_obj, folder_name):
    folder_obj = first_of_type_or_none(dir_parent_obj.find(folder_name), ObjectType.FOLDER)
    if folder_obj is not None:
        return folder_obj
    dir_parent_obj.create_folder(folder_name)
    return first_of_type_or_error(
        dir_parent_obj.find(folder_name),
        ObjectType.FOLDER,
        u"Folder of name " + folder_name + u" should have been created, but cannot be found",
    )


def export_pou(child_obj, parent_obj, parent_folder_path, export_child_fn):
    if child_obj.has_textual_implementation:
        file_path = os.path.join(parent_folder_path, child_obj.get_name() + u".st")
        file_path_bytes = ensure_unicode_path(file_path)
        with io.open(file_path_bytes, "w", encoding='utf-8') as f:
            write_st(child_obj, f)
    else:
        export_native(child_obj, parent_obj, parent_folder_path, export_child_fn)

    for c in child_obj.get_children():
        export_child_fn(c, child_obj, parent_folder_path)


def import_pou_st(child, dir_path, dir_parent_obj, import_dir_fn):
    filename, _ = os.path.splitext(child)
    pou_obj = dir_parent_obj.create_pou(filename)
    full_path = os.path.join(dir_path, child)
    full_path_bytes = ensure_unicode_path(full_path)
    with io.open(full_path_bytes, "r", encoding='utf-8') as f:
        import_st(f, pou_obj)


def find_gvl_or_error(parent_obj, name, err):
    for gvl_type in (ObjectType.GVL, ObjectType.GVL_PERSISTENT):
        found = first_of_type_or_none(parent_obj.find(name), gvl_type)
        if found is not None:
            return found
    raise ValueError(err)


def export_gvl(child_obj, parent_obj, parent_folder_path, export_child_fn):
    """
    Exports native xml and structured text representation.
    This is because we need to support EVL, NVL and persistent GVL as well, using this function.
    """
    write_native(child_obj, os.path.join(parent_folder_path, child_obj.get_name() + u".gvl.xml"), recursive=False)
    file_path = os.path.join(parent_folder_path, child_obj.get_name() + u".gvl.st")
    file_path_bytes = ensure_unicode_path(file_path)
    with io.open(file_path_bytes, "w", encoding='utf-8') as f:
        write_st_decl_only(child_obj, f)


def import_gvl(child, dir_path, dir_parent_obj, import_dir_fn):
    """
    Import the native xml and then overwrite the textual definition with the structured text.
    """
    name, ext = os.path.splitext(child)

    if u".gvl" not in name:
        raise ValueError(u".gvl not in file name!")

    name = name.replace(u".gvl", u"")

    if ext != u".st":
        raise ValueError(u"Expected GVL st file!")

    gvl_xml_path = os.path.join(dir_path, name + u".gvl.xml")
    gvl_xml_path_bytes = ensure_unicode_path(gvl_xml_path)
    if os.path.exists(gvl_xml_path_bytes):
        import_native(gvl_xml_path, dir_path, dir_parent_obj, import_dir_fn)  # import_native ожидает путь
        imported_obj = find_gvl_or_error(
            dir_parent_obj,
            name,
            name + u" GVL should have been created, but cannot be found",
        )
    else:
        imported_obj = dir_parent_obj.create_gvl(name)

    full_path = os.path.join(dir_path, child)
    full_path_bytes = ensure_unicode_path(full_path)
    with io.open(full_path_bytes, "r", encoding='utf-8') as f:
        import_st_decl_only(f, imported_obj)


def export_native(child_obj, parent_obj, parent_folder_path, export_child_fn):
    write_native(child_obj, os.path.join(parent_folder_path, child_obj.get_name() + u".xml"), recursive=False)


def export_visualisation(child_obj, parent_obj, parent_folder_path, export_child_fn):
    """
    Visualisations often share names with POUs (e.g. Main program + Main visualisation).
    Use a dedicated suffix to avoid overwriting `Name.xml` from other object types.
    """
    write_native(child_obj, os.path.join(parent_folder_path, child_obj.get_name() + u".vis.xml"), recursive=False)


def export_native_recursive(child_obj, parent_obj, parent_folder_path, export_child_fn):
    write_native(child_obj, os.path.join(parent_folder_path, child_obj.get_name() + u".xml"), recursive=True)


def import_native(child, dir_path, dir_parent_obj, import_dir_fn, application_obj=None):
    full_path = os.path.join(dir_path, child)
    if application_obj is None:
        application_obj = dir_parent_obj
    parent_obj = resolve_native_import_parent(application_obj, dir_parent_obj, full_path)
    if parent_obj is not dir_parent_obj:
        try:
            safe_print(
                u"Importing " + child + u" under " + parent_obj.get_name()
            )
        except Exception:
            pass
    read_native(full_path, parent_obj)


def export_dut(child_obj, parent_obj, parent_folder_path, export_child_fn):
    file_path = os.path.join(parent_folder_path, child_obj.get_name() + u".st")
    file_path_bytes = ensure_unicode_path(file_path)
    with io.open(file_path_bytes, "w", encoding='utf-8') as f:
        f.write(child_obj.textual_declaration.text)


def import_dut(child, dir_path, dir_parent_obj, import_dir_fn):
    filename, _ = os.path.splitext(child)
    dut_obj = dir_parent_obj.create_dut(filename)
    full_path = os.path.join(dir_path, child)
    full_path_bytes = ensure_unicode_path(full_path)
    with io.open(full_path_bytes, "r", encoding='utf-8') as f:
        content = f.read()
        dut_obj.textual_declaration.replace(content.strip() + u"\n")


def export_method(child_obj, parent_obj, parent_folder_path, export_child_fn):
    if child_obj.has_textual_implementation:
        file_path = os.path.join(parent_folder_path, parent_obj.get_name() + u"." + child_obj.get_name() + u".st")
        file_path_bytes = ensure_unicode_path(file_path)
        with io.open(file_path_bytes, "w", encoding='utf-8') as f:
            write_st(child_obj, f)
    else:
        write_native(
            child_obj,
            os.path.join(parent_folder_path, parent_obj.get_name() + u"." + child_obj.get_name() + u".xml"),
            recursive=False,
        )


def import_method_st(child, dir_path, dir_parent_obj, import_dir_fn):
    full_path = os.path.join(dir_path, child)
    full_path_bytes = ensure_unicode_path(full_path)
    filename, _ = os.path.splitext(child)
    parent_name, method_name = filename.split(u".")
    parent_obj = first_of_type_or_error(
        dir_parent_obj.find(parent_name),
        ObjectType.POU,
        parent_name + u" should have been created, but cannot be found",
    )

    method_obj = parent_obj.create_method(method_name)
    with io.open(full_path_bytes, "r", encoding='utf-8') as f:
        import_st(f, method_obj)


def export_sub_pou(child_obj, parent_obj, parent_folder_path, export_child_fn):
    write_native(
        child_obj,
        os.path.join(parent_folder_path, parent_obj.get_name() + u"." + child_obj.get_name() + u".xml"),
        recursive=True,
    )


def import_sub_pou(child, dir_path, dir_parent_obj, import_dir_fn):
    full_path = os.path.join(dir_path, child)
    full_path_bytes = ensure_unicode_path(full_path)
    filename, _ = os.path.splitext(child)
    parent_name = filename.split(u".")[0]
    parent_obj = first_of_type_or_error(
        dir_parent_obj.find(parent_name),
        ObjectType.POU,
        parent_name + u" should have been created, but cannot be found",
    )

    parent_obj.import_native(full_path_bytes)


OBJECT_TYPE_TO_EXPORT_FUNCTION = {
    ObjectType.FOLDER: export_folder,
    ObjectType.POU: export_pou,
    ObjectType.GVL: export_gvl,  # EVL, NVL are "special types" of GVL which show up with the same UUID
    ObjectType.GVL_PERSISTENT: export_gvl,  # e.g. PersistentVars (RETAIN)
    ObjectType.EVC: export_native,
    ObjectType.VISUALISATION: export_visualisation,
    ObjectType.TASK_CONFIGURATION: export_native_recursive,
    ObjectType.DUT: export_dut,
    ObjectType.METHOD: export_method,
    ObjectType.METHOD_NORET: export_method,
    ObjectType.PROPERTY: export_sub_pou,
    ObjectType.ACTION: export_sub_pou,
    ObjectType.TRANSITION: export_sub_pou,
}

SUB_POU_MEMBER_TYPES = (
    ObjectType.METHOD,
    ObjectType.METHOD_NORET,
    ObjectType.PROPERTY,
    ObjectType.ACTION,
    ObjectType.TRANSITION,
)

# Native exports kept for reference / diff only — live in .project template, not round-trip import.
IMPORT_SKIP_NATIVE_TYPE_GUIDS = frozenset([
    u"ae1de277-a207-4a28-9efb-456c06bd52f3",  # Task configuration
    u"f18bec89-9fef-401d-9953-2f11739a6808",  # Visualisation
    u"4d3fdb8f-ab50-4c35-9d3a-d4bb9bb9a628",  # Visualization manager
])

RECIPE_MANAGER_TYPE_GUID = u"09ecc42e-586d-4a08-932f-5bdcac20bb55"
PERSISTENT_VARIABLES_TYPE_GUID = u"6b3dfb6a-1865-4356-a39b-1fe0ef89651c"

_EXPORT_ROOT_TYPE_GUID_RE = re.compile(
    ur'<Single Name="TypeGuid" Type="System\.Guid">([^<]+)</Single>',
    re.IGNORECASE,
)
_EXPORT_ROOT_GUID_RE = re.compile(
    ur'<Single Name="Guid" Type="System\.Guid">([^<]+)</Single>',
    re.IGNORECASE,
)
_EXPORT_ROOT_PARENT_GUID_RE = re.compile(
    ur'<Single Name="ParentGuid" Type="System\.Guid">([^<]+)</Single>',
    re.IGNORECASE,
)
_EXPORT_ROOT_OBJECT_NAME_RE = re.compile(
    ur'<Single Name="MetaObject"[^>]*>.*?<Single Name="Name" Type="string">([^<]*)</Single>',
    re.IGNORECASE | re.DOTALL,
)


def _normalize_object_guid(guid):
    if guid is None:
        return None
    if isinstance(guid, unicode):
        g = guid
    else:
        g = unicode(guid)
    return g.strip().strip(u"{}").lower()


def _read_export_head(full_path, size=8192):
    path_bytes = ensure_unicode_path(full_path)
    try:
        with io.open(path_bytes, "r", encoding="utf-8") as f:
            return f.read(size)
    except (IOError, OSError):
        return u""


def _peek_export_root_meta(full_path):
    head = _read_export_head(full_path)
    if not head:
        return None
    type_m = _EXPORT_ROOT_TYPE_GUID_RE.search(head)
    guid_m = _EXPORT_ROOT_GUID_RE.search(head)
    parent_m = _EXPORT_ROOT_PARENT_GUID_RE.search(head)
    name_m = _EXPORT_ROOT_OBJECT_NAME_RE.search(head)
    if not type_m and not guid_m and not parent_m and not name_m:
        return None
    meta = {}
    if type_m:
        meta[u"type_guid"] = _normalize_object_guid(type_m.group(1))
    if guid_m:
        meta[u"guid"] = _normalize_object_guid(guid_m.group(1))
    if parent_m:
        meta[u"parent_guid"] = _normalize_object_guid(parent_m.group(1))
    if name_m:
        meta[u"name"] = name_m.group(1)
    return meta


def _peek_export_root_type_guid(full_path):
    meta = _peek_export_root_meta(full_path)
    if not meta:
        return None
    return meta.get(u"type_guid")


def _object_guid(obj):
    try:
        return _normalize_object_guid(obj.guid)
    except Exception:
        return None


def _find_object_by_guid_subtree(root_obj, guid):
    target = _normalize_object_guid(guid)
    if not target:
        return None
    queue = [root_obj]
    while queue:
        obj = queue.pop(0)
        if _object_guid(obj) == target:
            return obj
        try:
            queue.extend(obj.get_children())
        except Exception:
            pass
    return None


def _find_object_by_name_subtree(root_obj, name):
    queue = [root_obj]
    while queue:
        obj = queue.pop(0)
        if obj.get_name() == name:
            return obj
        try:
            queue.extend(obj.get_children())
        except Exception:
            pass
    return None


def _find_recipe_manager(application_obj):
    queue = list(application_obj.get_children())
    while queue:
        obj = queue.pop(0)
        if _normalize_object_guid(getattr(obj, "type", None)) == RECIPE_MANAGER_TYPE_GUID:
            return obj
        if obj.get_name() in (u"RecipeManager", u"Recipe Manager", u"Rezeptmanager"):
            return obj
        try:
            queue.extend(obj.get_children())
        except Exception:
            pass
    return None


def resolve_native_import_parent(application_obj, dir_parent_obj, full_path):
    """
    Native exports of RecipeManager children (e.g. PersistentVariables with recipe
    data) are written flat into application/ but must be imported under their
    real parent in the project tree.
    """
    meta = _peek_export_root_meta(full_path)
    if meta is None:
        return dir_parent_obj

    parent_guid = meta.get(u"parent_guid")
    if parent_guid:
        found = _find_object_by_guid_subtree(application_obj, parent_guid)
        if found is not None:
            return found

    if meta.get(u"type_guid") == PERSISTENT_VARIABLES_TYPE_GUID:
        recipe_manager = _find_recipe_manager(application_obj)
        if recipe_manager is not None:
            return recipe_manager

    if _object_guid(dir_parent_obj) == parent_guid:
        return dir_parent_obj

    return dir_parent_obj


def should_defer_native_import(child, full_path, application_obj):
    filename, ext = os.path.splitext(child)
    if ext != u".xml" or u"." in filename:
        return False
    if should_skip_application_import_file(child, full_path):
        return False
    meta = _peek_export_root_meta(full_path)
    if meta is None or not meta.get(u"parent_guid"):
        return False
    if _object_guid(application_obj) == meta.get(u"parent_guid"):
        return False
    return _find_object_by_guid_subtree(application_obj, meta[u"parent_guid"]) is None


def should_skip_application_import_file(child, full_path):
    """
    Task config, visualisations and vis manager are exported for diff/reference but
    must not be imported — GUIDs and device bindings are project-template specific.
    """
    filename, ext = os.path.splitext(child)
    if filename.endswith(u".vis") and ext == u".xml":
        return True
    if ext != u".xml":
        return False
    if not os.path.isfile(ensure_unicode_path(full_path)):
        return False
    type_guid = _peek_export_root_type_guid(full_path)
    return type_guid in IMPORT_SKIP_NATIVE_TYPE_GUIDS


def is_template_managed_application_object(obj):
    obj_type = get_object_type(obj)
    if obj_type in (ObjectType.TASK_CONFIGURATION, ObjectType.VISUALISATION):
        return True
    return _normalize_object_guid(getattr(obj, "type", None)) in IMPORT_SKIP_NATIVE_TYPE_GUIDS


def _remove_named_child(parent_obj, name, allowed_types):
    for obj in list(parent_obj.get_children()):
        if obj.get_name() != name:
            continue
        if get_object_type(obj) not in allowed_types:
            continue
        safe_print(u"Removing " + name)
        obj.remove()
        return


def remove_object_for_import_child(child, dir_path, dir_parent_obj, application_obj=None):
    """
    Remove only the project object that corresponds to a single import file.

    Used immediately before importing that file so unrelated objects (e.g. GVL,
    PLC_PRG, Libs) are not deleted up front and lost when import aborts midway.
    """
    try:
        if child.lower().endswith(u".xml.st"):
            return
    except Exception:
        pass

    full_path = os.path.join(dir_path, child)
    filename, ext = os.path.splitext(child)

    if os.path.isdir(full_path):
        _remove_named_child(dir_parent_obj, child, (ObjectType.FOLDER,))
        return

    if filename.endswith(u".gvl"):
        if ext != u".st":
            return
        name = filename.replace(u".gvl", u"")
        _remove_named_child(
            dir_parent_obj, name, (ObjectType.GVL, ObjectType.GVL_PERSISTENT)
        )
        return

    if filename.endswith(u".vis"):
        if ext != u".xml":
            return
        name = filename.replace(u".vis", u"")
        _remove_named_child(dir_parent_obj, name, (ObjectType.VISUALISATION,))
        return

    if u"." in filename:
        parent_name, member_name = filename.split(u".", 1)
        parent_obj = first_of_type_or_none(
            dir_parent_obj.find(parent_name), ObjectType.POU
        )
        if parent_obj is None:
            return
        for sub in list(parent_obj.get_children()):
            if sub.get_name() != member_name:
                continue
            if get_object_type(sub) not in SUB_POU_MEMBER_TYPES:
                continue
            safe_print(u"Removing " + parent_name + u"." + member_name)
            sub.remove()
            return
        return

    if ext not in (u".xml", u".st"):
        return

    if application_obj is None:
        application_obj = dir_parent_obj

    meta = _peek_export_root_meta(full_path) if ext == u".xml" else None
    name = meta.get(u"name") if meta and meta.get(u"name") else filename
    parent_obj = (
        resolve_native_import_parent(application_obj, dir_parent_obj, full_path)
        if ext == u".xml"
        else dir_parent_obj
    )

    for obj in list(parent_obj.get_children()):
        if obj.get_name() != name:
            continue
        obj_type = get_object_type(obj)
        if obj_type in OBJECT_TYPE_TO_EXPORT_FUNCTION or obj_type == ObjectType.UNKNOWN:
            safe_print(u"Removing " + name)
            obj.remove()
        return


def remove_orphans_in_parent(parent_obj, dir_path):
    """Remove application objects with no matching file on disk (after full import)."""
    dir_path_bytes = ensure_unicode_path(dir_path)
    if not os.path.isdir(dir_path_bytes):
        return

    expected = collect_application_import_object_names(dir_path)
    for obj in list(parent_obj.get_children()):
        name = obj.get_name()
        obj_type = get_object_type(obj)

        if name in expected:
            if obj_type == ObjectType.FOLDER:
                subdir = os.path.join(dir_path, name)
                child_folder = first_of_type_or_none(
                    parent_obj.find(name), ObjectType.FOLDER
                )
                if child_folder is not None:
                    remove_orphans_in_parent(child_folder, subdir)
            continue

        if is_template_managed_application_object(obj):
            continue

        if obj_type in OBJECT_TYPE_TO_EXPORT_FUNCTION or obj_type == ObjectType.UNKNOWN:
            safe_print(u"Removing orphan " + name)
            obj.remove()


def collect_application_import_object_names(dir_path):
    """
    Top-level application object names that import_from_files will recreate.

    Includes native-xml objects (e.g. DifferentialMonitor, Symbols) whose type
    is not in OBJECT_TYPE_TO_EXPORT_FUNCTION and were therefore not removed
    by the older import cleanup logic.
    """
    names = set()
    for child in os.listdir(dir_path):
        try:
            if child.lower().endswith(u".xml.st"):
                continue
        except Exception:
            pass

        full_path = os.path.join(dir_path, child)
        filename, ext = os.path.splitext(child)

        if should_skip_application_import_file(child, full_path):
            continue

        if os.path.isdir(full_path):
            names.add(child)
            continue

        if filename.endswith(u".gvl"):
            if ext == u".st":
                names.add(filename.replace(u".gvl", u""))
            continue
        if filename.endswith(u".vis"):
            if ext == u".xml":
                names.add(filename.replace(u".vis", u""))
            continue
        if u"." in filename:
            # Parent.Child.xml / Parent.Method.st — sub-POU; parent is removed only
            # when Parent.xml or Parent.st is present in the application folder.
            continue
        if ext == u".xml":
            names.add(filename)
        elif ext == u".st":
            names.add(filename)
    return names


def remove_tracked_objects(obj_list, import_dir_path=None):
    import_names = None
    if import_dir_path is not None:
        import_names = collect_application_import_object_names(import_dir_path)

    for obj in obj_list:
        name = obj.get_name()
        obj_type = get_object_type(obj)
        if obj_type in OBJECT_TYPE_TO_EXPORT_FUNCTION:
            safe_print(u"Removing " + name)
            obj.remove()
        elif import_names is not None and name in import_names:
            safe_print(u"Removing " + name)
            obj.remove()