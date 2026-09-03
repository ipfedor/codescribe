# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re

a1 = os.path.join(
    u"d:/projects",
    u"1952_1953МираторгБелгород",
    u"plc",
    u"1952_1953МираторгБелгород",
    u"Device",
    u"devices",
    u"Right_Expansion_Module",
    u"A1.xml",
)
bak = a1 + u".bak_before_map"
ref = r"d:\projects\1855zakaz\plc\plc_main\1855_PLC_Main\Device\devices\Right_Expansion_Module.xml"

for label, p in (("a1", a1), ("bak", bak), ("1855", ref)):
    t = open(p, "r", encoding="utf-8", errors="replace").read()
    print("====", label)
    print("HostObjectGuid", set(re.findall(r'HostObjectGuid" Type="System.Guid">([^<]+)', t)))
    # MetaObject Guid of IsRoot True entries
    roots = re.findall(
        r'IsRoot" Type="bool">True</Single>\s*<Single Name="MetaObject"[^>]*>\s*'
        r'<Single Name="Guid" Type="System.Guid">([^<]+)</Single>\s*'
        r'<Single Name="ParentGuid"[^>]*>([^<]+)</Single>\s*'
        r'<Single Name="Name" Type="string">([^<]*)</Single>',
        t,
        re.S,
    )
    print("IsRoot True count", len(roots))
    for g, pg, n in roots[:6]:
        print("  root", n, "guid", g, "parent", pg)
    vars_ = re.findall(r'Name="Variable" Type="string">([^<]*)</Single>', t)
    nonempty = [v for v in vars_ if v.strip()]
    print("vars", len(nonempty), "/", len(vars_))
    # Does bak store names in Description?
    if label == "bak":
        descs = re.findall(r'Name="Description" Type="string">([^<]*)</Single>', t)
        interesting = [d for d in descs if d.strip() and ("i_" in d or "o_" in d)]
        print("desc with i_/o_", len(interesting), interesting[:10])
        visible = re.findall(r'Name="VisibleName" Type="string">([^<]*)</Single>', t)
        print("visible sample", visible[:15])
