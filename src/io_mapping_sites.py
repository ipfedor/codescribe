# -*- coding: utf-8 -*-
"""
I/O Mapping site policy for Xinje/CODESYS module native XML (A1-style).

Status: STUB ONLY — classify + policy tables; fill/strip not implemented yet.

---------------------------------------------------------------------------
Per process bit (i_*/o_*) a complete A1 export has up to 3 Variable rows.
Only some of them are needed for application I/O.

REQUIRED (keep / fill on import-export)
  bit          ActualAddr %IXn.m / %QXn.m on InputChN — real channel binding
  null_dup     Null ActualAddr under the same bit BaseType — nested duplicate
               CODESYS keeps this next to the bit; empty here breaks parity

UNNECESSARY (do not invent; strip later when implemented)
  aggregate_word   %IWn on TBitStringBytein parent mapped to a BOOL name
                   (A1: %IW0 -> i_autostop). Wrong type for CreateVariable.
  errcode_word     ErrCode_module %IWn -> borrowed BOOL name (A1: i_rkn)
  errcode_dword    ErrCode_CH %IDn -> borrowed BOOL name (A1: i_plkpmu)
  null_tail        Null ActualAddr AFTER errcode block, no VisibleName —
                   remaining bit names only (A1: i_zumer .. i_kc14_km).
                   Connector/shadow copies; not addressable I/O.

Current fill_empty_io_mappings_from_visible_names() still fills word +
tail for A1 file-parity experiments. Replace with fill_required_sites()
when this stub is implemented.

Ad-hoc probe scripts (not production; do not call from import path):
  tools/_inspect_iomap.py
  tools/_inspect_mappings.py
  tools/_cmp_a1_a2_maps.py
  tools/_check_a2_kc15.py
  tools/_a2_list2_near_kc15.py
  tools/_verify_a2_null.py
  tools/verify_a2_null.py
  tools/_dump_map_nesting.py
  tools/_list_var_counts.py
  tools/_channel_empty_report.py
  tools/_compare_map_sources.py
  tools/_test_merge_maps.py
  tools/_guid_format.py
  tools/_1855_vars_per_entry.py
  tools/report_word_maps.py
  tools/report_addr_maps_parts.py
"""
from __future__ import print_function

import re

try:
    unicode  # noqa: py2
except NameError:  # pragma: no cover — py3
    unicode = str

# Policy
SITE_REQUIRED = (u"bit", u"null_dup")
SITE_UNNECESSARY = (
    u"aggregate_word",
    u"errcode_word",
    u"errcode_dword",
    u"null_tail",
)

_IOMAPPING_RE = re.compile(
    ur'<Single Name="IoMapping" Type="\{d6d934cf-5ec0-42c3-b628-2a7aea7d364c\}"[^>]*>'
)
_ACTUAL_ADDR_RE = re.compile(
    ur"<(?:Single|Null) Name=\"ActualAddr\"[^/]*?(?:/>|>[^<]*</Single>)"
)
_VAR_RE = re.compile(ur'<Single Name="Variable" Type="string">([^<]*)</Single>')
_EMPTY_LIST2_RE = re.compile(ur'<List2 Name="Mappings"\s*/>')
_BIT_ADDR_RE = re.compile(ur"%[IQ]X\d+\.\d+", re.IGNORECASE)
_WORD_ADDR_RE = re.compile(ur"%[IQ]W\d+", re.IGNORECASE)
_DWORD_ADDR_RE = re.compile(ur"%[IQ]D\d+", re.IGNORECASE)


class MappingSite(object):
    __slots__ = (u"kind", u"var", u"addr_xml", u"pos", u"channel_hint")

    def __init__(self, kind, var, addr_xml, pos, channel_hint=u""):
        self.kind = kind
        self.var = var
        self.addr_xml = addr_xml
        self.pos = pos
        self.channel_hint = channel_hint or u""

    @property
    def required(self):
        return self.kind in SITE_REQUIRED

    def as_tuple(self):
        return (self.kind, self.var, self.pos, self.channel_hint)


def _channel_hint(prev):
    """Best-effort Identifier|Default from preceding VisibleName."""
    vn = list(
        re.finditer(
            ur'Name="VisibleName".{0,200}?'
            ur'<Single Name="Identifier" Type="string">([^<]+)</Single>.{0,80}?'
            ur'<Single Name="Default" Type="string">([^<]*)</Single>',
            prev,
            re.DOTALL,
        )
    )
    if vn:
        return vn[-1].group(1) + u"|" + vn[-1].group(2)
    ids = list(
        re.finditer(ur'<Single Name="Identifier" Type="string">([^<]+)</Single>', prev)
    )
    return ids[-1].group(1) if ids else u""


def _classify_addr(addr_xml, channel_hint, prev_tail, pos, first_word_pos):
    if u"Null" in addr_xml:
        if first_word_pos is not None and pos >= first_word_pos:
            return u"null_tail"
        return u"null_dup"
    if _BIT_ADDR_RE.search(addr_xml):
        return u"bit"
    if _WORD_ADDR_RE.search(addr_xml):
        blob = (channel_hint or u"") + u" " + (prev_tail or u"")
        if u"ErrCode" in blob:
            return u"errcode_word"
        return u"aggregate_word"
    if _DWORD_ADDR_RE.search(addr_xml):
        blob = (channel_hint or u"") + u" " + (prev_tail or u"")
        if u"ErrCode" in blob:
            return u"errcode_dword"
        return u"aggregate_dword"
    return u"other"


def classify_mapping_sites(xml_text):
    """
    Return list of MappingSite for every non-empty Variable under IoMapping.

    Does not modify XML. Safe to call from tools / tests.
    """
    if not xml_text:
        return []

    # First word/dword ActualAddr marks start of aggregate/errcode/tail region.
    first_word_pos = None
    for m in re.finditer(
        ur'<Single Name="ActualAddr" Type="string">(%[IQ][WD]\d+)</Single>',
        xml_text,
        re.IGNORECASE,
    ):
        first_word_pos = m.start()
        break

    sites = []
    for m in _IOMAPPING_RE.finditer(xml_text):
        block = xml_text[m.start() : m.start() + 1200]
        aa = _ACTUAL_ADDR_RE.search(block)
        if not aa:
            continue
        if _EMPTY_LIST2_RE.search(block[:500]):
            continue
        vm = _VAR_RE.search(block)
        if not vm or not vm.group(1).strip():
            continue
        var = vm.group(1).strip()
        if not (var.startswith(u"i_") or var.startswith(u"o_")):
            continue
        prev = xml_text[max(0, m.start() - 800) : m.start()]
        hint = _channel_hint(prev)
        kind = _classify_addr(
            aa.group(0), hint, prev[-500:], m.start(), first_word_pos
        )
        sites.append(MappingSite(kind, var, aa.group(0), m.start(), hint))
    return sites


def summarize_sites(sites):
    """Return {kind: count} and lists of unnecessary vars."""
    counts = {}
    unnecessary_vars = []
    required_vars = []
    for s in sites:
        counts[s.kind] = counts.get(s.kind, 0) + 1
        if s.required:
            required_vars.append(s.var)
        elif s.kind in SITE_UNNECESSARY:
            unnecessary_vars.append((s.kind, s.var))
    return counts, required_vars, unnecessary_vars


def fill_required_sites(xml_text):
    """STUB: fill only bit + null_dup empty Mappings from VisibleName Default."""
    raise NotImplementedError(
        u"fill_required_sites: stub only — see module docstring policy"
    )


def strip_unnecessary_sites(xml_text):
    """STUB: clear Variable on aggregate/errcode/null_tail (leave empty List2)."""
    raise NotImplementedError(
        u"strip_unnecessary_sites: stub only — see module docstring policy"
    )


def report_xml_path(path):
    """Load XML path and print classification summary (CLI helper)."""
    import io
    import os

    with io.open(path, u"r", encoding=u"utf-8", errors=u"replace") as f:
        text = f.read()
    sites = classify_mapping_sites(text)
    counts, required, unnecessary = summarize_sites(sites)
    print(u"file:", os.path.basename(path))
    print(u"sites:", len(sites))
    for kind in sorted(counts):
        flag = u"REQUIRED" if kind in SITE_REQUIRED else (
            u"DROP" if kind in SITE_UNNECESSARY else u"?"
        )
        print(u"  %-18s %3d  %s" % (kind, counts[kind], flag))
    print(u"unnecessary rows:")
    for kind, var in unnecessary:
        print(u"  [%s] %s" % (kind, var))
    return counts, unnecessary


if __name__ == u"__main__":
    import sys

    if len(sys.argv) < 2:
        print(u"Usage: io_mapping_sites.py <module.xml> [more.xml ...]")
        sys.exit(2)
    for p in sys.argv[1:]:
        report_xml_path(p)
        print(u"")
