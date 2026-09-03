# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import re
import sys

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

if not found:
    print("A1.xml not found")
    sys.exit(1)

bak = found + ".bak_before_map"
print("cur", found, os.path.getsize(found))
print("bak exists", os.path.isfile(bak), os.path.getsize(bak) if os.path.isfile(bak) else 0)

for label, path in (("cur", found), ("bak", bak if os.path.isfile(bak) else None)):
    if not path:
        continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    print("====", label, "chars", len(text))
    print("HostObjectGuid", text.count("HostObjectGuid"))
    print("Name=Variable", len(re.findall(r'Name="Variable"', text)))
    hosts = re.findall(
        r'<Single Name="HostObjectGuid" Type="System\.Guid">([^<]*)</Single>', text
    )
    print("unique hosts", len(set(hosts)))
    for h in sorted(set(hosts))[:5]:
        print("  host", h)
    # Variable value samples
    vals = re.findall(
        r'<Single Name="Variable"[^>]*>([^<]*)</Single>', text
    )
    nonempty = [v for v in vals if v.strip()]
    print("Variable nonempty", len(nonempty), "of", len(vals))
    for v in nonempty[:20]:
        print("  var", v[:120])
    # also look for MappingInfo / IoMap style
    for key in (
        "MappingInfo",
        "IoMapping",
        "VariableMapping",
        "ChannelMapping",
        "ExplicitConnector",
        "SymbolicAccess",
        "ApplicationGuid",
        "DeviceGuid",
    ):
        print(key, text.count(key))

# diff sizes and whether rewrite already applied
if os.path.isfile(bak):
    with open(found, "r", encoding="utf-8", errors="replace") as f:
        cur = f.read()
    with open(bak, "r", encoding="utf-8", errors="replace") as f:
        old = f.read()
    print("cur==bak", cur == old)
    # first ParentGuid / HostObjectGuid
    for tag in ("ParentGuid", "HostObjectGuid"):
        c = re.search(
            r'<Single Name="%s" Type="System\.Guid">([^<]*)</Single>' % tag, cur
        )
        o = re.search(
            r'<Single Name="%s" Type="System\.Guid">([^<]*)</Single>' % tag, old
        )
        print(tag, "cur", c.group(1) if c else None, "bak", o.group(1) if o else None)
