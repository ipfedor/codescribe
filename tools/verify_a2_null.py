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

t = open(os.path.join(base, "A2.xml"), encoding="utf-8").read()
matches = list(re.finditer(r'Default" Type="string">i_kc15_km</Single>', t))
print("Default i_kc15_km count", len(matches))
for i, m in enumerate(matches):
    chunk = t[m.start() : m.start() + 3500]
    lists = list(
        re.finditer(r'<List2 Name="Mappings"[^>]*/?>.*?(?:</List2>|/>)', chunk, re.S)
    )
    print("occurrence", i, "at", m.start(), "List2 in next 3.5k", len(lists))
    for j, lm in enumerate(lists[:3]):
        blob = re.sub(r"\s+", " ", lm.group(0))[:220]
        print(" ", j, blob)
