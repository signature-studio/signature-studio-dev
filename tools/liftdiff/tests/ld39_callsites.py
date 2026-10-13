#!/usr/bin/env python3
"""LD-39 / LD-51 (#1526): 対象関数の呼出し側を PE の .text から E8 (call rel32) の全走査で数える。

  python3 tools/liftdiff/tests/ld39_callsites.py <PE> [--show N] [--list-dir DIR] [--targets VA ...] [--iat SLOT]

出力: 対象 VA ごとに E8 rel32 の一致件数、先頭 N 件の呼出し VA と直前の命令列。
--iat SLOT を指定すると、その IAT slot の import 名 (dll!名前) を pefile で引いて出す。
--list-dir を指定すると全件の VA 一覧を DIR/<VA>.txt に書く (DIR は work/ 等、commit しない)。

注意: E8 のバイト走査なので、命令の途中や data 上の E8 も拾う (偽陽性を含む上限値)。
      件数は「その VA に向かう E8 rel32 の数」で、真の呼出し件数とは一致しない場合がある。
      読んだ件の読みは人が行う (本 script は件数と先頭の命令列を出すだけ)。
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'liftdiff'))
import capstone  # noqa: E402
from ldlib import pe as P  # noqa: E402

TARGETS = ['40c660', '40c750', '4256c0', '664890', '6649b0', '6649c0', '664a80',
           '442a50', '442b90', '653c80', '691dd0']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe')
    ap.add_argument('--show', type=int, default=4)
    ap.add_argument('--list-dir', default=None)
    ap.add_argument('--targets', nargs='*', default=TARGETS)
    ap.add_argument('--iat', default=None, help='IAT slot VA (16 進)。import 名を pefile で引く')
    a = ap.parse_args()

    p = P.PE(a.pe)
    txt = [s for s in p.sections if s['name'] == '.text'][0]
    base = p.base + txt['rva']
    data = txt['data']
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    print('# LD-39 呼出し側 E8 走査 (PE=%s, image base=%#x, .text=%#x+%#x)' % (
        os.path.basename(a.pe), p.base, base, len(data)))

    want = {int(t, 16): t for t in a.targets}
    hits = {t: [] for t in want}
    # E8 rel32 を .text 全域でバイト走査する (命令境界は見ない)
    i = data.find(b'\xe8')
    while i != -1 and i + 5 <= len(data):
        rel = struct.unpack_from('<i', data, i + 1)[0]
        call_va = base + i
        tgt = (call_va + 5 + rel) & 0xffffffffffffffff
        if tgt in want:
            hits[tgt].append(call_va)
        i = data.find(b'\xe8', i + 1)

    if a.iat:
        import pefile
        iat_va = int(a.iat, 16)
        pe_obj = pefile.PE(a.pe, fast_load=False)
        found = None
        for ent in pe_obj.DIRECTORY_ENTRY_IMPORT:
            for imp in ent.imports:
                if imp.address == iat_va:
                    found = '%s!%s' % (ent.dll.decode('latin1'), imp.name.decode('latin1') if imp.name else 'ord%d' % imp.ordinal)
        print()
        print('== IAT %#x -> %s' % (iat_va, found))

    for t_va, t in want.items():
        vas = hits[t_va]
        print()
        print('== %s  E8 走査の件数: %d' % (t, len(vas)))
        for c in vas[:a.show]:
            print('  call @%#x' % c)
            # 直前 24 バイトを逆順に読めないので、少し前から逆アセンブルして call までの行を出す
            start = c - 24
            off = start - base
            if off >= 0:
                for ins in md.disasm(data[off:off + 24], start):
                    if ins.address >= c:
                        break
                    print('      %x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
            print('      %x: call %s' % (c, t))
        if a.list_dir and vas:
            os.makedirs(a.list_dir, exist_ok=True)
            with open(os.path.join(a.list_dir, t + '.txt'), 'w') as f:
                for c in vas:
                    f.write('%#x\n' % c)
    return 0


if __name__ == '__main__':
    sys.exit(main())
