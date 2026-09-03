# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import sys

sys.path.insert(0, r"d:\projects\codescribe\src")

# Import only the pure helpers without scriptengine
import importlib.util
spec = importlib.util.spec_from_file_location(
    "ie", r"d:\projects\codescribe\src\import_export.py"
)
# Can't load import_export - pulls scriptengine via util
# Test regex logic inline instead

import re
import io

_VARIABLE_MAP_RE = re.compile(
    r'<Single Name="Variable" Type="string">([^<]*)</Single>',
    re.IGNORECASE,
)
_IOMAPPING_ACTUAL_RE = re.compile(
    r'(<Single Name="IoMapping"[^>]*>.*?<Single Name="ActualAddr" Type="string">)'
    r'([^<]*)'
    r'(</Single>.*?<Single Name="Mappings"[^>]*>\s*)'
    r'(<List2 Name="Mappings"[^>]*/?>.*?</List2>|<List2 Name="Mappings"[^>]*/>)'
    r'(\s*</Single>)',
    re.IGNORECASE | re.DOTALL,
)

def count_io_variable_mappings(xml_text):
    n = 0
    for m in _VARIABLE_MAP_RE.finditer(xml_text or ""):
        if m.group(1).strip():
            n += 1
    return n

def _iomap_mappings_by_addr(xml_text):
    out = {}
    for m in _IOMAPPING_ACTUAL_RE.finditer(xml_text or ""):
        addr = m.group(2).strip()
        list2 = m.group(4)
        if not addr:
            continue
        if "Variable" in list2 or addr not in out:
            out[addr] = list2
    return out

def merge_preserved_io_mappings(new_text, previous_text):
    if not previous_text or count_io_variable_mappings(previous_text) == 0:
        return new_text
    if count_io_variable_mappings(new_text) > 0:
        return new_text
    prev_maps = _iomap_mappings_by_addr(previous_text)
    if not prev_maps:
        return new_text
    def _repl(m):
        addr = m.group(2).strip()
        list2 = prev_maps.get(addr)
        if not list2 or "Variable" not in list2:
            return m.group(0)
        return m.group(1) + m.group(2) + m.group(3) + list2 + m.group(5)
    return _IOMAPPING_ACTUAL_RE.sub(_repl, new_text)

base = os.path.join(
    u"d:/projects",
    u"1952_1953МираторгБелгород",
    u"plc",
    u"1952_1953МираторгБелгород",
    u"Device",
    u"devices",
    u"Right_Expansion_Module",
)
cur = open(os.path.join(base, "A1.xml"), encoding="utf-8").read()
bak = open(os.path.join(base, "A1.xml.bak_before_map"), encoding="utf-8").read()
print("cur vars", count_io_variable_mappings(cur))
print("bak vars", count_io_variable_mappings(bak))
print("prev map addrs", len(_iomap_mappings_by_addr(cur)))
merged = merge_preserved_io_mappings(bak, cur)
print("merged vars", count_io_variable_mappings(merged))
print("merged==bak", merged == bak)
print("sample", re.search(r'Name="Variable" Type="string">([^<]+)', merged).group(1) if count_io_variable_mappings(merged) else None)
