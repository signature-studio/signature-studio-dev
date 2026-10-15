#!/usr/bin/env python3
"""élastique の RetDec 1 関数 lift の失敗 (data/retdec_lift_4284.csv の fail 行) を分類し、pdata 件数の出典を揃える (T-SH-141 / #5179)。

使い方: python3 elastique_fail_classify.py <dll> <retdec_lift_4284.csv>
出力: 件数の出典 (生 .pdata・.text 内・pefile)、fail 行の rc 内訳、各 fail 関数の EVEX マスク付き vpshufd/vshufi32x4 の有無。
"""
import collections
import os
import sys

import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from elastique_facts import parse_pe, pdata_funcs  # noqa: E402


def main():
    dll, csv = sys.argv[1], sys.argv[2]
    raw = open(dll, "rb").read()
    base, sections, image, dd = parse_pe(raw)
    txt = {s["name"]: s for s in sections}[".text"]
    lo, hi = base + txt["va"], base + txt["va"] + txt["vsize"]

    raw_pairs = pdata_funcs(image, base, dd)
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    pefile_n = len(getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", []))
    print(f"pdata 生スロット {len(raw_pairs)} / .text 内 {sum(lo <= b < hi for b, _ in raw_pairs)} / pefile {pefile_n}")

    status, ranges = {}, {}
    for line in open(csv):
        parts = line.strip().split(",", 1)
        if len(parts) == 2 and parts[0].startswith("0x"):
            status[parts[0]] = parts[1].strip()
    for b, e in raw_pairs:
        if lo <= b < hi:
            ranges[f"0x{b:x}"] = (b, e)

    print("fail 行の内訳:", dict(collections.Counter(v for v in status.values() if v != "ok")))

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    masked = collections.Counter()
    for key, st in status.items():
        if st == "ok" or key not in ranges:
            continue
        b, e = ranges[key]
        hit = next(
            (i for i in md.disasm(bytes(image[b - base:e - base]), b)
             if i.mnemonic in ("vpshufd", "vshufi32x4") and "{" in i.op_str),
            None,
        )
        masked[(st, hit is not None)] += 1
    print("fail 関数の EVEX マスク付き vpshufd/vshufi32x4 (rc, 有無) 件数:", dict(masked))

    ok_hit = 0
    for key, st in status.items():
        if st != "ok" or key not in ranges:
            continue
        b, e = ranges[key]
        if any(i.mnemonic in ("vpshufd", "vshufi32x4") and "{" in i.op_str
               for i in md.disasm(bytes(image[b - base:e - base]), b)):
            ok_hit += 1
    print("ok 関数のうち同命令を含むもの:", ok_hit)


if __name__ == "__main__":
    main()
