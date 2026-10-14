#!/usr/bin/env python3
"""unicorn_trace.py の watch writes を、書込み元 rip の囲む pdata 関数ごとに集計する (#2493)。

使い方: python3 write_origin.py <block_PE.bin> <unicorn_trace.py の出力ファイル>
出力: 関数 (pdata 範囲) ごとの書込み件数・書込み元 rip の範囲・書込み先の範囲と、
書込み元命令 (capstone の逆アセンブル)。どの pdata 関数にも入らない rip は unmapped として数える。
"""
import bisect
import re
import struct
import sys

import capstone
import pefile

WRITE_RE = re.compile(r'write (0x[0-9a-f]+) size=(\d+) val=(0x[0-9a-f]+) rip=(0x[0-9a-f]+)')
SHOWN_RE = re.compile(r'watch writes \((\d+) shown\)')


def main(argv):
    pe = pefile.PE(argv[1], fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytes(pe.get_memory_mapped_image())
    pd = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".pdata"][0]
    raw = img[pd.VirtualAddress:pd.VirtualAddress + pd.Misc_VirtualSize]
    funcs = []
    for i in range(0, len(raw) - 11, 12):
        b, e, _ = struct.unpack_from("<III", raw, i)
        if b == 0:
            break
        funcs.append((base + b, base + e))
    funcs.sort()
    starts = [f[0] for f in funcs]

    def enclosing(a):
        i = bisect.bisect_right(starts, a) - 1
        return funcs[i] if i >= 0 and funcs[i][0] <= a < funcs[i][1] else None

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def disasm(va):
        for ins in md.disasm(img[va - base:va - base + 16], va, 1):
            return "%s %s" % (ins.mnemonic, ins.op_str)
        return "?"

    writes = []
    shown = None
    with open(argv[2], encoding="utf-8") as fh:
        for line in fh:
            m = WRITE_RE.search(line)
            if m:
                writes.append(tuple(int(x, 16) for x in m.groups()))
            s = SHOWN_RE.search(line)
            if s:
                shown = int(s.group(1))
    if shown is not None and shown != len(writes):
        print("warning: 出力の件数 %d と書込み行 %d が不一致 (LOG_LIMIT で切られた可能性)" % (shown, len(writes)))

    groups = {}
    unmapped = 0
    for addr, size, val, rip in writes:
        f = enclosing(rip)
        if f is None:
            unmapped += 1
            continue
        groups.setdefault(f, []).append((addr, rip))

    print("watch writes: %d (unicorn_trace の出力行)" % len(writes))
    for f in sorted(groups):
        ws = groups[f]
        rips = sorted({rip for _, rip in ws})
        addrs = sorted({a for a, _ in ws})
        print("pdata fn [%#x,%#x): %d 件、書込み元 rip %#x-%#x (%d 種)、書込み先 %#x-%#x" % (
            f[0], f[1], len(ws), rips[0], rips[-1], len(rips), addrs[0], addrs[-1]))
        for rip in rips:
            print("  rip %#x  %s" % (rip, disasm(rip)))
    print("unmapped (pdata 関数に入らない書込み元): %d" % unmapped)


if __name__ == "__main__":
    main(sys.argv)
