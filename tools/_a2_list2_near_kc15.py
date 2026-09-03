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

def show_all_list2_near(path, needle, window=1200):
    t = open(path, encoding="utf-8", errors="replace").read()
    print("FILE", path, "size", os.path.getsize(path))
    idx = t.find(needle)
    if idx < 0:
        print("  needle not found:", needle)
        return
    # find all List2 Mappings within +/- 3k of first VisibleName Default occurrence
    # Better: for each 'Default">needle' find following Mappings List2 until next Default or far
    for m in re.finditer(
        r'Default" Type="string">' + re.escape(needle) + r"</Single>", t
    ):
        chunk = t[m.start() : m.start() + 8000]
        print("  -- after VisibleName/Default at", m.start())
        for lm in re.finditer(r'<List2 Name="Mappings"[^>]*/?>.*?(?:</List2>|/>)', chunk, re.S):
            blob = re.sub(r"\s+", " ", lm.group(0))
            print("    List2@", m.start() + lm.start(), ":", blob[:220])
            if lm.start() > 3500:
                break

a2 = os.path.join(base, "A2.xml")
a2bak = a2 + ".bak_before_map"
show_all_list2_near(a2, "i_kc15_km")
print()
show_all_list2_near(a2bak, "i_kc15_km")
print()
# Count empty self-closing List2 in A2 vs filled
for label, p in (("A2", a2), ("A2.bak", a2bak), ("A1", os.path.join(base, "A1.xml"))):
    t = open(p, encoding="utf-8", errors="replace").read()
    empty = len(re.findall(r'<List2 Name="Mappings"\s*/>', t))
    filled = len(re.findall(r'<List2 Name="Mappings">\s*<Single', t))
    print(label, "empty self-close", empty, "filled with Single", filled)
