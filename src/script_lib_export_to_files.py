# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
from __future__ import print_function

import os
import shutil

import scriptengine  # type: ignore

from entrypoint import get_src_folder
from import_export import OBJECT_TYPE_TO_EXPORT_FUNCTION
from object_type import get_object_type
from util import *



def safe_print(msg):
    """Безопасная печать строки с поддержкой UTF-8 в Python 2.7"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8'))


def export_child(child_obj, parent_obj, parent_folder_path):
    child_obj_type = get_object_type(child_obj)
    export_fn = OBJECT_TYPE_TO_EXPORT_FUNCTION.get(child_obj_type)
    if export_fn is not None:
        export_fn(child_obj, parent_obj, parent_folder_path, export_child)


def ensure_bytes_path(path):
    """Преобразует unicode путь в байтовую строку UTF-8 для вызовов os / shutil"""
    if isinstance(path, unicode):
        return path.encode('utf-8')
    return path


# Список имен объектов, которые НЕ нужно экспортировать (служебные)
SKIP_NAMES = ['Library Manager', 'Task Configuration', 'Symbol Configuration',
              'Visualization Manager', 'Alarm Configuration', 'Recipe Manager']


def should_skip(obj):
    """Определяет, нужно ли пропустить объект при экспорте"""
    name = obj.get_name()
    if name in SKIP_NAMES:
        return True
    # Пропускаем объекты, которые не являются экспортируемыми типами
    obj_type = get_object_type(obj)
    if obj_type not in OBJECT_TYPE_TO_EXPORT_FUNCTION:
        return True
    return False


def export_library_object(obj, parent_folder_path):
    """Экспортирует один объект библиотеки (POU, DUT, GVL и т.д.)"""
    obj_type = get_object_type(obj)
    export_fn = OBJECT_TYPE_TO_EXPORT_FUNCTION.get(obj_type)
    if export_fn is not None:
        # Для корневых объектов parent_obj = None
        export_fn(obj, None, parent_folder_path, export_child)


def export_folder(folder_obj, parent_folder_path):
    """Рекурсивно экспортирует содержимое папки (например, POUs)"""
    folder_name = folder_obj.get_name()
    folder_path = os.path.join(parent_folder_path, folder_name)
    folder_path_bytes = ensure_bytes_path(folder_path)
    if not os.path.exists(folder_path_bytes):
        os.mkdir(folder_path_bytes)

    for child in folder_obj.get_children():
        if should_skip(child):
            continue
        child_type = get_object_type(child)
        # Если это папка (имеет дочерние элементы), рекурсивно обрабатываем
        if child.get_children():
            export_folder(child, folder_path)
        else:
            # Экспортируем сам объект
            export_fn = OBJECT_TYPE_TO_EXPORT_FUNCTION.get(child_type)
            if export_fn is not None:
                export_fn(child, folder_obj, folder_path, export_child)


try:
    print_python_version()
    assert_project_open()

    src_folder = get_src_folder(scriptengine.projects.primary)
    safe_print("Writing to: " + src_folder)

    # Безопасное удаление и создание папки
    src_folder_bytes = ensure_bytes_path(src_folder)
    if os.path.exists(src_folder_bytes):
        shutil.rmtree(src_folder_bytes)
    os.mkdir(src_folder_bytes)

    project = scriptengine.projects.primary
    top_level_objs = project.get_children()

    for obj in top_level_objs:
        if should_skip(obj):
            continue

        # Если объект является контейнером (папкой с дочерними элементами)
        if obj.get_children():
            export_folder(obj, src_folder)
        else:
            # Одиночный экспортируемый объект (например, POU в корне старого проекта)
            export_library_object(obj, src_folder)

    safe_print("Done!")
except Exception as e:
    try:
        print(e)
    except UnicodeEncodeError:
        print(unicode(e).encode('utf-8'))
    raise e