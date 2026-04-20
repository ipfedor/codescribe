# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
from __future__ import print_function

import os
import shutil

import scriptengine  # type: ignore

from communication_import_export import remove_tracked_communication_devices
from entrypoint import find_application, find_communication, get_device_entrypoints
from import_export import *
from project_template import find_template_paths_and_versions, generate_template_path
from util import *


def safe_print(msg):
    """Безопасная печать строки с поддержкой UTF-8 в Python 2.7"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8'))


def get_new_template_version(template_versions):
    if len(template_versions) < 1:
        safe_print("No existing template found!")
        safe_print("New template version: 1")
        return 1

    current_version = max(template_versions)
    new_version = current_version + 1
    safe_print("Found a template with version: " + str(current_version))
    safe_print("New template version: " + str(new_version))
    return new_version


def delete_old_templates(template_paths):
    safe_print("Deleting " + str(len(template_paths)) + " old template(s):")
    for path in template_paths:
        # Безопасный вывод пути
        try:
            safe_print("    " + path)
        except UnicodeEncodeError:
            safe_print("    " + path.encode('utf-8'))
        # Безопасное удаление файла
        if isinstance(path, unicode):
            path = path.encode('utf-8')
        os.remove(path)


try:
    print_python_version()
    assert_project_open()

    template_paths, template_versions = find_template_paths_and_versions(scriptengine.projects.primary)
    new_template_version = get_new_template_version(template_versions)
    new_template_path = generate_template_path(scriptengine.projects.primary, new_template_version)

    # Безопасное копирование: преобразуем пути в байтовые строки, если это unicode
    src_path = scriptengine.projects.primary.path
    if isinstance(src_path, unicode):
        src_path = src_path.encode('utf-8')
    if isinstance(new_template_path, unicode):
        new_template_path = new_template_path.encode('utf-8')
    shutil.copyfile(src_path, new_template_path)
    scriptengine.projects.open(new_template_path, primary=False)

    template_project = scriptengine.projects.get_by_path(new_template_path)

    for device_obj in get_device_entrypoints(template_project):
        application = find_application(device_obj)
        remove_tracked_objects(application.get_children())
        communication = find_communication(device_obj)
        if communication is not None:
            remove_tracked_communication_devices(communication)

    template_project.save()

    if len(template_paths) > 0:
        delete_old_templates(template_paths)
except Exception as e:
    # Безопасный вывод исключения
    try:
        print(e)
    except UnicodeEncodeError:
        print(unicode(e).encode('utf-8'))
    raise e

safe_print("Done!")