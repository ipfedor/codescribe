# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

base = None
for n in os.listdir(r"d:\projects"):
    if n.startswith("1952"):
        base = os.path.join(
            r"d:\projects",
            n,
            "plc",
            n,
            "Device",
            "devices",
            "Right_Expansion_Module",
        )
        break

a1 = open(os.path.join(base, "A1.xml"), encoding="utf-8", errors="replace").read()
a2 = open(os.path.join(base, "A2.xml"), encoding="utf-8", errors="replace").read()

print("A1 i_autostop count", a1.count("i_autostop"))
print("A2 i_kc15_km count", a2.count("i_kc15_km"))

# Find every occurrence of i_kc15_km with context
for label, text, needle in (
    ("A1", a1, "i_autostop"),
    ("A2", a2, "i_kc15_km"),
):
    print("====", label, needle)
    for m in re.finditer(re.escape(needle), text):
        start = max(0, m.start() - 400)
        end = min(len(text), m.end() + 200)
        snip = text[start:end]
        # classify context
        if "Name=\"Variable\"" in snip[max(0, 400 - 80) : 400 + 80]:
            kind = "Variable field"
        elif "VisibleName" in snip or "Description" in snip:
            kind = "name/desc?"
        else:
            kind = "other"
        print("---", kind, "at", m.start())
        print(snip)
        print()

# For A2: walk ActualAddr and show exact List2 content (not just Variable in window)
print("==== A2 channel List2 exact")
for m in re.finditer(
    r'<Single Name="ActualAddr" Type="string">([^<]*)</Single>\s*'
    r'<Single Name="AutomaticAddress"[^>]*>.*?</Single>\s*'
    r'<Single Name="IecAddress"[^>]*>.*?</Single>\s*'
    r'<Single Name="Mappings"[^>]*>\s*'
    r'(<List2 Name="Mappings"[^>]*/?>.*?</List2>|<List2 Name="Mappings"\s*/>|<List2 Name="Mappings"></List2>)',
    a2,
    re.S,
):
    addr = m.group(1)
    list2 = m.group(2)
    compact = re.sub(r"\s+", " ", list2)[:180]
    has_var = "Variable" in list2
    print(addr, "has_var=", has_var, "|", compact)
