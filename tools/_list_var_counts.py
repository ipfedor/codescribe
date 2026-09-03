# -*- coding: utf-8 -*-
import os
import re

base = None
for n in os.listdir(r"d:\projects"):
    if n.startswith("1952"):
        base = os.path.join(
            r"d:\projects", n, "plc", n, "Device", "devices", "Right_Expansion_Module"
        )
        break

for fn in sorted(os.listdir(base)):
    if not (fn.endswith(".xml") or "bak" in fn):
        continue
    p = os.path.join(base, fn)
    if not os.path.isfile(p):
        continue
    t = open(p, encoding="utf-8", errors="replace").read()
    n = len(
        [
            v
            for v in re.findall(
                r'Name="Variable" Type="string">([^<]+)</Single>', t
            )
            if v.strip()
        ]
    )
    print("%-28s vars=%3d size=%7d" % (fn, n, os.path.getsize(p)))
