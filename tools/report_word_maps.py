# -*- coding: utf-8 -*-
import os
import re

base = None
for n in os.listdir("d:/projects"):
    if n.startswith("1952"):
        base = os.path.join(
            "d:/projects", n, "plc", n, "Device", "devices", "Right_Expansion_Module"
        )
        break

for fn in ("A1.xml", "A2.xml"):
    t = open(os.path.join(base, fn), encoding="utf-8").read()
    print("====", fn)
    for m in re.finditer(r'ActualAddr" Type="string">(%I[WD][^<]*)</Single>', t):
        window = t[m.end() : m.end() + 700]
        var = re.search(r'Name="Variable" Type="string">([^<]*)</Single>', window)
        empty = bool(re.search(r'<List2 Name="Mappings"\s*/>', window[:400]))
        print(
            " ",
            m.group(1),
            "pos",
            m.start(),
            "var",
            var.group(1) if var else None,
            "empty",
            empty,
        )
