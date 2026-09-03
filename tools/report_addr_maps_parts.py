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


def report(fn):
    t = open(os.path.join(base, fn), encoding="utf-8").read()
    print("====", fn, "len", len(t))
    # all ActualAddr with following List2 summary
    for m in re.finditer(
        r'<Single Name="ActualAddr" Type="string">([^<]*)</Single>\s*'
        r'<Single Name="AutomaticAddress"[^>]*>.*?</Single>\s*'
        r'<Single Name="IecAddress"[^>]*>.*?</Single>\s*'
        r'<Single Name="Mappings"[^>]*>\s*'
        r'(<List2 Name="Mappings">.*?</List2>|<List2 Name="Mappings"\s*/>)',
        t,
        re.S,
    ):
        addr = m.group(1)
        list2 = m.group(2)
        var = re.search(r'Name="Variable" Type="string">([^<]*)</Single>', list2)
        pos = m.start()
        # which third of file
        third = 1 if pos < len(t) // 3 else (2 if pos < 2 * len(t) // 3 else 3)
        v = var.group(1) if var else "(empty)"
        print("  part%s  %6s  pos=%7d  -> %s" % (third, addr, pos, v))


report("A1.xml")
report("A2.xml")
