#!/usr/bin/env python3
"""MX-57 (#4928): FH3 try 関数の RVA と ShxSehScope 表 (C 側 shimx_fh3_scopes / shimx_fh3_unwind_scopes と同じ規則) を出す。

入力: PE。出力 JSON: FH3 親関数ごとに {begin, fi, try_scopes, unwind_scopes, funclets}。
- try_scopes: try map + IP-to-state map。pType==0 は catch-all (kind 2)、それ以外は pType の RVA を kind にする。
- unwind_scopes: unwind map の action を持つ state を内側から順に kind 0 にする (seh_run_pads の表順)。
- try 関数 = try_scopes が 1 件以上ある親。
上限・棄却 (maxState 0x1000 / nTry 0x1000 / nIP 0x1000 / nCatch 0x100) と IP 昇順違反の棄却は C 側と同じ。
usage: mx57_fh3_scopes.py <pe> <out.json>
"""
import json
import os
import sys

import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mx6_pdata_eh as P  # noqa: E402
from mx39_funclet_reach import FH3, fh3_funclets_capped  # noqa: E402

CAP_STATE, CAP_TRY, CAP_CATCH = 0x1000, 0x1000, 0x100
MAGIC = (0x19930520, 0x19930521, 0x19930522)


def fuinfo_parts(rd, fi):
    b = rd(fi, 36)
    if b is None or int.from_bytes(b[:4], 'little') not in MAGIC:
        return None
    w = [int.from_bytes(b[4 * i:4 * i + 4], 'little') for i in range(9)]
    return {'max_state': w[1], 'disp_unwind': w[2], 'n_try': w[3], 'disp_try': w[4],
            'n_ip': w[5], 'disp_ip': w[6]}


def ip_map(rd, f):
    out = []
    for i in range(f['n_ip']):
        e = rd(f['disp_ip'] + 8 * i, 8) or b'\0' * 8
        out.append((int.from_bytes(e[:4], 'little'), int.from_bytes(e[4:8], 'little', signed=True)))
    return out


def scopes_of(rd, fi, func_end):
    """(try_scopes, unwind_scopes) を返す。try 表が棄却なら (None, None)。unwind 表だけが棄却なら (tries, None)。
    上限判定は C 側と揃える: try 表は shimx_fh3_scopes (n_try / n_ip / n_catch)、unwind 表は shimx_fh3_unwind_scopes (max_state / n_ip)。"""
    f = fuinfo_parts(rd, fi)
    if f is None or f['n_try'] > CAP_TRY or f['n_ip'] > CAP_STATE:
        return None, None
    ips = ip_map(rd, f)
    if any(ips[i][0] < ips[i - 1][0] for i in range(1, len(ips))):
        return None, None
    ranges = []
    for i, (begin, state) in enumerate(ips):
        end = ips[i + 1][0] if i + 1 < len(ips) else func_end
        if end > begin:
            ranges.append((begin, end, state))

    tries = []
    for t in range(f['n_try']):
        tb = rd(f['disp_try'] + 20 * t, 20) or b'\0' * 20
        low = int.from_bytes(tb[0:4], 'little', signed=True)
        high = int.from_bytes(tb[4:8], 'little', signed=True)
        n_catch = int.from_bytes(tb[12:16], 'little')
        if n_catch > CAP_CATCH:
            return None, None
        disp_ha = int.from_bytes(tb[16:20], 'little')
        hs = []
        for h in range(n_catch):
            hb = rd(disp_ha + 16 * h, 16) or b'\0' * 16
            ptype = int.from_bytes(hb[4:8], 'little')
            hs.append({'kind': ptype if ptype else 2, 'target': int.from_bytes(hb[12:16], 'little')})
        for begin, end, state in ranges:
            if low <= state <= high:
                tries.extend({'begin': begin, 'end': end, **h} for h in hs)

    unwind = None
    if f['max_state'] <= CAP_STATE:
        unwind = []
        for begin, end, state in ranges:
            cur = state
            while 0 <= cur < f['max_state']:
                e = rd(f['disp_unwind'] + 8 * cur, 8) or b'\0' * 8
                prev = int.from_bytes(e[:4], 'little', signed=True)
                act = int.from_bytes(e[4:8], 'little')
                if act:
                    unwind.append({'begin': begin, 'end': end, 'kind': 0, 'target': act})
                if prev >= cur:
                    break
                cur = prev
    return tries, unwind


def main(pe_path, out_p):
    pe = pefile.PE(pe_path, fast_load=False)
    data = open(pe_path, 'rb').read()
    rd = P.make_rva_reader(pe, data)
    iat = P.walk_imports(rd, pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].VirtualAddress)
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    praw = pdata.get_data()
    entries = {}
    for i in range(0, len(praw) - 11, 12):
        st, e, ui = (int.from_bytes(praw[i + j:i + j + 4], 'little') for j in (0, 4, 8))
        if st and e > st:
            entries[st] = (e, ui)

    def handler_is_fh3(h):
        code = rd(h, 6) or b''
        if code[:2] == b'\xff\x25':
            return iat.get(h + 6 + int.from_bytes(code[2:6], 'little', signed=True)) == FH3
        return False

    funcs = []
    rejected = 0
    unwind_rejected = 0
    for st, (e, ui) in sorted(entries.items()):
        b = rd(ui, 4)
        if b is None or b == b'\0\0\0\0' or not (b[0] >> 3) & (P.EHANDLER | P.UHANDLER):
            continue
        hdr = 4 + 2 * ((b[2] + 1) & ~1)
        hb = rd(ui + hdr, 8)
        if hb is None or not handler_is_fh3(int.from_bytes(hb[:4], 'little')):
            continue
        fi = int.from_bytes(hb[4:8], 'little')
        tries, unwind = scopes_of(rd, fi, e)
        if tries is None:
            rejected += 1
            continue
        if unwind is None:
            unwind_rejected += 1
            unwind = []
        funclets = sorted(fh3_funclets_capped(rd, fi) or ())
        funcs.append({'begin': '0x%x' % st, 'fi': '0x%x' % fi,
                      'try_scopes': tries, 'unwind_scopes': unwind,
                      'funclets': ['0x%x' % f for f in funclets]})
        for s in tries + unwind:
            s['begin'], s['end'], s['target'] = '0x%x' % s['begin'], '0x%x' % s['end'], '0x%x' % s['target']

    try_fn = [f for f in funcs if f['try_scopes']]
    summary = {'fh3_functions': len(funcs), 'fh3_rejected': rejected, 'unwind_rejected': unwind_rejected,
               'try_functions': len(try_fn),
               'try_scopes': sum(len(f['try_scopes']) for f in funcs),
               'unwind_scopes': sum(len(f['unwind_scopes']) for f in funcs)}
    json.dump({'summary': summary, 'functions': funcs}, open(out_p, 'w'), indent=1)
    print(json.dumps(summary))


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
