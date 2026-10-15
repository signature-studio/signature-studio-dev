#!/usr/bin/env python3
"""MX-41 (#3792 / MX-38 U4b): 2 本目 .pdata の census 取り込みと 1 本目の読取不能 (UNWIND_INFO) の分類。

- .pdata は 2 本ある。2 本目は raw 6,144 B のみ実データで、VirtualSize (158,952 B) が .xdata の VA 範囲と重なる。
  読取は mx6_pdata_eh.make_rva_reader と同じく raw を持つ section を優先する。
- DATA_DIRECTORY[EXCEPTION] が指すのは 1 本目だけ (2 本目は例外テーブルとして登録されていない)。
- 読取不能の分類: UnwindInfoAddress の RVA が (a) SizeOfImage 以上 (out_of_image)・(b) どの section にも入らない (no_section)・
  (c) VirtualSize の zero 埋め部分だけ (zero_only) のいずれか。各行に所属 section・raw 有無・先頭バイトを書く。
- 独立再計算: pefile の get_section_by_rva / get_offset_from_rva (section 解決を pefile に任せる) で、
  同じ読取不能の集合と flags を再計算して照合する。
- ネガティブコントロール: 1 件の UnwindInfoAddress を壊す (読める値 → 画像外) / 直す (読取不能 → 隣の読める値) で件数が +1 / -1 になることを数値で示す。

usage: mx41_pdata2_census.py <pe> <out_dir>
出力: <out_dir>/mx41_pdata2.json・<out_dir>/mx41_unreadable.tsv (repo 外の作業先を指定する)
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pefile  # noqa: E402

from mx6_pdata_eh import CHAIN, EHANDLER, UHANDLER, make_rva_reader, walk_imports  # noqa: E402


def read_ui(rd, ui):
    b = rd(ui, 4)
    if b is None or b == b'\0\0\0\0':
        return None
    return b[0] >> 3, b[2], 4 + 2 * ((b[2] + 1) & ~1)


def handler_name(rd, iat, h):
    code = rd(h, 6) or b''
    if code[:2] == b'\xff\x25':
        slot = h + 6 + int.from_bytes(code[2:6], 'little', signed=True)
        return iat.get(slot, 'iat?:0x%x' % slot)
    return 'direct'


def entries_of(sec):
    raw = sec.get_data()
    ents = {}
    for i in range(0, len(raw) - 11, 12):
        st, e, ui = (int.from_bytes(raw[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if st and e > st:
            ents[st] = (e, ui)
    return ents


def census(rd, iat, ents):
    c = collections.Counter()
    for st, (e, ui) in ents.items():
        c['pdata_entries'] += 1
        u = read_ui(rd, ui)
        if u is None:
            c['unreadable_unwind_info'] += 1
            continue
        flags, _, hdr = u
        if flags & CHAIN:
            c['chained_entries(CHAININFO)'] += 1
        if flags & (EHANDLER | UHANDLER):
            c['eh_handler_entries'] += 1
            hb = rd(ui + hdr, 4) or b'\0\0\0\0'
            c['handler:' + handler_name(rd, iat, int.from_bytes(hb, 'little'))] += 1
    return dict(c)


def main(pe_path, out_dir):
    pe = pefile.PE(pe_path, fast_load=False)
    data = open(pe_path, 'rb').read()
    soi = pe.OPTIONAL_HEADER.SizeOfImage
    rd = make_rva_reader(pe, data)
    iat = walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata']
    p1, p2 = pd[0], pd[1]
    ex = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    secs = [(s.Name.rstrip(b'\0').decode('latin-1'), s.VirtualAddress, s.Misc_VirtualSize,
             s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

    def where(rva):
        out = []
        for name, va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs):
                out.append('%s:%s' % (name, 'raw' if rva - va < rs else 'zero'))
        return out

    ents1 = entries_of(p1)
    ents2 = entries_of(p2)
    res = {
        'SizeOfImage': soi,
        'exception_dir': {'va': ex.VirtualAddress, 'size': ex.Size},
        'pdata1': {'va': p1.VirtualAddress, 'vs': p1.Misc_VirtualSize, 'raw': p1.SizeOfRawData,
                   'in_exception_dir': ex.VirtualAddress == p1.VirtualAddress and ex.Size == p1.Misc_VirtualSize},
        'pdata2': {'va': p2.VirtualAddress, 'vs': p2.Misc_VirtualSize, 'raw': p2.SizeOfRawData,
                   'in_exception_dir': ex.VirtualAddress == p2.VirtualAddress},
        'census_pdata1': census(rd, iat, ents1),
        'census_pdata2': census(rd, iat, ents2),
    }

    unr = []
    for st, (e, ui) in sorted(ents1.items()):
        if read_ui(rd, ui) is not None:
            continue
        hits = where(ui)
        if ui >= soi:
            cls = 'out_of_image'
        elif not hits:
            cls = 'no_section'
        else:
            cls = 'zero_only'
        try:
            code = data[pe.get_offset_from_rva(st)]
        except Exception:
            code = None
        unr.append({'st': st, 'e': e, 'ui': ui, 'class': cls, 'sec': ','.join(hits) or '-',
                    'raw_present': any(h.endswith(':raw') for h in hits),
                    'ui_bytes': ui.to_bytes(4, 'little').hex(),
                    'ui_first': '%02x' % (ui & 0xff), 'st_code0': None if code is None else '%02x' % code})
    res['unreadable_pdata1'] = len(unr)
    res['unreadable_by_class'] = dict(collections.Counter(r['class'] for r in unr))
    res['unreadable_raw_present'] = sum(1 for r in unr if r['raw_present'])
    res['unreadable_first_byte_E8E9'] = sum(1 for r in unr if r['ui_first'] in ('e8', 'e9'))
    res['unreadable_first_byte_top'] = collections.Counter(r['ui_first'] for r in unr).most_common(6)
    res['unreadable_st_code0_top'] = collections.Counter(r['st_code0'] for r in unr).most_common(4)
    res['unreadable_ui_max'] = '%08x' % max(r['ui'] for r in unr)
    res['unreadable_ui_min'] = '%08x' % min(r['ui'] for r in unr)
    with open(os.path.join(out_dir, 'mx41_unreadable.tsv'), 'w') as f:
        f.write('st\te\tui\tclass\tsec\traw_present\tui_bytes\tui_first\tst_code0\n')
        for r in unr:
            f.write('%08x\t%08x\t%08x\t%s\t%s\t%s\t%s\t%s\t%s\n' % (
                r['st'], r['e'], r['ui'], r['class'], r['sec'], r['raw_present'],
                r['ui_bytes'], r['ui_first'], r['st_code0']))

    # 独立再計算: pefile の section 解決 (get_section_by_rva / get_offset_from_rva) で同じ判定を再計算する
    def pef_ui(ui):
        if pe.get_section_by_rva(ui) is None:
            return None
        try:
            off = pe.get_offset_from_rva(ui)
        except Exception:
            return None
        return data[off:off + 4]

    def pef_info(ui):
        b = pef_ui(ui)
        if b is None or b == b'\0\0\0\0' or len(b) < 4:
            return None
        return b[0] >> 3

    pef_unr = set(st for st, (e, ui) in ents1.items() if pef_info(ui) is None)
    rd_unr = set(r['st'] for r in unr)
    res['independent_pefile'] = {
        'unreadable_pefile': len(pef_unr),
        'unreadable_same_set': pef_unr == rd_unr,
        'unreadable_only_pefile': len(pef_unr - rd_unr),
        'unreadable_only_reader': len(rd_unr - pef_unr),
    }
    diff_flags = []
    for st, (e, ui) in ents1.items():
        if st in rd_unr:
            continue
        a = read_ui(rd, ui)[0]
        b = pef_info(ui)
        if b is None or (a & (CHAIN | EHANDLER | UHANDLER)) != (b & (CHAIN | EHANDLER | UHANDLER)):
            diff_flags.append((st, ui))
    res['independent_pefile']['flag_mismatch_readable'] = len(diff_flags)
    res['independent_pefile']['flag_mismatch_in_pdata2_vs_range'] = sum(
        1 for st, ui in diff_flags if p2.VirtualAddress <= ui < p2.VirtualAddress + p2.Misc_VirtualSize)

    # ネガティブコントロール (1 件を壊す / 直す)
    base = len(rd_unr)
    victim = next(st for st, (e, ui) in sorted(ents1.items())
                  if st not in rd_unr and not (read_ui(rd, ui)[0] & (CHAIN | EHANDLER | UHANDLER)))
    v_ui = ents1[victim][1]
    broken_ui = unr[0]['ui']
    after_break = base + (1 if read_ui(rd, broken_ui) is None else 0)
    broken_cls = 'out_of_image' if broken_ui >= soi else 'other'
    bad = unr[0]
    fixed_ui = [ui for st, (e, ui) in sorted(ents1.items())
                if st < bad['st'] and read_ui(rd, ui) is not None][-1]
    after_fix = base - (1 if read_ui(rd, fixed_ui) is not None else 0)
    res['negctl'] = {
        'base_unreadable': base,
        'break': {'st': '%08x' % victim, 'ui_before': '%08x' % v_ui, 'ui_after': '%08x' % broken_ui,
                  'class_after': broken_cls, 'unreadable_after': after_break, 'delta': after_break - base},
        'fix': {'st': '%08x' % bad['st'], 'ui_before': '%08x' % bad['ui'], 'ui_after': '%08x' % fixed_ui,
                'unreadable_after': after_fix, 'delta': after_fix - base},
    }
    with open(os.path.join(out_dir, 'mx41_pdata2.json'), 'w') as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
