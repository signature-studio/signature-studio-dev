#!/usr/bin/env python3
"""PY-325 (#4405): 0x72db20 (TQuickMenuItem の 0xd0 上書き関数) と 0x12acb70 (公開表 MoveLeftMenuClick) の参照元を PE 上で走査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py325_refs.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin' (<展開先>/extracted/block00031_PE.bin に展開される)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。負の対照は検出できれば PASS。
前段: pe_py320_fire_site.py (VMT 0x725a58・0x838c10 と slot 0xd0 の照合)。
"""
import os
import struct
import sys

RAW = open(os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin"), "rb").read()
TEXT_VA = 0x401000
TEXT_FO = 0x400
PDATA_FO = 0x1278400
PDATA_SIZE = 0xA9800
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def fo(va):
    return va - TEXT_VA + TEXT_FO


def hits(fmt, value):
    pat = struct.pack(fmt, value)
    out = []
    i = RAW.find(pat)
    while i >= 0:
        out.append(i)
        i = RAW.find(pat, i + 1)
    return out


SLOT_Q = 0x725A58 + 0xD0
q_fn = hits("<Q", 0x72DB20)
check("0x72db20 の 8 バイト参照は TQuickMenuItem の VMT スロット 0xd0 (VA 0x725b28) の 1 件のみ",
      q_fn == [fo(SLOT_Q)], f"hits={[hex(x) for x in q_fn]}")

d_fn = hits("<I", 0x72DB20)
pd = [x for x in d_fn if PDATA_FO <= x < PDATA_FO + PDATA_SIZE]
check("0x72db20 の 4 バイト参照のうち .pdata 内の 1 件は RUNTIME_FUNCTION の関数先頭 RVA (呼出しではない)",
      len(pd) == 1 and (pd[0] - PDATA_FO) % 12 == 0, f"pdata={[hex(x) for x in pd]}")
check("0x72db20 の 4 バイト参照の総数は VMT (qword の低位) と .pdata の 2 件のみ",
      len(d_fn) == 2 and fo(SLOT_Q) in d_fn, f"hits={[hex(x) for x in d_fn]}")

d_ml = hits("<I", 0x12ACB70)
check("0x12acb70 の 4 バイト参照は公開表の 1 件のみ (コードは即値で持たない)",
      len(d_ml) == 1, f"hits={[hex(x) for x in d_ml]}")

q_ml = hits("<Q", 0x12ACB70)
check("0x12acb70 の 8 バイト絶対値は公開表の 4 バイト参照と同じ 1 箇所 (表は 8 バイト絶対ポインタ)",
      q_ml == d_ml, f"q={[hex(x) for x in q_ml]} d={[hex(x) for x in d_ml]}")

q_disp = hits("<Q", 0x840B50)
check("負の対照: 0x840b50 は TMenuItem の VMT スロット 0xd0 として 8 バイト参照で検出される",
      fo(0x838C10 + 0xD0) in q_disp, f"hits={[hex(x) for x in q_disp]}")

sys.exit(0 if all(RESULTS) else 1)
