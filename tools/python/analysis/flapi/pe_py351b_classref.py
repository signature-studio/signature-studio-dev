#!/usr/bin/env python3
"""PY-351b (#5309): TQuickMenuItem の VMT (0x725a58) を指す値を PE イメージ全体で数える。

pe_py351_vmt_writes.py は .text 内だけを見た。本 probe は .data・.rdata・.pdata 等を含むイメージ全体を見て、
(1) 8 バイト絶対値 (2) 4 バイト RVA 値 (3) rip 相対の lea・mov で VMT を指す箇所 を数える。
どれも VMT 自身の自己ポインタ・RTTI 位置以外に無ければ、TQuickMenuItem のインスタンスは静的な定数では作られていない。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py351b_classref.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402
import pefile  # noqa: E402

VMT_Q = 0x725A58
VMT_SELF = {0x725990, 0x725B80}  # VMT-0xc8 の自己ポインタ位置・RTTI 位置 (.text 内のデータ。PY-351 で確認済み)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def main():
    raw = open(pc.PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def fo2va(fo):
        for s in pe.sections:
            if s.PointerToRawData <= fo < s.PointerToRawData + s.SizeOfRawData:
                return base + s.VirtualAddress + fo - s.PointerToRawData
        return None

    abs8 = sorted(fo2va(i) for i in range(len(raw) - 7) if struct.unpack_from("<Q", raw, i)[0] == VMT_Q)
    rva4 = sorted(fo2va(i) for i in range(len(raw) - 3) if struct.unpack_from("<I", raw, i)[0] == VMT_Q - base)
    print(f"8 バイト絶対 0x725a58 (イメージ全体): {[hex(x) if x else None for x in abs8]}")
    print(f"4 バイト RVA 0x325a58 (イメージ全体): {[hex(x) if x else None for x in rva4]}")

    insns = pc.load()
    nxt = {insns[k][0]: insns[k + 1][0] for k in range(len(insns) - 1)}
    rip_refs = []
    for a, m, o in insns:
        if "[rip" not in o:
            continue
        part = o.split("[rip")[1].split("]")[0].replace(" ", "")
        sign = -1 if "-" in part else 1
        try:
            d = int(part.lstrip("+-"), 16)
        except ValueError:
            continue
        if a in nxt and nxt[a] + sign * d == VMT_Q:
            rip_refs.append((a, m, o))
    print(f"rip 相対で 0x725a58 を指す命令: {[(hex(a), m, o) for a, m, o in rip_refs]}")
    imm_refs = [(a, m, o) for a, m, o in insns if f"0x{VMT_Q:x}" in o]
    print(f"オペランドに 0x725a58 を持つ命令: {len(imm_refs)}")

    check("8 バイト絶対 0x725a58 はイメージ全体で VMT 自己ポインタ・RTTI の 2 件のみ (クラス参照変数なし)",
          {x for x in abs8} == VMT_SELF, f"hits={[hex(x) if x else None for x in abs8]}")
    check("4 バイト RVA 0x325a58 はイメージ全体で 0 件 (RVA 形のクラス参照なし)",
          len(rva4) == 0, f"n={len(rva4)}")
    check("rip 相対で 0x725a58 を指す命令は 0 件 (VMT 自身の自己ポインタ位置は .text のデータで、命令ではない)",
          len(rip_refs) == 0, f"n={len(rip_refs)}")
    check("オペランドに 0x725a58 を持つ命令は 0 件",
          len(imm_refs) == 0, f"n={len(imm_refs)}")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
