# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import io
import os
import re

from object_type import ObjectType, get_object_type
from util import *

IMPLEMENTATION_DELIMITER_SPLIT = u"// --- BEGIN IMPLEMENTATION ---"
IMPLEMENTATION_DELIMITER_INSERT = u"\n" + IMPLEMENTATION_DELIMITER_SPLIT + u"\n\n"


def safe_print(msg):
    """Безопасная печать строки с поддержкой UTF-8 в Python 2.7"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8'))


def ensure_bytes_path(path):
    """Преобразует unicode путь в байтовую строку UTF-8 для вызовов os / shutil"""
    if isinstance(path, unicode):
        return path.encode('utf-8')
    return path


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


def write_native(obj, path, recursive=False):
    # path может быть байтовой строкой или unicode; для export_native нужно передать str в Python 2.7?
    # obj.export_native ожидает, вероятно, байтовую строку. Преобразуем в bytes.
    path_bytes = ensure_bytes_path(path)
    obj.export_native(path_bytes, recursive=recursive)

    # используем io.open для чтения/записи UTF-8
    with io.open(path_bytes, "r+", encoding='utf-8') as f:
        lines = f.read()

        # XXX: Warning! Overwriting Id's broke visualisations
        # It's probably a bad idea to overwrite Id's and UUIDs, even if it is annoying to have them show up in the diff
        # Stick to just overwriting timestamps for now

        # uuid_replaced = re.sub(
        #     r'(^.+<Single Name="(?:EventPOUGuid|ParentSVNodeGuid|ParentGuid|LmGuid|LmStructTypeGuid|LmArrayTypeGuid|IoConfigGlobalsGuid|IoConfigGLobalsMappingGuid|IoConfigVarConfigGuid|IoConfigErrorPouGuid)".+?>).+(<\/Single>$)',
        #     r"\g<1>00000000-0000-0000-0000-000000000000\g<2>",
        #     lines,
        #     flags=re.MULTILINE,
        # )

        # match any tags with Timestamp or Id and replace their contents with "0"
        # timestamp_replaced = re.sub(
        #     r'(^.+<Single Name="(?:Timestamp|Id)" Type="long">).+(<\/Single>$)',
        #     r"\g<1>0\g<2>",
        #     lines,
        #     flags=re.MULTILINE,
        # )

        timestamp_replaced = re.sub(
            ur'(^.+<Single Name="(?:Timestamp)" Type="long">).+(<\/Single>$)',
            ur"\g<1>0\g<2>",
            lines,
            flags=re.MULTILINE,
        )

        f.seek(0)
        f.write(timestamp_replaced)
        f.truncate()


def read_native(f, obj):
    # f - это путь (строка) или файловый объект? По контексту - путь.
    # В вызовах read_native(os.path.join(...), dir_parent_obj) - передаётся путь.
    # Преобразуем в байтовую строку для import_native.
    path_bytes = ensure_bytes_path(f)
    obj.import_native(path_bytes)


def export_folder(child_obj, parent_obj, parent_folder_path, export_child_fn):
    child_obj_folder = os.path.join(parent_folder_path, child_obj.get_name())
    child_obj_folder_bytes = ensure_bytes_path(child_obj_folder)
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
        file_path_bytes = ensure_bytes_path(file_path)
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
    full_path_bytes = ensure_bytes_path(full_path)
    with io.open(full_path_bytes, "r", encoding='utf-8') as f:
        import_st(f, pou_obj)


def export_gvl(child_obj, parent_obj, parent_folder_path, export_child_fn):
    """
    Exports native xml and structured text representation.
    This is because we need to support EVL and NVL as well, using this function.
    """
    write_native(child_obj, os.path.join(parent_folder_path, child_obj.get_name() + u".gvl.xml"), recursive=False)
    file_path = os.path.join(parent_folder_path, child_obj.get_name() + u".gvl.st")
    file_path_bytes = ensure_bytes_path(file_path)
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
    gvl_xml_path_bytes = ensure_bytes_path(gvl_xml_path)
    if os.path.exists(gvl_xml_path_bytes):
        import_native(gvl_xml_path, dir_path, dir_parent_obj, import_dir_fn)  # import_native ожидает путь
        imported_obj = first_of_type_or_error(
            dir_parent_obj.find(name), ObjectType.GVL, name + u" GVL should have been created, but cannot be found"
        )
    else:
        imported_obj = dir_parent_obj.create_gvl(name)

    full_path = os.path.join(dir_path, child)
    full_path_bytes = ensure_bytes_path(full_path)
    with io.open(full_path_bytes, "r", encoding='utf-8') as f:
        import_st_decl_only(f, imported_obj)


def export_native(child_obj, parent_obj, parent_folder_path, export_child_fn):
    write_native(child_obj, os.path.join(parent_folder_path, child_obj.get_name() + u".xml"), recursive=False)


def export_native_recursive(child_obj, parent_obj, parent_folder_path, export_child_fn):
    write_native(child_obj, os.path.join(parent_folder_path, child_obj.get_name() + u".xml"), recursive=True)


def import_native(child, dir_path, dir_parent_obj, import_dir_fn):
    read_native(os.path.join(dir_path, child), dir_parent_obj)


def export_dut(child_obj, parent_obj, parent_folder_path, export_child_fn):
    file_path = os.path.join(parent_folder_path, child_obj.get_name() + u".st")
    file_path_bytes = ensure_bytes_path(file_path)
    with io.open(file_path_bytes, "w", encoding='utf-8') as f:
        f.write(child_obj.textual_declaration.text)


def import_dut(child, dir_path, dir_parent_obj, import_dir_fn):
    filename, _ = os.path.splitext(child)
    dut_obj = dir_parent_obj.create_dut(filename)
    full_path = os.path.join(dir_path, child)
    full_path_bytes = ensure_bytes_path(full_path)
    with io.open(full_path_bytes, "r", encoding='utf-8') as f:
        content = f.read()
        dut_obj.textual_declaration.replace(content.strip() + u"\n")


def export_method(child_obj, parent_obj, parent_folder_path, export_child_fn):
    if child_obj.has_textual_implementation:
        file_path = os.path.join(parent_folder_path, parent_obj.get_name() + u"." + child_obj.get_name() + u".st")
        file_path_bytes = ensure_bytes_path(file_path)
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
    full_path_bytes = ensure_bytes_path(full_path)
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
    full_path_bytes = ensure_bytes_path(full_path)
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
    ObjectType.EVC: export_native,
    ObjectType.VISUALISATION: export_native,
    ObjectType.TASK_CONFIGURATION: export_native_recursive,
    ObjectType.DUT: export_dut,
    ObjectType.METHOD: export_method,
    ObjectType.PROPERTY: export_sub_pou,
    ObjectType.ACTION: export_sub_pou,
    ObjectType.TRANSITION: export_sub_pou,
}


def remove_tracked_objects(obj_list):
    for obj in obj_list:
        if get_object_type(obj) in OBJECT_TYPE_TO_EXPORT_FUNCTION:
            safe_print(u"Removing " + obj.get_name())
            obj.remove()