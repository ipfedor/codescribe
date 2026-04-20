# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import os

import scriptengine  # type: ignore

# Используем unicode-строки для корректной работы с путями, содержащими не-ASCII символы
PROJECT_EXT = u".project"
TEMPLATE_FILEPART = u"_template_v"


def find_template_paths_and_versions(project):
    # Используем путь из переданного проекта, а не глобальный scriptengine.projects.primary
    working_dir = os.path.dirname(project.path)
    project_name, _ = os.path.splitext(os.path.basename(project.path))

    template_name_start = project_name + TEMPLATE_FILEPART

    template_paths = []
    template_versions = []

    # os.listdir вернёт unicode, если working_dir — unicode
    for child in os.listdir(working_dir):
        name, ext = os.path.splitext(child)
        if ext == PROJECT_EXT and name.startswith(template_name_start):
            version_str = name.replace(template_name_start, u"")
            try:
                version = int(version_str)
            except ValueError:
                # В сообщении об ошибке могут быть не-ASCII символы, но оно будет выведено через обработку в вызывающем коде
                raise ValueError(u"Found a template with invalid version: " + version_str)

            template_paths.append(os.path.join(working_dir, child))
            template_versions.append(version)

    return template_paths, template_versions


def generate_template_path(project, version_number):
    working_dir = os.path.dirname(project.path)
    project_name, _ = os.path.splitext(os.path.basename(project.path))

    template_name_start = project_name + TEMPLATE_FILEPART

    return os.path.join(working_dir, template_name_start + unicode(version_number) + PROJECT_EXT)

