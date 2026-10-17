#!/usr/bin/env python3
"""hs_jmp_41cf60.py — 0x41cf60 の間接 jmp 先を IAT から解決する (#5421 / PLG-P0b-58)。

出す事実 (機械語・PE 上の静的値のみ):
  1. 0x41cf60 の逆アセンブル (先頭 2 命令)
  2. jmp スロット VA (= 0x41cf66 + disp32) と、スロットの PE 上の初期値
  3. スロットを指す PE インポート名 (DLL・関数名)

限界: 実行時にローダが書き換える値そのものではなく、PE のインポート表から引く。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared の site-packages> python3 hs_jmp_41cf60.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_disp_emu as E
import hs_resp_src as S
import hs_store_111c as W

FUNC = 0x41cf60
DISP_END = 0x41cf66  # jmp qword ptr [rip + disp32] の次の命令の先頭 (6B)


def main():
    raw = open(E.PE_PATH, 'rb').read()
    pe, base, _ = E.load_image(raw)
    rd = S.make_reader(pe, base)

    print('== 0x%x (先頭 2 命令)' % FUNC)
    for ins in W.scan(rd, FUNC, FUNC + 0x7):
        print(ins)

    ins_bytes = rd(FUNC, 6)
    disp = struct.unpack('<i', ins_bytes[2:6])[0]
    slot = DISP_END + disp
    print('jmp スロット VA = 0x%x (disp32 = %#x)' % (slot, disp))

    val = struct.unpack('<Q', rd(slot, 8))[0]
    print('スロットの PE 初期値 = 0x%x' % val)

    import pefile
    pef = pefile.PE(E.PE_PATH, fast_load=False)
    ib = pef.OPTIONAL_HEADER.ImageBase
    hits = []
    for entry in pef.DIRECTORY_ENTRY_IMPORT:
        for imp in entry.imports:
            if imp.address is not None and imp.address - ib == slot - base:
                hits.append((entry.dll.decode(), imp.name.decode() if imp.name else None))
    print('IAT 一致 = %s' % (hits if hits else 'なし'))


if __name__ == '__main__':
    main()
