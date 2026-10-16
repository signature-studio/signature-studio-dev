#!/usr/bin/env python3
"""hs_store5_prov.py — 応答スロット格納 5 行 (#5421 / PLG-P0b-58) の供給元を機械語から出す。

hs_store5_src.py が出す格納直前の命令列に加え、各 call 先の戻り値 (eax/al/rax) が
どの命令で作られるかを、関数先頭から線形に逆アセンブルして示す。
出力は『確定』の根拠 (VA) と『未確定』の理由。ゲートの訪問数は基準 JSON から読む。

入力: hs_disp_emu.py を HS_DISP_PATH=1 で全 256 ID 実行した JSON (基準 base.json)。
使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store5_prov.py base.json
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E

# 格納 VA と、その値を作る call 先 (格納直前の call)
STORE_CALLEE = {
    0x13218c1: 0x1313220,  # call 0x1313220 → movsx rax, al
    0x13219b0: 0x1313220,  # call 0x1313220 → movsx rax, al
    0x1321966: 0xf5b190,   # call 0xf5b190 → cmp/sete (戻り値は未使用)
    0x1321b6c: 0x41d110,   # call 0x41d110 → rax + 0x12a8
    0x132257d: 0xfdd2c0,   # call 0xfdd2c0 → movsxd rax, eax
}
GATES = [0x1321854, 0x1321b19, 0x1322550]


def lin(rd, lo, hi):
    return [i for i in S.md.disasm(rd(lo, hi - lo), lo) if i.address < hi]


def show(rd, lo, hi, title):
    print('== %s 0x%x..0x%x' % (title, lo, hi))
    for i in lin(rd, lo, hi):
        print('  0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))


def writes_to(rd, lo, hi, disp):
    out = []
    for i in lin(rd, lo, hi):
        if i.mnemonic in ('mov', 'movzx', 'movsx', 'movsxd') and ('+ %s]' % disp) in i.op_str \
                and i.op_str.split(',')[0].strip().endswith(']'):
            out.append(i)
    return out


def main():
    run = json.load(open(sys.argv[1]))
    visited = {}
    for v in run.values():
        for a in v.get('path') or []:
            visited[a] = visited.get(a, 0) + 1
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)

    print('== 1. 格納 0x1321854 付近の窓 (線形)')
    show(rd, 0x13217a0, 0x13217e0, 'rbp+0x111c/0x111a の書込み周辺')
    for d in ('0x111c', '0x111a'):
        for i in writes_to(rd, 0x1321000, 0x1321966, d):
            print('  write [rbp+%s] at 0x%x: %s %s' % (d, i.address, i.mnemonic, i.op_str))

    print('== 2. 各格納の戻り値の由来 (call 先の戻り値を作る命令)')
    show(rd, 0x1313220, 0x1313220 + 0x80, 'callee 0x1313220 (先頭 128B)')
    show(rd, 0x40ffe0, 0x40ffe0 + 0x30, 'resolver 0x40ffe0 (call rax の関数ポインタ源)')
    show(rd, 0x41d110, 0x41d110 + 0x60, 'callee 0x41d110')
    rets = [i for i in lin(rd, 0xfdd2c0, 0xfdd2c0 + 0x2000) if i.mnemonic == 'ret']
    print('== callee 0xfdd2c0: ret 位置 %s' % [hex(r.address) for r in rets])
    show(rd, 0xfde880, 0xfde8ac + 1, 'callee 0xfdd2c0 末尾 (戻り値 [rbp+0x4c])')
    print('  [rbp+0x4c] 書込み箇所数 (0xfdd2c0..0xfde8ac): %d'
          % len(writes_to(rd, 0xfdd2c0, 0xfde8ac + 1, '0x4c')))

    print('== 3. 基準 run での訪問 (格納 0 件 / ゲート ID 数)')
    for st, callee in STORE_CALLEE.items():
        print('store 0x%x (callee 0x%x): visited by %d IDs' % (st, callee, visited.get(st, 0)))
    for g in GATES:
        print('gate 0x%x: visited by %d IDs' % (g, visited.get(g, 0)))


if __name__ == '__main__':
    main()
