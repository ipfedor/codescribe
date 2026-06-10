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


def import_folder(child, dir_path, dir_parent_obj, import_dir_fn):
    dir_parent_obj.create_folder(child)
    folder_obj = first_of_type_or_error(
        dir_parent_obj.find(child),
        ObjectType.FOLDER,
        u"Folder of name " + child + u" should have been created, but cannot be found",
    )
    import_dir_fn(os.path.join(dir_path, child), folder_obj)


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


def import_native(child, dir_path, dir_parent_obj, import_dir_fn):
    read_native(os.path.join(dir_path, child), dir_parent_obj)


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


def remove_tracked_objects(obj_list):
    for obj in obj_list:
        if get_object_type(obj) in OBJECT_TYPE_TO_EXPORT_FUNCTION:
            safe_print(u"Removing " + obj.get_name())
            obj.remove()