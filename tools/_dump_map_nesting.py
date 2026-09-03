# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

base = None
for n in os.listdir(r"d:\projects"):
    if n.startswith("1952"):
        base = os.path.join(
            r"d:\projects", n, "plc", n, "Device", "devices", "Right_Expansion_Module"
        )
        break

def dump_structure(fn, needle):
    t = open(os.path.join(base, fn), encoding="utf-8", errors="replace").read()
    # find first Default>needle then print indentation-ish tags until 2nd Variable or 4k
    m = re.search(r'Default" Type="string">' + re.escape(needle) + r"</Single>", t)
    chunk = t[m.start() - 200 : m.start() + 4500]
    # keep only relevant lines
    for line in chunk.splitlines():
        s = line.strip()
        if any(
            k in s
            for k in (
                "VisibleName",
                "Description",
                "SubElements",
                "IoMapping",
                "ActualAddr",
                "Mappings",
                "Variable",
                "CreateVariable",
                "List2",
                "Bit0",
                "Bit1",
                "InputCh",
            )
        ) or s.startswith("</"):
            if len(s) > 160:
                s = s[:160] + "..."
            print(s)

print("==== A1 i_autostop")
dump_structure("A1.xml", "i_autostop")
print("\n==== A2 i_kc15_km")
dump_structure("A2.xml", "i_kc15_km")
