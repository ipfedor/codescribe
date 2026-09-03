# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import io
import os

from communication_import_export import import_communication
from device_tree_import_export import import_device_tree_siblings
from entrypoint import (
    find_application,
    find_communication,
    get_device_entrypoints,
    get_src_folder,
)
from import_export import *
from util import *


def first_word_of_line_iter(f):
    for line in f.readlines():
        # line уже будет unicode, если файл открыт с encoding='utf-8'
        words = line.strip().split()
        if len(words) > 0:
            yield words[0]


def detect_st_object_kind(full_path):
    """
    Peek ST file keywords (TYPE vs PROGRAM/FUNCTION_BLOCK/FUNCTION).

    Must close the file before import_pou_st/import_dut reopen it: on Windows
    Python 2.7 a second open of the same path raises Errno 32 (sharing violation).
    """
    full_path_bytes = ensure_unicode_path(full_path)
    with io.open(full_path_bytes, "r", encoding="utf-8") as f:
        for word in first_word_of_line_iter(f):
            if word == u"TYPE":
                return u"dut"
            if word in [u"PROGRAM", u"FUNCTION_BLOCK", u"FUNCTION"]:
                return u"pou"
    return None


def import_directory(dir_path, dir_parent_obj, application_obj=None):
    if application_obj is None:
        application_obj = dir_parent_obj

    def import_dir_fn(dp, dpo, app_obj=None):
        import_directory(dp, dpo, app_obj or application_obj)

    children = sorted(os.listdir(dir_path), key=lambda x: x.count("."))
    pending_guids = collect_pending_native_import_guids(dir_path, children)
    deferred = []
    for child in children:
        full_path = os.path.join(dir_path, child)
        if should_defer_native_import(
            child, full_path, application_obj, pending_guids
        ):
            deferred.append(child)
            continue
        import_directory_child(
            child, dir_path, dir_parent_obj, import_dir_fn, application_obj
        )
    for child in deferred:
        safe_print(u"Deferred import: " + child)
        import_directory_child(
            child, dir_path, dir_parent_obj, import_dir_fn, application_obj
        )


def import_directory_child(
    child, dir_path, dir_parent_obj, import_dir_fn=None, application_obj=None
):
    # Extra converter artifacts (sidecar ST for exported XML) must not be imported into CODESYS.
    # Example: `Something.xml.st`
    try:
        if child.lower().endswith(".xml.st"):
            return
    except Exception:
        pass

    if import_dir_fn is None:
        import_dir_fn = import_directory

    if application_obj is None:
        application_obj = dir_parent_obj

    full_path = os.path.join(dir_path, child)
    if should_skip_application_import_file(child, full_path):
        safe_print(u"Skipping import (template object): " + child)
        return

    remove_object_for_import_child(
        child, dir_path, dir_parent_obj, application_obj
    )

    filename, ext = os.path.splitext(child)

    if os.path.isdir(full_path):
        import_folder(
            child, dir_path, dir_parent_obj, import_dir_fn, application_obj
        )

    if filename.endswith(".gvl"):
        if ext == ".xml":
            # this is just here to point out that the xml is imported alongside the st file
            pass
        if ext == ".st":
            import_gvl(child, dir_path, dir_parent_obj, import_dir_fn)
    elif filename.endswith(".vis"):
        if ext == ".xml":
            import_native(
                child, dir_path, dir_parent_obj, import_dir_fn, application_obj
            )
    elif "." in filename:
        # . means some sort of sub POU
        if ext == ".xml":
            import_sub_pou(child, dir_path, dir_parent_obj, import_dir_fn)
        if ext == ".st":
            # currently only methods are exported as ST if possible
            import_method_st(child, dir_path, dir_parent_obj, import_dir_fn)
    else:
        if ext == ".xml":
            import_native(
                child, dir_path, dir_parent_obj, import_dir_fn, application_obj
            )
        if ext == ".st":
            kind = detect_st_object_kind(full_path)
            if kind == u"dut":
                import_dut(child, dir_path, dir_parent_obj, import_dir_fn)
            elif kind == u"pou":
                import_pou_st(child, dir_path, dir_parent_obj, import_dir_fn)


def import_from_files(project):
    src_folder = get_src_folder(project)
    safe_print("Reading from: " + src_folder)
    # Преобразуем путь в байтовую строку для проверки существования
    src_folder_bytes = ensure_unicode_path(src_folder)
    assert_path_exists(src_folder_bytes)

    for device_obj in get_device_entrypoints(project):
        device_folder = os.path.join(src_folder, device_obj.get_name())
        device_folder_bytes = ensure_unicode_path(device_folder)
        assert_path_exists(device_folder_bytes)

        application = find_application(device_obj)
        application_folder = os.path.join(device_folder, "application")
        import_directory(application_folder, application, application)
        remove_orphans_in_parent(application, application_folder)

        communication = find_communication(device_obj)
        if communication is not None:
            import_communication(communication, device_folder)

        import_device_tree_siblings(device_obj, device_folder)
