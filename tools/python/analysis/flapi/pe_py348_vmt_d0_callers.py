#!/usr/bin/env python3
"""PY-348 (#4603): 仮想スロット 0xd0 の間接 call (call qword ptr [reg + 0xd0]) を .text 全体で数え、所属関数ごとに集計する。
併せて TQuickMenuItem (0x725a58) と TMenuItem (0x838c10) の VMT を指す rip 相対変位・即値を数え、
型を VMT 参照から絞れるかを確認する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py348_vmt_d0_callers.py [--dump <path>]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import bisect
import collections
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

RAW_PATH = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
TEXT_VA = 0x401000
TEXT_FO = 0x400
TEXT_SIZE = 0xFA34B0
VMT_Q = 0x725A58
VMT_T = 0x838C10
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def vmt_refs(raw):
    """VMT アドレスを rip 相対変位 (disp32 の直後の次命令 VA) か即値で指す位置。自己ポインタ (VMT-0xc8 の 8 バイト) を含む生の出現も数える。"""
    body = raw[TEXT_FO:TEXT_FO + TEXT_SIZE]
    out = {}
    for name, vmt in (("TQuickMenuItem", VMT_Q), ("TMenuItem", VMT_T)):
        hits = []
        for i in range(len(body) - 3):
            d = struct.unpack_from("<i", body, i)[0]
            if TEXT_VA + i + 4 + d == vmt:
                hits.append(TEXT_VA + i)
        out[name] = hits
    return out


def main():
    insns = pc.load()
    starts = pc.function_starts(insns)
    sites = []
    for a, m, o in insns:
        if m == "call" and o.startswith("qword ptr [") and o.endswith("+ 0xd0]"):
            sites.append((a, o))
    regs = collections.Counter(o.split("[")[1].split(" ")[0] for _, o in sites)
    fns = collections.defaultdict(list)
    for a, _ in sites:
        i = bisect.bisect_right(starts, a) - 1
        fns[starts[i] if i >= 0 else None].append(a)
    print(f"call [reg+0xd0] 件数: {len(sites)} / レジスタ別: {dict(regs)} / 所属関数 (推定): {len(fns)}")
    for fn in sorted(fns, key=lambda x: (x is None, x or 0)):
        print(f"  fn={hex(fn) if fn else None} sites={[hex(x) for x in fns[fn]]}")
    raw = open(RAW_PATH, "rb").read()
    refs = vmt_refs(raw)
    for k, v in refs.items():
        print(f"{k} VMT の rip 相対参照: {[hex(x) for x in v]}")
    if "--dump" in sys.argv:
        with open(sys.argv[sys.argv.index("--dump") + 1], "w") as f:
            for a, o in sites:
                f.write(f"{a:#x}\t{o}\n")
    check("0xd0 の間接 call (qword ptr [reg+0xd0]) 件数 243 (PY-320 §3 の 244 とは 1 件ずれ・差は未解明)",
          len(sites) == 243, f"n={len(sites)}")
    check("TQuickMenuItem VMT を指す rip 相対変位は 2 件 (型を VMT 参照で絞れないことの確認)",
          len(refs["TQuickMenuItem"]) == 2,
          f"hits={[hex(x) for x in refs['TQuickMenuItem']]}")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
