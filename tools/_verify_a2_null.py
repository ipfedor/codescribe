# -*- coding: utf-8 -*-
import os
import re

base = None
for n in os.listdir(r"d:\projects"):
    if n.startswith("1952"):
        base = os.path.join(
            r"d:\projects", n, "plc", n, "Device", "devices", "Right_Expansion_Module"
        )
        break
t = open(os.path.join(base, "A2.xml"), encoding="utf-8").read()
m = re.search(
    r'<Null Name="ActualAddr" />\s*'
    r'<Single Name="AutomaticAddress"[^>]*>.*?</Single>\s*'
    r'<Single Name="IecAddress"[^>]*>.*?</Single>\s*'
    r'<Single Name="Mappings"[^>]*>\s*'
    r'(<List2 Name="Mappings">.*?</List2>|<List2 Name="Mappings"\s*/>)',
    t,
    re.S,
)
blob = re.sub(r"\s+", " ", m.group(1)) if m else "NO MATCH"
print("first Null ActualAddr List2:", blob[:250])
print("vars", len(re.findall(r'Name="Variable" Type="string">([^<]+)</Single>', t)))
print("empty self-close", len(re.findall(r'<List2 Name="Mappings"\s*/>', t)))
