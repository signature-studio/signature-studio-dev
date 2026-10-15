#!/usr/bin/env python3
"""undo 系 (cmd 0x14/0x15/0x16) の戻り値 out+0x08 の出所 (PY-354 / #4682) を PE から検算する (読取りのみ)。

確認する事実 (結論は tools/python/REPORT_PY354.md):
  1. 0xd84680 を呼ぶ箇所のうち、直前の r8d が 0x14・0x15・0x16 のものを列挙する (undo 系)。
  2. 0xd84680 は out (rbx) を 0xfdd2c0 に渡さない。out への store は out+0 (qword ptr [rbx]) の 3 箇所だけ。
  3. 0x415610 は out+0x10 だけを書く経路を含み、out+0x08 ([rbx+8] / [rbp+...]) への store を持たない
     (0x415610 の全 store を列挙して確認)。
  4. 0xd843d0 の out+8 ([rsi+8]) への store は 0xd844c6 の 1 箇所 (値は [obj+0x10])。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py354_probe.py
期待値と一致しなければ rc 1 で止まる。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
FAIL = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        FAIL.append(msg)


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = [(s.VirtualAddress, max(s.Misc_VirtualSize, s.SizeOfRawData), s.PointerToRawData)
            for s in pe.sections]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def v2o(va):
        rva = va - base
        for vaddr, size, praw in secs:
            if vaddr <= rva < vaddr + size:
                return praw + (rva - vaddr)
        return None

    def o2v(off):
        for vaddr, size, praw in secs:
            if praw <= off < praw + size:
                return base + vaddr + (off - praw)
        return None

    def dis(start, end):
        return list(md.disasm(raw[v2o(start):v2o(start) + end - start], start))

    def direct(i):
        if i.mnemonic.startswith(("j", "call")) and i.op_str.startswith("0x"):
            return int(i.op_str, 16)
        return None

    # 1. 0xd84680 の呼出し元のうち、直前 (16 命令内) の r8d が 0x14/0x15/0x16 のもの
    callers = []
    for m in re.finditer(b"\xe8", raw):
        off = m.start()
        va = o2v(off)
        if va is None or off + 5 > len(raw):
            continue
        if va + 5 + struct_i32(raw, off + 1) == 0xD84680:
            callers.append(va)
    undo_sites = []
    for c in callers:
        prev = dis(c - 0x40, c)
        r8 = None
        for i in prev:
            if i.address >= c:
                break
            m = re.match(r"(r8d|r8), (0x[0-9a-f]+|\d+)$", i.op_str) if i.mnemonic == "mov" else None
            if m:
                r8 = int(m.group(2), 16 if m.group(2).startswith("0x") else 10)
        if r8 in (0x14, 0x15, 0x16):
            undo_sites.append((c, r8))
    print("0xd84680 呼出し元:", [hex(c) for c in callers])
    print("undo 系 (cmd 0x14/0x15/0x16) の呼出し:", [(hex(c), hex(r)) for c, r in undo_sites])
    check(len(undo_sites) >= 3, f"undo 系の 0xd84680 呼出しが 3 種 (0x14/0x15/0x16) 以上見つかる (実測 {len(undo_sites)} 件)")

    # 2. 0xd84680 の out (rbx) の store は out+0 の 3 箇所だけ、rbx は 0xfdd2c0 に渡らない
    ins = dis(0xD84680, 0xD846DB)
    rbx_stores = [i for i in ins if i.mnemonic == "mov" and i.op_str.split(", ")[0].startswith("qword ptr [rbx")]
    check(len(rbx_stores) == 3 and all(i.op_str.split(", ")[0] == "qword ptr [rbx]" for i in rbx_stores),
          "0xd84680 の out への store は qword ptr [rbx] (out+0) の 3 箇所だけ")
    calls = [i for i in ins if direct(i) == 0xFDD2C0]
    before = ins[:ins.index(calls[0])] if calls else []
    check(len(calls) == 1 and not any(i.op_str.endswith(", rbx") for i in before),
          "0xd84680 の 0xfdd2c0 呼出し前に out (rbx) を引数へ渡す命令は無い")

    # 3. 0x415610 (関数末尾 0x4158b2) の store 先に out+8 相当 (+8 のオフセット) が無い
    ins = dis(0x415610, 0x4158B2)
    st = [i for i in ins if i.mnemonic == "mov" and "ptr [" in i.op_str.split(", ")[0]]
    suspicious = [i for i in st if re.search(r"\+ 0x8\]|\+ 8\]", i.op_str.split(", ")[0])]
    check(not suspicious, f"0x415610 (末尾 0x4158b2) の store 先に +8 のオフセットは無い (実測 {[i.op_str for i in suspicious]})")

    # 4. 0xd843d0 の out+8 への store は 0xd844c6 の 1 箇所
    ins = dis(0xD843D0, 0xD84510)
    out8 = [i for i in ins if i.mnemonic == "mov" and i.op_str.split(", ")[0] == "qword ptr [rsi + 8]"]
    check(len(out8) == 1 and out8[0].address == 0xD844C6, "0xd843d0 の out+8 ([rsi+8]) への store は 0xd844c6 の 1 箇所")

    # 5. undo ハンドラ (0xd68dc0 ほか) の out (rbp+0x48) の out+8 (rbp+0x50) への store が無い
    rows = sorted((e.struct.BeginAddress + base, e.struct.EndAddress + base) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    fn_ranges = {}
    for site, _ in undo_sites + [(0xD68DD8, 0)]:
        for s, e in rows:
            if s <= site < e:
                fn_ranges[s] = e
    for s, e in sorted(fn_ranges.items()):
        ins = dis(s, e)
        out8_stores = [i for i in ins if i.mnemonic == "mov" and i.op_str.split(", ")[0] in ("qword ptr [rbp + 0x50]", "dword ptr [rbp + 0x50]")]
        check(not out8_stores, f"undo fn {s:#x}: out+8 ([rbp+0x50]) への store は無い")
    h = dis(0xD68DC0, 0xD68DDD)
    check(any(i.address == 0xD68DCD and i.op_str == "rcx, [rbp + 0x48]" for i in h)
          and any(i.address == 0xD68DD8 and direct(i) == 0x415610 for i in h),
          "undo fn 0xd68dc0: out = [rbp+0x48] を 0x415610 に渡す (0xd68dd8)")

    if FAIL:
        print(f"FAIL {len(FAIL)} 件")
        sys.exit(1)
    print("PASS")


def struct_i32(raw, off):
    import struct
    return struct.unpack_from("<i", raw, off)[0]


if __name__ == "__main__":
    main()
