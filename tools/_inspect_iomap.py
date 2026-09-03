# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

base = r"d:\projects"
found = None
for name in os.listdir(base):
    if not name.startswith("1952"):
        continue
    cand = os.path.join(
        base, name, "plc", name, "Device", "devices", "Right_Expansion_Module", "A1.xml"
    )
    if os.path.isfile(cand):
        found = cand
        break

with open(found, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

# find first Variable and print surrounding 1500 chars
m = re.search(r'Name="Variable"', text)
print("first Variable at", m.start())
print(text[max(0, m.start() - 800) : m.start() + 600])
print("====")
# IoMapping block sample
m2 = re.search(r"IoMapping", text)
print("first IoMapping at", m2.start() if m2 else None)
if m2:
    print(text[m2.start() : m2.start() + 1200])

# list all Single Name= near Variable parents
names = set(re.findall(r'<Single Name="([^"]+)"', text[m.start() - 2000 : m.start() + 500]))
print("nearby names", sorted(names)[:40])

# Guid-like fields near first variable
chunk = text[max(0, m.start() - 2500) : m.start() + 800]
for g in re.findall(r'<Single Name="([^"]*Guid[^"]*)"[^>]*>([^<]*)</Single>', chunk):
    print("guid field", g)
