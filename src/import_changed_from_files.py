# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import io
import os

from entrypoint import find_application, get_device_entrypoints, get_src_folder
from git_import import import_git_base_ref, list_git_changed_under
from import_export import *
from import_export import SUB_POU_MEMBER_TYPES
from import_from_files import first_word_of_line_iter, import_directory_child
from object_type import ObjectType, get_object_type
from util import *


def _normalize_relpath(path):
    return path.replace("\\", "/")


def _parse_application_relpath(relpath):
    relpath = _normalize_relpath(relpath)
    if relpath.lower().endswith(u".xml.st"):
        return {"scope": "skip"}

    dirname = os.path.dirname(relpath)
    if dirname == ".":
        dirname = u""
    basename = os.path.basename(relpath)
    filename, ext = os.path.splitext(basename)

    if filename.endswith(u".gvl"):
        if ext == u".st":
            return {
                "scope": "top",
                "name": filename.replace(u".gvl", u""),
                "parent_path": dirname,
            }
        return {"scope": "skip"}

    if filename.endswith(u".vis"):
        return {"scope": "skip"}

    if u"." in filename:
        if ext in (u".xml", u".st"):
            parent_name, child_rest = filename.split(u".", 1)
            if ext == u".xml":
                child_name = child_rest
            else:
                child_name = child_rest
            return {
                "scope": "sub",
                "parent_name": parent_name,
                "child_name": child_name,
                "parent_path": dirname,
            }
        return {"scope": "skip"}

    if ext in (u".xml", u".st"):
        return {"scope": "top", "name": filename, "parent_path": dirname}
    return {"scope": "skip"}


def _resolve_parent_object(root_obj, parent_path):
    obj = root_obj
    if not parent_path:
        return obj
    for part in parent_path.replace("\\", "/").split("/"):
        if not part:
            continue
        obj = first_of_type_or_error(
            obj.find(part),
            ObjectType.FOLDER,
            u"Folder " + part + u" not found in project",
        )
    return obj


def _expand_changed_relpaths(application_folder, relpaths):
    expanded = set(_normalize_relpath(p) for p in relpaths)
    for rel in list(expanded):
        dirname = os.path.dirname(rel)
        if dirname == ".":
            dirname = u""
        basename = os.path.basename(rel)
        filename, ext = os.path.splitext(basename)
        if filename.endswith(u".gvl") and ext == u".xml":
            st_name = filename + u".st"
            st_rel = os.path.join(dirname, st_name) if dirname else st_name
            st_rel = _normalize_relpath(st_rel)
            st_abs = os.path.join(application_folder, st_rel.replace("/", os.sep))
            if os.path.isfile(ensure_unicode_path(st_abs)):
                expanded.add(st_rel)
    return expanded


def _prefix_has_changes(dir_rel, changed_set):
    dir_rel = _normalize_relpath(dir_rel).rstrip("/")
    if dir_rel in changed_set:
        return True
    prefix = dir_rel + u"/"
    for path in changed_set:
        if path.startswith(prefix):
            return True
    return False


def remove_object_for_relpath(root_obj, parsed):
    if parsed.get("scope") == "skip":
        return

    if parsed["scope"] == "sub":
        container = _resolve_parent_object(root_obj, parsed.get("parent_path", u""))
        parent_name = parsed["parent_name"]
        parent = first_of_type_or_none(container.find(parent_name), ObjectType.POU)
        if parent is None:
            return
        child_name = parsed["child_name"]
        for child in list(parent.get_children()):
            if child.get_name() == child_name and get_object_type(child) in SUB_POU_MEMBER_TYPES:
                safe_print(u"Removing " + parent_name + u"." + child_name)
                child.remove()
                return
        return

    if parsed["scope"] == "top":
        parent = _resolve_parent_object(root_obj, parsed.get("parent_path", u""))
        name = parsed["name"]
        target = None
        for child in list(parent.get_children()):
            if child.get_name() == name:
                target = child
                break
        if target is None:
            target = _find_object_by_name_subtree(parent, name)
        if target is None:
            return
        obj_type = get_object_type(target)
        if obj_type in OBJECT_TYPE_TO_EXPORT_FUNCTION or obj_type == ObjectType.UNKNOWN:
            safe_print(u"Removing " + name)
            target.remove()
        return


def import_directory_filtered(
    dir_path, dir_parent_obj, application_folder, application_obj, changed_relpaths
):
    dir_path = ensure_unicode_path(dir_path)
    application_folder = ensure_unicode_path(application_folder)
    changed_set = _expand_changed_relpaths(application_folder, changed_relpaths)

    def import_dir_fn(dp, dpo, app_obj=None):
        import_directory_filtered(
            dp, dpo, application_folder, app_obj or application_obj, changed_relpaths
        )

    children = sorted(os.listdir(dir_path), key=lambda x: x.count("."))
    to_import = []
    for child in children:
        full_path = ensure_unicode_path(os.path.join(dir_path, child))
        child_rel = _normalize_relpath(os.path.relpath(full_path, application_folder))

        if os.path.isdir(full_path):
            if not _prefix_has_changes(child_rel, changed_set):
                continue
            folder_obj = ensure_folder(dir_parent_obj, child)
            import_directory_filtered(
                full_path, folder_obj, application_folder, application_obj, changed_relpaths
            )
            continue

        if child_rel not in changed_set:
            continue
        to_import.append(child)

    pending_guids = collect_pending_native_import_guids(dir_path, to_import)
    deferred = []
    for child in to_import:
        full_path = ensure_unicode_path(os.path.join(dir_path, child))
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


def import_changed_from_files(project):
    # Keep unicode paths end-to-end (Windows Python 2.7; never utf-8 bytes).
    src_folder = ensure_unicode_path(get_src_folder(project))
    base_ref = import_git_base_ref()
    safe_print(u"Reading git changes from: " + src_folder)
    safe_print(u"Git base ref: " + base_ref)
    safe_print(
        u"Note: Import Changed covers Device/application/ only "
        u"(not devices/ or communication/). Use Import From Files for modules."
    )
    assert_path_exists(src_folder)

    any_changes = False

    for device_obj in get_device_entrypoints(project):
        device_folder = ensure_unicode_path(os.path.join(src_folder, device_obj.get_name()))
        if not os.path.isdir(device_folder):
            continue

        application = find_application(device_obj)
        application_folder = ensure_unicode_path(os.path.join(device_folder, "application"))
        if not os.path.isdir(application_folder):
            continue

        try:
            changed, deleted = list_git_changed_under(application_folder, base_ref)
        except ValueError as e:
            raise ValueError(
                unicode(e)
                + u"\nIncremental import requires a git repository. "
                u"Use Import From Files for a full import."
            )

        if not changed and not deleted:
            safe_print(u"No git changes under " + application_folder)
            continue

        any_changes = True
        safe_print(u"Changed files (" + unicode(len(changed)) + u"): " + application_folder)
        for rel in changed:
            safe_print(u"  + " + rel)
        if deleted:
            safe_print(u"Deleted files (" + unicode(len(deleted)) + u"):")
            for rel in deleted:
                safe_print(u"  - " + rel)

        for rel in deleted:
            rel_os = rel.replace("/", os.sep)
            full_path = ensure_unicode_path(os.path.join(application_folder, rel_os))
            child = os.path.basename(rel_os)
            if should_skip_application_import_file(child, full_path):
                safe_print(u"Skipping orphan removal (template object): " + rel)
                continue
            parsed = _parse_application_relpath(rel)
            remove_object_for_relpath(application, parsed)

        import_directory_filtered(
            application_folder, application, application_folder, application, changed
        )

    if not any_changes:
        safe_print(u"No changed application files to import.")
