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

def channel_report(fn):
    t = open(os.path.join(base, fn), encoding="utf-8", errors="replace").read()
    print("====", fn)
    # For each ActualAddr show if Variable present in following Mappings (next 800 chars)
    for m in re.finditer(
        r'<Single Name="ActualAddr" Type="string">([^<]*)</Single>', t
    ):
        addr = m.group(1)
        window = t[m.end() : m.end() + 900]
        vars_ = re.findall(
            r'<Single Name="Variable" Type="string">([^<]*)</Single>', window
        )
        # stop at next ActualAddr conceptually - window is enough if Mappings close
        nonempty = [v for v in vars_ if v.strip()]
        # only leaf channels with real addr
        if not addr.strip():
            continue
        if nonempty:
            print("  OK ", addr, "->", nonempty[0])
        else:
            print("  EMPTY", addr)
            # show mapping snippet
            mm = re.search(r'Name="Mappings".{0,200}', window)
            print("       ", (mm.group(0).replace("\n", " ") if mm else window[:120]))

channel_report("A1.xml")
channel_report("A2.xml")
channel_report("A15.xml")

# Also Modbus
mod = os.path.join(os.path.dirname(base), "Modbus_COM")
if os.path.isdir(mod):
    for fn in os.listdir(mod):
        if fn.endswith(".xml"):
            p = os.path.join(mod, fn)
            t = open(p, encoding="utf-8", errors="replace").read()
            vars_ = [
                v
                for v in re.findall(
                    r'Name="Variable" Type="string">([^<]*)</Single>', t
                )
                if v.strip()
            ]
            print("Modbus", fn, "vars", len(vars_), "size", os.path.getsize(p))
