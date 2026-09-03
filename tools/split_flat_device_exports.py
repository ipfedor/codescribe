#!/usr/bin/env python3
"""
Split legacy flat codescribe device exports into nested-folder layout.

Input:  Device/devices/Parent.xml
        (recursive native export: parent IsRoot=True + nested IsRoot=False)
Output: Device/devices/Parent/<Child>.xml

Does not require CODESYS. Migrates existing flat exports and demonstrates
nested coverage offline.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Optional, Tuple

ENTRY_START_RE = re.compile(
    r'<Single Type="\{6198ad31-4b98-445c-927f-3258a0e82fe3\}" Method="IArchivable">',
)
ISROOT_RE = re.compile(
    r'<Single Name="IsRoot" Type="bool">(True|False)</Single>',
)
NAME_RE = re.compile(
    r'<Single Name="Name" Type="string">([^<]*)</Single>',
)


def _find_matching_close(text: str, start: int) -> int:
    depth = 0
    i = start
    n = len(text)
    while i < n:
        next_open = text.find("<Single", i)
        next_close = text.find("</Single>", i)
        if next_close < 0:
            raise ValueError("unbalanced Single tags")
        if next_open >= 0 and next_open < next_close:
            depth += 1
            i = next_open + 7
            continue
        depth -= 1
        i = next_close + len("</Single>")
        if depth == 0:
            return i
    raise ValueError("unbalanced Single tags")


def extract_entries(xml_text: str) -> List[Tuple[bool, str, str]]:
    """Return [(is_root, device_name, entry_xml), ...]."""
    results = []
    for m in ENTRY_START_RE.finditer(xml_text):
        start = m.start()
        end = _find_matching_close(xml_text, start)
        entry = xml_text[start:end]
        root_m = ISROOT_RE.search(entry)
        if root_m is None:
            continue
        is_root = root_m.group(1) == "True"
        nm = NAME_RE.search(entry)
        name = nm.group(1) if nm else "unnamed"
        results.append((is_root, name, entry))
    return results


def wrap_export(entry_xml: str, force_root: bool = True) -> str:
    """Wrap one EntryList item; optionally force IsRoot=True for child re-import."""
    if force_root:
        entry_xml = ISROOT_RE.sub(
            '<Single Name="IsRoot" Type="bool">True</Single>',
            entry_xml,
            count=1,
        )
    return (
        "<ExportFile>\n"
        '  <StructuredView Guid="{d9b2b2cc-ea99-4c3b-aa42-1e5c49e65b84}">\n'
        '<Single xml:space="preserve" Type="{3daac5e4-660e-42e4-9cea-3711b98bfb63}" '
        'Method="IArchivable">\n'
        '  <Null Name="Profile" />\n'
        '  <List2 Name="EntryList">\n'
        f"{entry_xml}\n"
        "  </List2>\n"
        '  <Null Name="ProfileName" />\n'
        "</Single>  </StructuredView>\n"
        "</ExportFile>\n"
    )


def split_file(src_xml: str, out_dir: str) -> List[str]:
    with open(src_xml, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    entries = extract_entries(text)
    nested = [(n, e) for is_root, n, e in entries if not is_root]
    if not nested:
        return []

    os.makedirs(out_dir, exist_ok=True)
    written = []
    used_names = {}
    for name, entry in nested:
        safe = name if name else "unnamed"
        count = used_names.get(safe, 0)
        used_names[safe] = count + 1
        if count:
            safe = "%s_%d" % (safe, count + 1)
        out_path = os.path.join(out_dir, safe + ".xml")
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(wrap_export(entry, force_root=True))
        written.append(out_path)
    return written


def summarize(src_xml: str) -> Tuple[List[str], List[str]]:
    with open(src_xml, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    entries = extract_entries(text)
    roots = [n for is_root, n, _ in entries if is_root]
    nested = [n for is_root, n, _ in entries if not is_root]
    return roots, nested


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("src_xml", help="Flat devices/<Parent>.xml path")
    p.add_argument(
        "--out-dir",
        help="Output folder (default: <parent_dir>/<basename>/)",
    )
    p.add_argument(
        "--list-only",
        action="store_true",
        help="Only print root/nested names",
    )
    args = p.parse_args(argv)

    roots, nested = summarize(args.src_xml)
    size = os.path.getsize(args.src_xml)
    print("Source: %s (%d bytes)" % (args.src_xml, size))
    print("Roots (%d): %s" % (len(roots), ", ".join(roots) if roots else "(none)"))
    print(
        "Nested (%d): %s"
        % (len(nested), ", ".join(nested) if nested else "(none)")
    )

    if args.list_only:
        return 0 if nested else 1

    if not nested:
        print("No nested devices to split.")
        return 1

    out_dir = args.out_dir
    if not out_dir:
        base = os.path.splitext(os.path.basename(args.src_xml))[0]
        out_dir = os.path.join(os.path.dirname(args.src_xml), base)

    written = split_file(args.src_xml, out_dir)
    print("Wrote %d files under %s" % (len(written), out_dir))
    for path in written:
        print("  %s (%d bytes)" % (os.path.basename(path), os.path.getsize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
