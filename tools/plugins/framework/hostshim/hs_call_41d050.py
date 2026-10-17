#!/usr/bin/env python3
"""hs_call_41d050.py — 0x41d050 の直接呼出元を機械語から列挙する (#5421 / PLG-P0b-58)。

0x41d050 は 0x13a9388 (= 0x41cf40 の戻り値を格納) を書く関数。その直接呼出元を出す。

出す事実 (機械語・VA):
  1. 0x41d050 を直接 `call rel32` する箇所 (.text 0x1000000..0x1400000)
  2. 各呼出元を含む関数の先頭 (push rbp 直前の ret/int3/nop の後を後方探索)
  3. 呼出元の直前 16 命令

走査範囲: 1〜3 は逆アセンブル (call のみ, .text 0x1000000..0x1400000)。参照の件数は生バイト走査 (E8/E9 rel32・絶対 32bit・RVA 32bit, 0x400000..0x13a44b0) で、jmp は生バイト経由のみ。RIP 相対 lea は未走査。
限界: 間接 call・RIP 相対 lea・レジスタ経由の関数ポインタは含まない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared の site-packages> python3 hs_call_41d050.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E
import hs_store_111c as W

FUNC = 0x41d050


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)

    allins = W.scan(rd, 0x1000000, 0x1400000)
    pos = {i.address: k for k, i in enumerate(allins)}

    print('== 0x%x を直接 call する箇所 (.text 0x1000000..0x1400000)' % FUNC)
    sites = []
    for k, i in enumerate(allins):
        if i.mnemonic == 'call' and i.op_str.startswith('0x'):
            try:
                tgt = int(i.op_str, 16)
            except ValueError:
                continue
            if tgt == FUNC:
                sites.append(k)
                print('  0x%x call 0x%x' % (i.address, tgt))
    print('  件数: %d' % len(sites))

    for k in sites:
        site = allins[k].address
        print('== 呼出元 0x%x の直前 16 命令' % site)
        for j in range(max(0, k - 16), k + 1):
            i = allins[j]
            print('  0x%x %s %s' % (i.address, i.mnemonic, i.op_str))

    chunks = []
    for s in pe.sections:
        va = base + s.VirtualAddress
        if 0x400000 <= va < 0x13a44b0 + 0x1000:
            chunks.append((va, rd(va, s.Misc_VirtualSize)))

    def refs(target):
        absn = abs64 = rvan = relc = 0
        for va, blob in chunks:
            for p in range(len(blob) - 4):
                v = struct.unpack('<I', blob[p:p + 4])[0]
                if v == target:
                    absn += 1
                if v == target - 0x400000:
                    rvan += 1
            for p in range(len(blob) - 8):
                if struct.unpack('<Q', blob[p:p + 8])[0] == target:
                    abs64 += 1
            for p in range(len(blob) - 5):
                if blob[p] in (0xe8, 0xe9):
                    rel = struct.unpack('<i', blob[p + 1:p + 5])[0]
                    if va + p + 5 + rel == target:
                        relc += 1
        return relc, absn, abs64, rvan

    print('== 0x%x の参照 (0x400000..0x13a44b0 の生バイト・セクション単位)' % FUNC)
    relc, absn, abs64, rvan = refs(FUNC)
    print('  rel32 call/jmp: %d 件 / 絶対 32bit: %d 件 / 絶対 64bit: %d 件 / RVA 32bit: %d 件' % (relc, absn, abs64, rvan))
    print('== control 0x41d110 の参照 (同じ生バイト走査)')
    relc, absn, abs64, rvan = refs(0x41d110)
    print('  rel32 call/jmp: %d 件 / 絶対 32bit: %d 件 / 絶対 64bit: %d 件 / RVA 32bit: %d 件' % (relc, absn, abs64, rvan))


if __name__ == '__main__':
    main()
