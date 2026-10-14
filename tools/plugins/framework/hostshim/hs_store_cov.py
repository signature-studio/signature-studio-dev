#!/usr/bin/env python3
"""hs_store_cov.py — Dispatcher の応答スロット [rbp+0x11a0] への格納命令の実行被覆 (#2886 / PLG-P0b-25)。

入力: hs_disp_emu.py を HS_DISP_PATH=1 で全 256 ID 実行した JSON (HS_DISP_OUT) を 1 つ以上。
  * 先頭 = 基準 (callee 戻り値は既定の 0)。以降 = callee 戻り値を変えた実行 (例: HS_DISP_RET_SPEC=0x40fe90:one)。
出力:
  * 静的: 関数 [FN_LO, FN_HI) 内で [rbp+0x11a0] へ書く命令の VA 数。
  * 基準の実行被覆: 全 ID の経路に現れた格納 VA の和集合。静的 − 被覆 = 基準で未実行の格納。
  * 以降の実行で新たに実行される格納 (VA と実行 ID)、および失われる格納。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_cov.py base.json [chg.json ...]
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E

INIT = 0x131873f  # 共通初期化 mov qword [rbp+0x11a0],0 (全 ID が実行する)
END = 0x1328a4a  # 共通終端 (応答 0 の ID が末尾に到達する VA)


def static_stores(read_va):
    code = read_va(E.FN_LO, E.FN_HI - E.FN_LO)
    out = set()
    for ins in S.md.disasm(code, E.FN_LO):
        if ins.mnemonic in ('mov', 'or') and ins.op_str.startswith('qword ptr ' + S.SLOT_STR + ','):
            out.add(ins.address)
    return out


def executed(run):
    res = {}
    for k, v in run.items():
        for a in v['path'] or []:
            res.setdefault(a, set()).add(int(k))
    return res


def no_case_store(run, static):
    """共通初期化 (INIT) の格納だけを実行し、共通終端 (END) に到達した ID の集合 (応答 0 の 202 件に相当)。"""
    return set(int(k) for k, v in run.items()
               if v['path'] and v['path'][-1] == END and set(a for a in v['path'] if a in static) == {INIT})


def main():
    runs = [json.load(open(p)) for p in sys.argv[1:]]
    if not runs:
        sys.exit('usage: hs_store_cov.py base.json [chg.json ...]')
    pe_data = open(E.PE_PATH, 'rb').read()
    pe, base, _ = E.load_image(pe_data)
    static = static_stores(S.make_reader(pe, base))
    ex0 = executed(runs[0])
    cov0 = set(a for a in ex0 if a in static)
    print('static stores in [0x%x,0x%x) = %d' % (E.FN_LO, E.FN_HI, len(static)))
    print('base executed (union over IDs) = %d / unexecuted = %d' % (len(cov0), len(static - cov0)))
    print('unexecuted: %s' % ' '.join('0x%x' % a for a in sorted(static - cov0)))
    s0 = no_case_store(runs[0], static)
    print('no-case-store IDs (init only, end 0x%x) = %d' % (END, len(s0)))
    for p, run in zip(sys.argv[2:], runs[1:]):
        ex = executed(run)
        now = set(a for a in ex if a in static)
        print('[%s]' % p)
        for a in sorted(now - cov0):
            print('  new  0x%x IDs=%s' % (a, ','.join('0x%02x' % i for i in sorted(ex[a]))))
        for a in sorted(cov0 - now):
            print('  lost 0x%x' % a)
        print('  executed = %d / new = %d / lost = %d' % (len(now), len(now - cov0), len(cov0 - now)))
        s = no_case_store(run, static)
        print('  no-case-store IDs = %d / leave = %s / enter = %s' % (
            len(s), ','.join('0x%02x' % i for i in sorted(s0 - s)) or '-', ','.join('0x%02x' % i for i in sorted(s - s0)) or '-'))


if __name__ == '__main__':
    main()
