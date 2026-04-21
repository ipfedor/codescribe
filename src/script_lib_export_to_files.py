# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
from __future__ import print_function

import os
import shutil
import sys
#import imp

import scriptengine  # type: ignore

from entrypoint import get_src_folder
from import_export import OBJECT_TYPE_TO_EXPORT_FUNCTION
from object_type import get_object_type
from util import *


# ----------------------------------------------------------------------
# Настройка кодировки по умолчанию
# ----------------------------------------------------------------------
#imp.reload(sys)
#sys.setdefaultencoding('utf-8')

def export_child(child_obj, parent_obj, parent_folder_path):
    child_obj_type = get_object_type(child_obj)
    export_fn = OBJECT_TYPE_TO_EXPORT_FUNCTION.get(child_obj_type)
    if export_fn is not None:
        export_fn(child_obj, parent_obj, parent_folder_path, export_child)


# Список имен объектов, которые НЕ нужно экспортировать (служебные)
SKIP_NAMES = [
    u'Library Manager', u'Task Configuration', u'Symbol Configuration',
    u'Visualization Manager', u'Alarm Configuration', u'Recipe Manager'
]


def should_skip(obj):
    """Определяет, нужно ли пропустить объект при экспорте"""
    name = obj.get_name()
    if isinstance(name, str) and not isinstance(name, unicode):
        name = fix_encoding(name)
    if name in SKIP_NAMES:
        return True
    obj_type = get_object_type(obj)
    if obj_type not in OBJECT_TYPE_TO_EXPORT_FUNCTION:
        return True
    return False


def export_library_object(obj, parent_folder_path):
    """Экспортирует один объект библиотеки (POU, DUT, GVL и т.д.)"""
    obj_type = get_object_type(obj)
    export_fn = OBJECT_TYPE_TO_EXPORT_FUNCTION.get(obj_type)
    if export_fn is not None:
        export_fn(obj, None, parent_folder_path, export_child)


def export_folder(folder_obj, parent_folder_path):
    """Рекурсивно экспортирует содержимое папки с исправлением кодировки имён"""
    folder_name = folder_obj.get_name()
    if isinstance(folder_name, str) and not isinstance(folder_name, unicode):
        folder_name = fix_encoding(folder_name)
    # Формируем путь в unicode
    folder_path = os.path.join(parent_folder_path, folder_name)
    # Создаём папку
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)

    for child in folder_obj.get_children():
        if should_skip(child):
            continue
        child_type = get_object_type(child)
        if child.get_children():
            export_folder(child, folder_path)
        else:
            export_fn = OBJECT_TYPE_TO_EXPORT_FUNCTION.get(child_type)
            if export_fn is not None:
                export_fn(child, folder_obj, folder_path, export_child)


# ----------------------------------------------------------------------
# Основной блок
# ----------------------------------------------------------------------
try:
    print_python_version()
    assert_project_open()

    src_folder = get_src_folder(scriptengine.projects.primary)
    src_folder = ensure_unicode_path(src_folder)
    safe_print(u"Writing to: " + src_folder)

    # Безопасное удаление и создание корневой папки
    if os.path.exists(src_folder):
        shutil.rmtree(src_folder)
    os.mkdir(src_folder)

    project = scriptengine.projects.primary
    top_level_objs = project.get_children()

    for obj in top_level_objs:
        if should_skip(obj):
            continue

        if obj.get_children():
            export_folder(obj, src_folder)
        else:
            export_library_object(obj, src_folder)

    safe_print("Done!")
except Exception as e:
    safe_print("ERROR: " + str(e))
    raise e