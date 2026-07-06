# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
from __future__ import print_function

import scriptengine  # type: ignore

from import_changed_from_files import import_changed_from_files
from util import *

try:
    print_python_version()
    assert_project_open()

    ui_continue = scriptengine.system.ui.prompt(
        "Import Changed will update POUs/GVLs from git-changed files only "
        "(compared to HEAD by default).\n\n"
        "Unexported changes in the project for those objects will be overwritten.\n\n"
        "Continue?",
        choice=scriptengine.PromptChoice.YesNo,
        default_result=scriptengine.PromptResult.No,
        store_description="Don't show again",
        store_key="import_changed_from_files_confirm",
    )

    if ui_continue == scriptengine.PromptResult.Yes:
        import_changed_from_files(scriptengine.projects.primary)
except Exception as e:
    try:
        print(e)
    except UnicodeEncodeError:
        print(unicode(e).encode("utf-8"))
    raise e

print("Done!")
