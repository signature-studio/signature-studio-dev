#!/usr/bin/env python3
"""FLEngine PE (block00031_PE.bin) の .text を線形走査し、直接 call (E8 rel32) だけで関数の前進閉包を調べる (PY-85 / #2668 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_callgraph.py func <VA(16進)> [...]
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_callgraph.py fwd <根 VA csv> <標的 VA csv> [深さ]
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_callgraph.py callers <標的 VA csv> [根 VA csv [深さ]]
  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_callgraph.py around <開始 VA> <終了 VA>

- func: VA の所属関数の先頭を推定する (直前が int3 パディングの命令を関数先頭とみなす)。
- fwd: 根から直接 call で前進し、標的関数へ至る経路を列挙する。間接 call (call reg / call [mem]) は辿らない。
  閉包内の間接 call 箇所数も出力する (静的に解決できない枝の大きさ)。
- callers: 標的 VA への直接 call (E8) の箇所と、それを含む関数 (所属関数の推定) の数を出す。
  根 VA を渡すと、各箇所の所属関数が根からの閉包 (fwd と同じ深さ) に入るかも出す。
- around: 区間内の命令を逆アセンブルする。
- --callee-starts (fwd・callers・func に付ける): 直接 call の先も関数先頭とみなす。CC パディングだけでは
  先頭を検出できない関数の内側を誤帰属しないための補正 (閉包の頑健性の確認用)。

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin' (展開先で実行)
"""
import bisect
import collections
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")


def load():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    n = min(text.Misc_VirtualSize, text.SizeOfRawData)
    va0 = pe.OPTIONAL_HEADER.ImageBase + text.VirtualAddress
    data = raw[text.PointerToRawData:text.PointerToRawData + n]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    insns = []
    off = 0
    while off < n:
        ins = next(md.disasm(data[off:off + 16], va0 + off), None)
        if ins is None:
            off += 1
            continue
        insns.append((ins.address, ins.mnemonic, ins.op_str))
        off += ins.size
    return insns


def function_starts(insns, callee_starts=False):
    starts = []
    prev = None
    for a, m, _ in insns:
        if prev is not None and prev == "int3" and m != "int3":
            starts.append(a)
        prev = m
    if callee_starts:
        known = {a for a, _, _ in insns}
        starts += [int(o, 16) for _, m, o in insns
                   if m == "call" and o.startswith("0x") and int(o, 16) in known]
        starts = sorted(set(starts))
    return starts


def walk(roots, calls_of, targets, depth_max):
    parent = {r: None for r in roots}
    hits = []
    frontier = list(roots)
    depth = 0
    while frontier and depth < depth_max:
        nxt = []
        for f in frontier:
            for t in sorted(calls_of.get(f, ())):
                if t in parent:
                    continue
                parent[t] = f
                nxt.append(t)
                if t in targets:
                    path = [t]
                    while parent[path[-1]] is not None:
                        path.append(parent[path[-1]])
                    hits.append(path)
        frontier = nxt
        depth += 1
    return parent, hits


def main():
    callee_starts = "--callee-starts" in sys.argv
    sys.argv = [x for x in sys.argv if x != "--callee-starts"]
    mode = sys.argv[1]
    insns = load()
    starts = function_starts(insns, callee_starts)

    def func_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return starts[i] if i >= 0 else None

    calls_of = collections.defaultdict(set)
    sites = collections.defaultdict(list)
    indirect = collections.Counter()
    for a, m, o in insns:
        if m != "call":
            continue
        f = func_of(a)
        if o.startswith("0x"):
            sites[int(o, 16)].append(a)
            if f is not None:
                calls_of[f].add(int(o, 16))
        elif f is not None:
            indirect[f] += 1

    if mode == "func":
        for x in sys.argv[2:]:
            f = func_of(int(x, 16))
            print(f"{x} -> func {hex(f) if f is not None else None}")
    elif mode == "around":
        lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
        for a, m, o in insns:
            if lo <= a <= hi:
                print(hex(a), m, o)
    elif mode == "fwd":
        roots = [int(x, 16) for x in sys.argv[2].split(",")]
        targets = {int(x, 16) for x in sys.argv[3].split(",")}
        depth_max = int(sys.argv[4]) if len(sys.argv) > 4 else 60
        parent, hits = walk(roots, calls_of, targets, depth_max)
        for path in hits:
            print("hit: " + " <- ".join(hex(x) for x in path))
        print(f"closure funcs {len(parent)} (depth <= {depth_max})")
        print(f"indirect call sites in closure {sum(indirect[f] for f in parent)}")
        if not any(t in parent for t in targets):
            print("no target reached")
    elif mode == "callers":
        targets = [int(x, 16) for x in sys.argv[2].split(",")]
        closure = None
        if len(sys.argv) > 3:
            roots = [int(x, 16) for x in sys.argv[3].split(",")]
            depth_max = int(sys.argv[4]) if len(sys.argv) > 4 else 60
            closure, _ = walk(roots, calls_of, set(), depth_max)
        for t in targets:
            cs = sites.get(t, [])
            fs = {func_of(a) for a in cs} - {None}
            print(f"{hex(t)}: direct call sites {len(cs)} from functions {len(fs)}")
            for a in cs:
                f = func_of(a)
                mark = "" if closure is None else (" in closure" if f in closure else " outside closure")
                print(f"  {hex(a)} in {hex(f) if f is not None else None}{mark}")
            if closure is not None:
                print(f"  call sites in closure: {sum(1 for a in cs if func_of(a) in closure)}")


if __name__ == "__main__":
    main()
