#!/usr/bin/env python3
"""hs_store_supplier.py — 未実行の応答スロット格納 (PLG-P0b-43 / #4130) の供給元を機械語から出す。

入力: 格納 VA の列 (既定は #3735 の 11 件)。出力: 各格納の直前命令・格納値の種別・
  * 即値格納なら、その格納へ至る分岐の入力 (al の供給元の読み出し元)
  * call 戻り値なら、呼出先の受け手 (レジスタに入る global / フィールドの連鎖)
  * [rip+disp] の global は PE 内の初期値をたどり、連鎖が静的に終わるかを示す
結論の判定は REPORT_DISPATCHER_APPENDIX_4130.md が行う。本スクリプトは出力を作るだけ。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_supplier.py [VA...]
"""
import os
import re
import sys
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pefile
import hs_resp_src as S
import hs_disp_emu as E

SITES = [0x1320e23, 0x13213f3, 0x1322971, 0x1328098, 0x1328104, 0x1328114,
         0x1328124, 0x1328131, 0x132818a, 0x1328197, 0x13281a4]


def aligned_window(read_va, site, back=0x60, n=14):
    """site に命令境界で一致する開始点を後方から探し、site 直前 n 命令を返す。"""
    for off in range(1, 0x40):
        start = site - back - off
        ins = list(S.md.disasm(read_va(start, back + off + 0x10), start))
        hit = [i for i, x in enumerate(ins) if x.address == site]
        if hit:
            return ins[max(0, hit[0] - n):hit[0] + 1]
    return None


def rip_global(ins):
    m = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', ins.op_str)
    if not m:
        return None
    disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
    return ins.address + ins.size + disp


def qword(read_va, va):
    b = read_va(va, 8)
    return struct.unpack('<Q', b)[0] if b and len(b) == 8 else None


def main():
    sites = [int(a, 0) for a in sys.argv[1:]] or SITES
    pe = pefile.PE(E.PE_PATH, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    rd = S.make_reader(pe, base)
    for site in sites:
        win = aligned_window(rd, site)
        print('==== 0x%x' % site)
        if not win:
            print('  (命令境界に揃わない)')
            continue
        for x in win:
            print('  %s0x%x: %s %s' % ('>>' if x.address == site else '  ', x.address, x.mnemonic, x.op_str))
        store = win[-1]
        src = store.op_str.split(',')[-1].strip()
        if src == 'rax':
            calls = [x for x in win[:-1] if x.mnemonic == 'call']
            if calls:
                print('  kind: rax (直近の call 0x%x: %s)' % (calls[-1].address, calls[-1].op_str))
            else:
                print('  kind: rax (窓内に call なし。直前の書込みを REPORT で辿る)')
        else:
            print('  kind: 即値 %s' % src)
    print('---- global 連鎖 (PE 内の初期値)')
    seen = set()
    code = rd(E.FN_LO, E.FN_HI - E.FN_LO)
    for ins in S.md.disasm(code, E.FN_LO):
        g = rip_global(ins)
        if g is None or g in seen:
            continue
        seen.add(g)
        p = qword(rd, g)
        o = qword(rd, p) if p else None
        print('  0x%x (at 0x%x %s): *G=%s *(*G)=%s' % (
            g, ins.address, ins.mnemonic,
            '0x%x' % p if p else '-', '0x%x' % o if o is not None else '-'))
    print('---- byte [rbp+0x89f] への書込み (dest 形式)')
    for ins in S.md.disasm(code, E.FN_LO):
        if ins.op_str.startswith('byte ptr [rbp + 0x89f]'):
            print('  0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))


if __name__ == '__main__':
    main()
