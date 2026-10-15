#!/usr/bin/env python3
"""PY-351 (#4656): TQuickMenuItem の VMT (0x725a58) を書く箇所を全形式で走査する。

PY-348 (pe_py348_vmt_d0_callers.py) は rip 相対 disp32 だけを数えた。本 probe は次の形式を追加で数える。
- オペランド文字列に 0x725a58 を含む命令 (即値の mov/push)。rip 相対の変位は PY-348 の probe が数える
- 生バイトの絶対アドレス (4 バイト LE 0x725a58 と 8 バイト LE 0x725a58) の .text 内の出現

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py351_vmt_writes.py [--dump <path>]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin' (展開先で実行)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import bisect
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

RAW_PATH = pc.PE
VMT_Q = 0x725A58
TEXT_VA = 0x401000
TEXT_FO = 0x400
TEXT_SIZE = 0xFA34B0
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def main():
    insns = pc.load()
    starts = pc.function_starts(insns)
    imm_hits = []
    for a, m, o in insns:
        if f"0x{VMT_Q:x}" in o:
            imm_hits.append((a, m, o))
    print(f"命令オペランドに 0x725a58 を含む: {len(imm_hits)}")
    for a, m, o in imm_hits:
        i = bisect.bisect_right(starts, a) - 1
        fn = starts[i] if i >= 0 else None
        print(f"  {a:#x} fn={hex(fn) if fn else None} {m} {o}")

    raw = open(RAW_PATH, "rb").read()
    body = raw[TEXT_FO:TEXT_FO + TEXT_SIZE]
    abs4 = [TEXT_VA + i for i in range(len(body) - 3)
            if struct.unpack_from("<I", body, i)[0] == VMT_Q]
    abs8 = [TEXT_VA + i for i in range(len(body) - 7)
            if struct.unpack_from("<Q", body, i)[0] == VMT_Q]
    print(f".text 内の 4 バイト絶対 0x725a58: {[hex(x) for x in abs4]}")
    print(f".text 内の 8 バイト絶対 0x725a58: {[hex(x) for x in abs8]}")

    if "--dump" in sys.argv:
        with open(sys.argv[sys.argv.index("--dump") + 1], "w") as f:
            for a, m, o in imm_hits:
                f.write(f"{a:#x}\t{m}\t{o}\n")

    check("0x725a58 を即値・オペランドに持つ命令 0 件 (rip 相対 lea は PY-348 側で数える)",
          len(imm_hits) == 0, f"n={len(imm_hits)}")
    check(".text 内の 8 バイト絶対 0x725a58 は VMT 先頭の自己ポインタ 0x725990 と RTTI 0x725b80 の 2 件 (データで、コードの VMT 書込みではない)",
          [hex(x) for x in abs8] == ["0x725990", "0x725b80"], f"hits={[hex(x) for x in abs8]}")
    check("PY-320 §3 の 244 件 = qword 形 243 + qword 接頭辞なし形 1 (0xd00111)",
          sum(1 for _, m, o in insns if m == "call" and o.endswith("+ 0xd0]") and "[" in o) == 244,
          f"n={sum(1 for _, m, o in insns if m == 'call' and o.endswith('+ 0xd0]') and '[' in o)}")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
