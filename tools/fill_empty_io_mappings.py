# -*- coding: utf-8 -*-
"""Fill empty IoMapping List2: VisibleName Default, word/dword aggregates, tail Nulls."""
from __future__ import print_function

import argparse
import os
import re
import sys
from collections import Counter

_EMPTY_LIST2_RE = re.compile(r'^([ \t]*)<List2 Name="Mappings"\s*/>', re.MULTILINE)
_DEFAULT_VAR_RE = re.compile(
    r'<Single Name="Default" Type="string">((?:i_|o_)[^<]+)</Single>'
)
_BIT_ADDR_VAR_RE = re.compile(
    r'<Single Name="ActualAddr" Type="string">(%[IQ]X\d+\.\d+)</Single>'
    r".*?"
    r'<Single Name="Variable" Type="string">((?:i_|o_)[^<]+)</Single>',
    re.IGNORECASE | re.DOTALL,
)
_WORD_ADDR_RE = re.compile(
    r'<Single Name="ActualAddr" Type="string">(%[IQ][WD]\d+)</Single>'
)
_VAR_RE = re.compile(
    r'<Single Name="Variable" Type="string">((?:i_|o_)[^<]+)</Single>'
)


def _mapping_block(indent, var, fat_indent=False):
    # A1 third-section Null blocks use deeper child indent.
    inner = "        " if fat_indent else "  "
    pad = "          " if fat_indent else "    "
    return (
        "%s<List2 Name=\"Mappings\">\n"
        "%s%s<Single Type=\"{47edf8ea-3f84-452c-b998-e18f878578d3}\" Method=\"IArchivable\">\n"
        "%s%s<Single Name=\"Variable\" Type=\"string\">%s</Single>\n"
        "%s%s<Single Name=\"Id\" Type=\"long\">-1</Single>\n"
        "%s%s<Single Name=\"CreateVariable\" Type=\"bool\">True</Single>\n"
        "%s%s<Single Name=\"DefaultVariable\" Type=\"string\"></Single>\n"
        "%s%s<Single Name=\"IoChannelFBInstance\" Type=\"string\"></Single>\n"
        "%s%s</Single>\n"
        "%s</List2>"
        % (
            indent,
            indent, inner,
            indent, pad, var,
            indent, pad,
            indent, pad,
            indent, pad,
            indent, pad,
            indent, inner,
            indent,
        )
    )


def _nearest_default(text, pos, lookback=2500):
    chunk = text[max(0, pos - lookback) : pos]
    matches = list(_DEFAULT_VAR_RE.finditer(chunk))
    return matches[-1].group(1).strip() if matches else None


def _ordered_bit_vars(text):
    seen = set()
    ordered = []
    for m in _BIT_ADDR_VAR_RE.finditer(text):
        var = m.group(2).strip()
        if var and var not in seen:
            seen.add(var)
            ordered.append(var)
    return ordered


def fill_empty_mappings(text):
    """Fill empty List2: Default, then %IW/%ID words, then post-word Null tails.

    A1 pattern per bit var: 3 Variable copies
      1) bit ActualAddr  2) nested Null  3) word (%IW/%ID) or later Null tail
    """
    bit_vars = _ordered_bit_vars(text)
    words = list(_WORD_ADDR_RE.finditer(text))
    first_word_pos = words[0].start() if words else None
    last_word_end = words[-1].end() if words else None
    counts = Counter(_VAR_RE.findall(text))

    out = []
    last = 0
    filled = 0
    word_idx = 0
    tail_idx = 0
    remain_tail = [
        v for v in bit_vars[len(words) :] if counts.get(v, 0) < 3
    ]

    for m in _EMPTY_LIST2_RE.finditer(text):
        indent = m.group(1)
        var = _nearest_default(text, m.start())
        fat = False
        if not var:
            look = text[max(0, m.start() - 900) : m.start()]
            am = None
            for cand in _WORD_ADDR_RE.finditer(look):
                am = cand
            if am is not None and word_idx < len(bit_vars):
                var = bit_vars[word_idx]
                word_idx += 1
            elif (
                last_word_end is not None
                and m.start() > last_word_end
                and "<Null Name=\"ActualAddr\"" in look
                and tail_idx < len(remain_tail)
            ):
                var = remain_tail[tail_idx]
                tail_idx += 1
                fat = True
            else:
                continue
        out.append(text[last : m.start()])
        out.append(_mapping_block(indent, var, fat_indent=fat))
        last = m.end()
        filled += 1
    if not filled:
        return text, 0
    out.append(text[last:])
    return "".join(out), filled


def process_file(path, dry_run=False):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    new_text, n = fill_empty_mappings(text)
    if n == 0:
        return 0
    if not dry_run:
        bak = path + ".bak_before_map_fill"
        if not os.path.isfile(bak):
            with open(bak, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
    return n


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("paths", nargs="+")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    files = []
    for path in args.paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if name.endswith(".xml") and ".bak" not in name.lower():
                    files.append(os.path.join(path, name))
        else:
            files.append(path)
    total = 0
    for path in files:
        n = process_file(path, dry_run=args.dry_run)
        print("%s: filled %d" % (path, n) if n else "%s: nothing" % path)
        total += n
    print("Total", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
