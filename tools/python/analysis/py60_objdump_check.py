#!/usr/bin/env python3
"""PY-60 (#1982): 0x1046a30〜0x104ccca の jcc/jmp 辺を objdump で独立に取り直し、capstone 出力 (fn.txt) と照合する。

  python3 analysis/py60_objdump_check.py <PE.bin> <work/py53/fn.txt>

objdump (GNU binutils) は分岐先を「ファイル先頭からの絶対オフセット」で出す。
VA = オフセット + (ImageBase + .text.VirtualAddress - .text.PointerToRawData) で換算する。
出力: 辺の総数・一致数・不一致数と、出口ブロック (0x104cc2e・0x104cc65・0x104cc72・0x104cb04) への入辺。
"""
import re
import subprocess
import sys

import pefile

FN_START = 0x1046A30
FN_END = 0x104CCCB


def main():
    pe_path, fn_path = sys.argv[1], sys.argv[2]
    pe = pefile.PE(pe_path, fast_load=True)
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    shift = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress - text.PointerToRawData
    start = FN_START - shift
    stop = FN_END - shift + 1
    out = subprocess.run(
        ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64",
         f"--start-address={start:#x}", f"--stop-address={stop:#x}", pe_path],
        capture_output=True, text=True, check=True,
    ).stdout

    cap = {}
    for ln in open(fn_path):
        m = re.match(r"(0x[0-9a-f]+): (\S+)\s*(.*)", ln.strip())
        if m:
            cap[int(m.group(1), 16)] = (m.group(2), m.group(3).split()[0] if m.group(3) else "")

    edges = {}
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3 or not parts[2].strip():
            continue
        mn = parts[2].split()[0]
        if not mn.startswith("j"):
            continue
        va = int(parts[0].strip().rstrip(":"), 16) + shift
        tgt = int(parts[2].split()[1], 16) + shift
        edges[va] = (mn, tgt)

    agree = sum(1 for va, (mn, tgt) in edges.items()
                if va in cap and cap[va][0] == mn and cap[va][1] == f"0x{tgt:x}")
    print(f"objdump jcc/jmp={len(edges)} agree={agree} disagree={len(edges) - agree}")
    for tgt in (0x104CC2E, 0x104CC65, 0x104CC72, 0x104CB04):
        srcs = sorted(f"{v:#x}" for v, (_, t) in edges.items() if t == tgt)
        print(f"into {tgt:#x}: {len(srcs)} edges {srcs}")
    return 0 if agree == len(edges) else 1


if __name__ == "__main__":
    sys.exit(main())
