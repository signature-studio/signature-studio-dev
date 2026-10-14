#!/usr/bin/env python3
"""MX-6 (#1123) U4 (census): .pdata の UNWIND_INFO を全数走査し、chained entry と EH handler の種類を数える。

- UNW_FLAG_CHAININFO (0x4): UNWIND_INFO 末尾の RUNTIME_FUNCTION が親。親まで辿って chain 深さを測る
- UNW_FLAG_EHANDLER (0x1) / UNW_FLAG_UHANDLER (0x2): handler RVA (UNWIND_INFO 直後 4B) の thunk
  `jmp [rip+X]` から IAT 名 (__CxxFrameHandler3/4, __C_specific_handler 等) を引く
- 対象は (a) PE 全体 (b) VST3 入口面 seeds (pdata 始点 566) と 1-round closure (pdata 始点 604)
- funclet の一覧 (FuncInfo / scope table の解析) は本 census の範囲外 (子 issue)

usage: mx6_pdata_eh.py <pe> <roots_seeds.json> <roots_one.json> <out.json>
"""
import collections
import json
import sys

import pefile

CHAIN, EHANDLER, UHANDLER = 0x4, 0x1, 0x2


def make_rva_reader(pe, data):
    secs = [(s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData) for s in pe.sections]

    def rd(rva, n):
        # 本 PE は .pdata の 2 本目の VirtualSize が .xdata と重なる (raw を持つ方を優先する)
        cands = [(va, rs, raw) for va, vs, raw, rs in secs if va <= rva < va + max(vs, rs)]
        hit = [c for c in cands if rva - c[0] < c[1]] or cands
        if not hit:
            return None
        va, rs, raw = hit[0]
        o = rva - va
        b = data[raw + o:raw + min(o + n, rs)] if o < rs else b''
        return b + b'\0' * (n - len(b))
    return rd


def walk_imports(rd, rva):
    """IMPORT_DESCRIPTOR を手動で辿り {IAT slot RVA: 'dll!name'} を返す。
    pefile の DIRECTORY_ENTRY_IMPORT は本 PE で 30 DLL 目で打ち切られる (REPORT §3) ため使わない。"""
    out = {}
    d = 0
    while True:
        desc = rd(rva + 20 * d, 20)
        oft, _, _, name_rva, ft = (int.from_bytes(desc[i:i + 4], 'little') for i in range(0, 20, 4))
        if not (oft or ft):
            break
        ilt = oft or ft
        dll = (rd(name_rva, 64) or b'?').split(b'\0')[0].decode('latin-1')
        for i in range(0, 1 << 20):
            tb = rd(ilt + 8 * i, 8)
            if tb is None:
                break
            th = int.from_bytes(tb, 'little')
            if th == 0:
                break
            if th & (1 << 63):
                nm = 'ord%d' % (th & 0xFFFF)
            else:
                nm = (rd(th + 2, 96) or b'?').split(b'\0')[0].decode('latin-1')
            out[ft + 8 * i] = '%s!%s' % (dll, nm)
        d += 1
    return out


def main(pe_path, seeds_p, one_p, out_p):
    pe = pefile.PE(pe_path, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(pe_path, 'rb').read()
    rd = make_rva_reader(pe, data)
    iat = walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = pdata.get_data()
    entries = {}
    for i in range(0, len(praw) - 11, 12):
        st, e, ui = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if st and e > st:
            entries[st] = (e, ui)

    def get(rva, n):
        return rd(rva, n)

    def uinfo(ui):
        b = get(ui, 4)
        if b is None or b == b'\0\0\0\0':
            raise ValueError(ui)
        flags = b[0] >> 3
        cnt = b[2]
        hdr = 4 + 2 * ((cnt + 1) & ~1)
        return flags, hdr

    def handler_name(h):
        code = rd(h, 6) or b''
        if code[:2] == b'\xff\x25':
            slot = h + 6 + int.from_bytes(code[2:6], 'little', signed=True)
            return iat.get(slot, 'iat?:0x%x' % slot)
        return 'direct'

    def info(va):
        if va not in entries:
            return None
        e, ui = entries[va]
        try:
            flags, hdr = uinfo(ui)
        except ValueError:
            return {'flags': -1, 'chain_depth': 0, 'handler': None}
        r = {'flags': flags, 'chain_depth': 0, 'handler': None}
        cur = ui
        for _ in range(16):
            try:
                f, h = uinfo(cur)
            except ValueError:
                break
            if not f & CHAIN:
                break
            r['chain_depth'] += 1
            cur = int.from_bytes(get(cur + h + 8, 4) or b'\0\0\0\0', 'little')
        if flags & (EHANDLER | UHANDLER):
            hb = get(ui + hdr, 4)
            if hb is not None:
                r['handler'] = handler_name(int.from_bytes(hb, 'little'))
        return r

    allrows = {va: info(va) for va in entries}
    stats = collections.Counter()
    for va, r in allrows.items():
        stats['pdata_entries'] += 1
        if r['flags'] < 0:
            stats['unreadable_unwind_info'] += 1
            continue
        if r['flags'] & CHAIN:
            stats['chained_entries(CHAININFO)'] += 1
        if r['flags'] & (EHANDLER | UHANDLER):
            stats['eh_handler_entries'] += 1
            stats['handler:' + r['handler']] += 1
    res = {'pe_total': dict(stats)}
    for label, path in (('seeds', seeds_p), ('one_round', one_p)):
        roots = sorted(set(int(x, 16) - base for x in json.load(open(path))['roots']))
        c = collections.Counter()
        for va in roots:
            r = allrows.get(va)
            if r is None:
                c['not_pdata_begin'] += 1
                continue
            if r['flags'] < 0:
                c['unreadable_unwind_info'] += 1
                continue
            c['pdata_begin'] += 1
            if r['flags'] & CHAIN:
                c['chained_child(CHAININFO)'] += 1
            if r['chain_depth']:
                c['chain_depth>=1'] += 1
            if r['flags'] & (EHANDLER | UHANDLER):
                c['eh_handler'] += 1
                c['handler:%s' % r['handler']] += 1
        res[label] = dict(c)
    with open(out_p, 'w') as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:5]))
