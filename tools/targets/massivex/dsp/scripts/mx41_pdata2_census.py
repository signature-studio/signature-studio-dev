#!/usr/bin/env python3
"""MX-41 (#3792 / MX-38 U4b): 2 本目 .pdata の census 取り込みと 1 本目の読取不能 (UNWIND_INFO) の分類。

- .pdata は 2 本ある。2 本目は raw 6,144 B のみ実データで、VirtualSize (158,952 B) が .xdata の VA 範囲と重なる。
  読取は mx6_pdata_eh.make_rva_reader と同じく raw を持つ section を優先する。
- DATA_DIRECTORY[EXCEPTION] が指すのは 1 本目だけ (2 本目は例外テーブルとして登録されていない)。
- 読取不能の分類 (reader と pefile の両方で行ごとに求め、一致を json に出す):
  out_of_image (UnwindInfoAddress >= SizeOfImage)・no_section (画像内で section の範囲に入らない)・
  zero_fill (VirtualSize の zero 埋め部分)・raw_zero (raw の内側で 4 バイトが 0)。
- 独立再計算: pefile の get_section_by_rva / get_offset_from_rva で同じ分類を求め、読取不能の集合・分類・
  読める行の flags を reader の結果と照合する。
- ネガティブコントロール: 分類 (unreadable_rows) に入力 (st -> (e, ui)) を渡し、入力を書き換えて再分類する。
  読める 1 件の ui を画像外の値に壊す (件数 +1 を期待) / 読取不能 1 件の ui を隣の読める値に直す (件数 -1 を期待)。
  delta は再分類の件数から求める (期待値を式に入れない)。

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

NEG_BROKEN_UI = 0x49500DE8  # ネガティブコントロールで壊す先 (画像外の値)


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


def reader_class(where, soi, ui):
    if ui >= soi:
        return 'out_of_image'
    hits = where(ui)
    if not hits:
        return 'no_section'
    return 'raw_zero' if any(h.endswith(':raw') for h in hits) else 'zero_fill'


def unreadable_rows(rd, ents, where, soi):
    rows = []
    for st, (e, ui) in sorted(ents.items()):
        if read_ui(rd, ui) is None:
            rows.append({'st': st, 'e': e, 'ui': ui, 'class': reader_class(where, soi, ui)})
    return rows


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

    def pef_cls(ui):
        """pefile の section 解決で分類を返す。読めた場合は (readable or raw_zero, 4 バイト)。"""
        if ui >= soi:
            return 'out_of_image', None
        s = pe.get_section_by_rva(ui)
        if s is None:
            return 'no_section', None
        off_in = ui - s.VirtualAddress
        if off_in >= s.SizeOfRawData:
            return 'zero_fill', None
        off = pe.get_offset_from_rva(ui)
        b = data[off:off + min(4, s.SizeOfRawData - off_in)].ljust(4, b'\0')
        return ('raw_zero' if b == b'\0\0\0\0' else 'readable'), b

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
    for r in unreadable_rows(rd, ents1, where, soi):
        st, ui = r['st'], r['ui']
        hits = where(ui)
        try:
            code = data[pe.get_offset_from_rva(st)]
        except Exception:
            code = None
        unr.append({'st': st, 'e': r['e'], 'ui': ui, 'class': r['class'], 'sec': ','.join(hits) or '-',
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

    # 独立再計算 (pefile): 読取不能の集合・行ごとの分類・読める行の flags を reader と照合する
    rd_cls = {r['st']: r['class'] for r in unr}
    pef = {st: pef_cls(ui) for st, (e, ui) in ents1.items()}
    pef_unr = {st: c for st, (c, b) in pef.items() if c != 'readable'}
    flag_diff = []
    for st, (e, ui) in ents1.items():
        if st in rd_cls:
            continue
        c, b = pef[st]
        a = read_ui(rd, ui)[0]
        if c != 'readable' or (a & (CHAIN | EHANDLER | UHANDLER)) != ((b[0] >> 3) & (CHAIN | EHANDLER | UHANDLER)):
            flag_diff.append((st, ui))
    res['independent_pefile'] = {
        'unreadable_pefile': len(pef_unr),
        'unreadable_same_set': set(pef_unr) == set(rd_cls),
        'unreadable_only_pefile': len(set(pef_unr) - set(rd_cls)),
        'unreadable_only_reader': len(set(rd_cls) - set(pef_unr)),
        'class_pefile': dict(collections.Counter(pef_unr.values())),
        'class_rows_match': sum(1 for st in rd_cls if pef_unr.get(st) == rd_cls[st]),
        'flag_mismatch_readable': len(flag_diff),
        'flag_mismatch_in_pdata2_vs_range': sum(
            1 for st, ui in flag_diff if p2.VirtualAddress <= ui < p2.VirtualAddress + p2.Misc_VirtualSize),
    }

    # ネガティブコントロール: 入力を書き換えて再分類し、件数の変化を測る
    base = len(unr)
    victim = next(st for st, (e, ui) in sorted(ents1.items())
                  if st not in rd_cls and not (read_ui(rd, ui)[0] & (CHAIN | EHANDLER | UHANDLER)))
    ents_b = dict(ents1)
    ents_b[victim] = (ents1[victim][0], NEG_BROKEN_UI)
    rows_b = unreadable_rows(rd, ents_b, where, soi)
    bad = unr[0]
    fixed_ui = [ui for st, (e, ui) in sorted(ents1.items()) if st < bad['st'] and read_ui(rd, ui) is not None][-1]
    ents_f = dict(ents1)
    ents_f[bad['st']] = (bad['e'], fixed_ui)
    rows_f = unreadable_rows(rd, ents_f, where, soi)
    res['negctl'] = {
        'base_unreadable': base,
        'break': {'st': '%08x' % victim, 'ui_before': '%08x' % ents1[victim][1],
                  'ui_after': '%08x' % NEG_BROKEN_UI, 'pefile_class_after': pef_cls(NEG_BROKEN_UI)[0],
                  'row_class_after': next((r['class'] for r in rows_b if r['st'] == victim), None),
                  'unreadable_after': len(rows_b), 'delta': len(rows_b) - base},
        'fix': {'st': '%08x' % bad['st'], 'ui_before': '%08x' % bad['ui'], 'ui_after': '%08x' % fixed_ui,
                'pefile_class_after': pef_cls(fixed_ui)[0],
                'row_removed': all(r['st'] != bad['st'] for r in rows_f),
                'unreadable_after': len(rows_f), 'delta': len(rows_f) - base},
    }
    with open(os.path.join(out_dir, 'mx41_pdata2.json'), 'w') as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
