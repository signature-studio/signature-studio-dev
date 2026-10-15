#!/usr/bin/env python3
"""PY-403 (#4921): 述語 0x12d8d30 (pred) の真偽を、G1 (0x15d51a0) の添字ごとに静的データから評価する。

  FL_WIN64_DIR=<展開先> python3 analysis/py403_pred_table.py [最大添字]

pred(ecx=G1, dl=1, r8b=1, r9b=1) の逆アセンブル (0x12d8d30..0x12d8db1) を読んだ結果:
  エントリ E = TABLE + G1*0xc0
  A = [E+0x20] != 0 かつ dword[[E+0x20]+0x14] > 0
  B = A かつ/または ([E+0x28] != 0 かつ dword[[E+0x28]+0x14] > 0)
  pred = !B かつ byte[E+0x84] != 0 かつ qword[E] == 0 かつ byte[E+0x14] == 0 かつ dword[E+0x10] == -1

結果 (PY-403 測定): テーブル 0x193fce0 は RVA 0x153fce0 で .bss (raw データ無し) に入る。
エントリの中身はファイルに無く実行時に決まるため、65 件 (添字 0..0x40) すべて読めず pred は確定しない。
ポインタの先 (+0x14) も heap 等の実行時値のため同様。G1 の初期値 (ファイル上) は 1。
"""
import os
import struct
import sys

import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
G1_VA = 0x15D51A0
TABLE_VA = 0x12D8D37 + 0x666FA9
STRIDE = 0xC0


def main():
    max_idx = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x40
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def rd(va, n):
        # ファイル上の値として読めるのは SizeOfRawData の範囲だけ。.bss など raw の無い領域は
        # 実行時に初期化されるため静的には決まらず None を返す。
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
                rel = rva - s.VirtualAddress
                if rel + n > s.SizeOfRawData:
                    return None
                off = s.PointerToRawData + rel
                return raw[off:off + n]
        return None

    g1 = rd(G1_VA, 4)
    print(f"G1 static (0x15d51a0): {struct.unpack('<i', g1)[0] if g1 else 'unreadable'}")
    print(f"TABLE {TABLE_VA:#x} stride {STRIDE:#x}")
    print("idx | ptr20 ptr28 | p20.14 p28.14 | b84 q0 b14 d10 | pred")
    for idx in range(max_idx + 1):
        e = TABLE_VA + idx * STRIDE
        ent = rd(e, STRIDE)
        if ent is None:
            print(f"{idx:3d} | unreadable")
            continue
        p20 = struct.unpack_from('<Q', ent, 0x20)[0]
        p28 = struct.unpack_from('<Q', ent, 0x28)[0]
        q0 = struct.unpack_from('<Q', ent, 0x00)[0]
        b14 = ent[0x14]
        b84 = ent[0x84]
        d10 = struct.unpack_from('<i', ent, 0x10)[0]

        def pointee_val(p):
            if p == 0:
                return 0
            r = rd(p + 0x14, 4)
            return None if r is None else struct.unpack('<i', r)[0]

        v20 = pointee_val(p20)
        v28 = pointee_val(p28)
        if v20 is None or v28 is None:
            pred = "unknown"
        else:
            a = (p20 != 0) and v20 > 0
            b = a or ((p28 != 0) and v28 > 0)
            pred = int((not b) and b84 != 0 and q0 == 0 and b14 == 0 and d10 == -1)
        print(f"{idx:3d} | {p20:#x} {p28:#x} | {v20} {v28} | {b84} {q0:#x} {b14} {d10} | {pred}")


if __name__ == "__main__":
    main()
