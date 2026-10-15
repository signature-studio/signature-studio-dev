#!/usr/bin/env python3
"""MX-43 (#3838) U4e 受入 1: FH3 funclet のうち flow 固定点で未到達のものを x64c の追加 root にする一覧を作る。

入力: PE, mx39_funclet_reach.py の reach.json (flow 到達 funclet を含む), 出力 roots.json (x64c --entries 形式)。
funclet universe の求め方は mx39_funclet_reach.main と同じ (mx6_pdata_eh の FH3 walk・上限棄却込み)。
既到達 (flow) の funclet は root に入れない (REPORT_APPENDIX_3776 §9.4 の 3. 二重 lift 回避)。
"""
import json
import os
import sys

import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mx6_pdata_eh as P  # noqa: E402
from mx39_funclet_reach import FH3, fh3_funclets_capped  # noqa: E402


def universe(pe_path):
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
            slot = h + 6 + int.from_bytes(code[2:6], 'little', signed=True)
            return iat.get(slot) == FH3
        return False

    fl_all = set()
    for st, (e, ui) in entries.items():
        b = rd(ui, 4)
        if b is None or b == b'\0\0\0\0':
            continue
        if not (b[0] >> 3) & (P.EHANDLER | P.UHANDLER):
            continue
        hdr = 4 + 2 * ((b[2] + 1) & ~1)
        hb = rd(ui + hdr, 8)
        if hb is None or not handler_is_fh3(int.from_bytes(hb[:4], 'little')):
            continue
        got = fh3_funclets_capped(rd, int.from_bytes(hb[4:8], 'little'))
        if got:
            fl_all |= set(got)
    return fl_all


def main(pe_path, reach_json, out_json):
    fl_all = universe(pe_path)
    reach = json.load(open(reach_json))
    flow_hit = {int(x['funclet'], 16) for x in reach['modes']['flow']['reached_funclets']}
    if not flow_hit <= fl_all:
        raise SystemExit('FATAL: flow 到達 funclet が universe の外にある (%d 件)' % len(flow_hit - fl_all))
    pe = pefile.PE(pe_path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    tx = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    lo = tx.VirtualAddress
    hi = lo + max(tx.Misc_VirtualSize, tx.SizeOfRawData)
    cand = sorted(fl_all - flow_hit)
    roots = [x for x in cand if lo <= x < hi]
    json.dump({'roots': [base + x for x in roots], 'calltgt': []}, open(out_json, 'w'), indent=1)
    print('universe=%d flow_reached=%d unreached=%d in_text=%d out_of_text_dropped=%d' % (
        len(fl_all), len(flow_hit), len(cand), len(roots), len(cand) - len(roots)))


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
