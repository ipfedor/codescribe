# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

p = r"d:\projects\1855zakaz\plc\plc_main\1855_PLC_Main\Device\devices\Right_Expansion_Module.xml"
t = open(p, "r", encoding="utf-8", errors="replace").read()

# Find each IsRoot entry and count Variables inside that entry block
ENTRY_START = re.compile(
    r'<Single Type="\{6198ad31-4b98-445c-927f-3258a0e82fe3\}" Method="IArchivable">'
)

def find_close(text, start):
    depth = 0
    i = start
    n = len(text)
    while i < n:
        o = text.find("<Single", i)
        c = text.find("</Single>", i)
        if c < 0:
            return n
        if o >= 0 and o < c:
            depth += 1
            i = o + 7
            continue
        depth -= 1
        i = c + len("</Single>")
        if depth == 0:
            return i
    return n

for m in ENTRY_START.finditer(t):
    start = m.start()
    # only top-level EntryList items: check IsRoot near start
    head = t[start : start + 500]
    if "IsRoot" not in head:
        continue
    end = find_close(t, start)
    block = t[start:end]
    ir = re.search(r'IsRoot" Type="bool">(True|False)', block)
    if not ir:
        continue
    nm = re.search(r'Name="Name" Type="string">([^<]*)</Single>', block)
    name = nm.group(1) if nm else "?"
    vars_ = re.findall(r'Name="Variable" Type="string">([^<]*)</Single>', block)
    nonempty = [v for v in vars_ if v.strip()]
    print(ir.group(1), name, "vars", len(nonempty), "sample", nonempty[:5])
