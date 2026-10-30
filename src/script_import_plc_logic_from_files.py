# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
from __future__ import print_function

import scriptengine  # type: ignore

from import_from_files import import_plc_logic_from_files
from util import *

try:
    print_python_version()
    assert_project_open()

    ui_continue = scriptengine.system.ui.prompt(
        "Import PLC Logic will overwrite unexported Application changes "
        "(POUs, GVLs, DUTs under Device/application/).\n\n"
        "Device tree (Modbus/Ethernet) and Communication are not imported.\n\n"
        "Do you want to continue?",
        choice=scriptengine.PromptChoice.YesNo,
        default_result=scriptengine.PromptResult.No,
        store_description="Don't show again",
        store_key="import_plc_logic_from_files_confirm",
    )

    if ui_continue == scriptengine.PromptResult.Yes:
        import_plc_logic_from_files(scriptengine.projects.primary)
except Exception as e:
    try:
        print(e)
    except UnicodeEncodeError:
        print(unicode(e).encode("utf-8"))
    raise e

print("Done!")
