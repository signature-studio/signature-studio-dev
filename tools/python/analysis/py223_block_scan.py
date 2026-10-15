#!/usr/bin/env python3
"""PY-223 (#3627) 受入 4: block00031 以外の PE block が、block00031 の G1・T・flag・表の VA を絶対値で指すかを全 PE block で数える。

  FL_WIN64_DIR=<展開先> python3 analysis/py223_block_scan.py [--mutate]

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*_PE.bin' (313 block)
各 block の Machine・ImageBase を表にし、block00031 (ImageBase 0x400000) の VA を、8 byte (qword) と 4 byte (imm32・絶対 disp32) の
リトルエンディアン一致として全 block の生バイト列から数える。
RIP 相対の参照は、その命令と同じ PE の VA 空間の中だけを指す。別 block から block00031 の VA を指せるのは絶対値の形だけなので、
この走査で別 block の RIP 相対を見る必要は無い (構造上の理由。線形走査はしていない)。
検査 (positive control): block00031 の qword に 0xed4b70 (表の添字 51) と 0xed0c28 (cell 0xed0b60 の値) が各 1 件以上あること。
--mutate: 検査の値を 1 ビット反転して FAIL することを確かめる (ネガティブコントロール)。
"""
import glob
import os
import struct
import sys

import pefile

DIR = os.path.join(os.environ["FL_WIN64_DIR"], "extracted")
MAIN = "block00031_PE.bin"
TARGETS = [
    ("G1 0x15d51a0", 0x15D51A0),
    ("flag cell 0x15e14a0", 0x15E14A0),
    ("T base 0x193fcf8", 0x193FCF8),
    ("T row 0x193fd08", 0x193FD08),
    ("table slot 51 0xed4b70", 0xED4B70),
    ("table base A 0xed0bb0", 0xED0BB0),
    ("table base B 0xed0c28", 0xED0C28),
    ("cell 0xed0b60", 0xED0B60),
    ("caller 0x12da6d0", 0x12DA6D0),
]
CONTROLS = [0xED4B70, 0xED0C28]


def count(raw, pat):
    hits, pos = [], raw.find(pat)
    while pos != -1:
        hits.append(pos)
        pos = raw.find(pat, pos + 1)
    return hits


def main():
    mutate = "--mutate" in sys.argv
    paths = sorted(glob.glob(os.path.join(DIR, "*_PE.bin")))
    machines = {}
    ibs = {}
    per = {}
    for p in paths:
        name = os.path.basename(p)
        raw = open(p, "rb").read()
        pe = pefile.PE(data=raw, fast_load=True)
        mach = pe.FILE_HEADER.Machine
        ib = pe.OPTIONAL_HEADER.ImageBase
        machines[mach] = machines.get(mach, 0) + 1
        ibs[ib] = ibs.get(ib, 0) + 1
        res = {}
        for label, v in TARGETS + [("control", c) for c in CONTROLS]:
            if mutate and name == MAIN and label == "control":
                v ^= 0x10
            pat8 = struct.pack("<Q", v)
            res[(label, v, 8)] = count(raw, pat8)
            if v < 1 << 32:
                res[(label, v, 4)] = count(raw, struct.pack("<I", v))
        per[name] = (mach, ib, len(raw), res)

    print(f"blocks {len(paths)}: " + ", ".join(f"{hex(m)} {n}" for m, n in sorted(machines.items())))
    print("ImageBase: " + ", ".join(f"{hex(b)} {n}" for b, n in sorted(ibs.items(), key=lambda x: -x[1])[:6]))
    print(f"block00031 ImageBase {hex(per[MAIN][1])}, machine {hex(per[MAIN][0])}")

    main_res = per[MAIN][3]
    ctrl_ok = True
    print("\n[target] VA: 8byte/4byte hits in other blocks (blocks) | block00031 self 8byte/4byte")
    for label, v in TARGETS:
        n8, n4, blocks = 0, 0, []
        for name, (mach, ib, size, res) in per.items():
            if name == MAIN:
                continue
            a = len(res.get((label, v, 8), []))
            b = len(res.get((label, v, 4), []))
            n8 += a
            n4 += b
            if a or b:
                blocks.append(f"{name}(m{hex(mach)} ib{hex(ib)} 8b={a} 4b={b})")
        self8 = len(main_res.get((label, v, 8), []))
        self4 = len(main_res.get((label, v, 4), []))
        print(f"  {label}: other {n8}/{n4} | self {self8}/{self4}")
        for x in blocks[:12]:
            print(f"      {x}")
    print("\n[control] block00031 qword の既知の一致 (表の添字 51 の 0xed4b70・cell 0xed0b60 の 0xed0c28)")
    for v in CONTROLS:
        hits = main_res.get(("control", v, 8), [])
        ok = len(hits) >= 1
        ctrl_ok = ctrl_ok and ok
        print(f"  {hex(v)}: {len(hits)} hit(s) at {[hex(h) for h in hits[:4]]} {'PASS' if ok else 'FAIL'}")
    if mutate:
        print("mutate: control value changed on purpose")
    verdict = "PASS" if ctrl_ok else "FAIL"
    print(f"block.check {verdict}")
    sys.exit(0 if ctrl_ok else 1)


if __name__ == "__main__":
    main()
