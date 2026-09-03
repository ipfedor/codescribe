# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

base = r"d:\projects"
a1 = None
for name in os.listdir(base):
    if name.startswith("1952"):
        a1 = os.path.join(
            base, name, "plc", name, "Device", "devices", "Right_Expansion_Module", "A1.xml"
        )
        break

text = open(a1, encoding="utf-8", errors="replace").read(8000)
for m in re.finditer(
    r'<Single Name="([^"]*Guid[^"]*)" Type="System\.Guid">([^<]*)</Single>', text
):
    print(m.group(1), "=>", repr(m.group(2)))
    if m.start() > 4000:
        break

# 1855 reference if exists
ref = r"d:\projects\1855zakaz\plc\plc_main\1855_PLC_Main\Device\devices\Right_Expansion_Module.xml"
if os.path.isfile(ref):
    t2 = open(ref, encoding="utf-8", errors="replace").read()
    print("1855 HostObjectGuid sample")
    hosts = re.findall(
        r'<Single Name="HostObjectGuid" Type="System\.Guid">([^<]*)</Single>', t2
    )
    print("count", len(hosts), "sample", hosts[:2])
    vars_ = re.findall(r'<Single Name="Variable" Type="string">([^<]*)</Single>', t2)
    nonempty = [v for v in vars_ if v.strip()]
    print("Variable nonempty", len(nonempty), "of", len(vars_))
    print("samples", nonempty[:10])
