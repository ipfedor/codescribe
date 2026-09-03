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

print("base", base)
for fn in sorted(os.listdir(base)):
    if not fn.endswith(".xml") or fn.endswith(".bak_before_map"):
        continue
    if fn.startswith("."):
        continue
    p = os.path.join(base, fn)
    t = open(p, encoding="utf-8", errors="replace").read()
    vars_ = [
        v
        for v in re.findall(r'Name="Variable" Type="string">([^<]*)</Single>', t)
        if v.strip()
    ]
    create = t.count('Name="CreateVariable" Type="bool">True')
    print(
        "%-8s size=%7d vars=%3d createTrue=%3d sample=%s"
        % (fn, os.path.getsize(p), len(vars_), create, vars_[:4])
    )

# Diff structure around first ActualAddr with mappings in A1 vs A2
for fn in ("A1.xml", "A2.xml"):
    p = os.path.join(base, fn)
    t = open(p, encoding="utf-8", errors="replace").read()
    print("====", fn)
    # find first IoMapping with ActualAddr %IX
    m = re.search(
        r'<Single Name="ActualAddr" Type="string">(%IX[^<]*)</Single>.*?Name="Mappings".{0,400}',
        t,
        re.S,
    )
    if m:
        print(m.group(0)[:500].replace("\n", "\n"))
    else:
        print("no %IX ActualAddr match")
    # count empty vs filled mapping lists after ActualAddr
    filled = 0
    empty = 0
    for m in re.finditer(
        r'ActualAddr" Type="string">([^<]*)</Single>\s*'
        r'<Single Name="AutomaticAddress"[^>]*>.*?</Single>\s*'
        r'<Single Name="IecAddress"[^>]*>.*?</Single>\s*'
        r'<Single Name="Mappings"[^>]*>\s*(<List2 Name="Mappings"[^/]*/>|<List2 Name="Mappings">.*?</List2>)',
        t,
        re.S,
    ):
        blob = m.group(2)
        if "Variable" in blob:
            filled += 1
        else:
            empty += 1
    print("channel maps filled", filled, "empty", empty)
