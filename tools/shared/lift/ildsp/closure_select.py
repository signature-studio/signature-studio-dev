#!/usr/bin/env python3
"""ildsp vtable 転送先 1 件の closure (直接 call / 直接 jmp で到達する関数集合) を求める。

usage: closure_select.py <ildsp_vtable.json> <pe> <target_rva_hex> <ranges_out>
  入力: tools/shared/scripts/ildsp_vtable.py の出力 (closure_with_slots.function_starts / direct_call_sites)
        と block24360_PE.bin (命令数の数え直し用)。
  出力: ranges_out に RetDec --select-ranges 用の絶対 VA (`0x180xxxxxx-0x180yyyyyy`, ',' 区切り) を書く。
  標準出力: target の body (.pdata 範囲) の命令数、closure の関数数・命令数・直接 call 辺数。
"""
import sys, json, bisect
import pefile, capstone


def closure(vt, target):
    fs = {}
    for f in vt["closure_with_slots"]["function_starts"]:
        s = int(f["start"], 16)
        fs[s] = max(int(r[1], 16) for r in f["ranges"])
    keys = sorted(fs)

    def owner(addr):
        i = bisect.bisect_right(keys, addr) - 1
        return keys[i] if i >= 0 and addr < fs[keys[i]] else None

    edges = {}
    for site, tgt in vt["closure_with_slots"]["direct_call_sites"]:
        f = owner(int(site, 16))
        if f is not None:
            edges.setdefault(f, set()).add(int(tgt, 16))
    seen, todo = set(), [target]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        todo.extend(edges.get(f, ()))
    ranges = {f: fs.get(f, f) for f in seen}
    return sorted(seen), ranges, edges


def main():
    vt = json.load(open(sys.argv[1]))
    pe = pefile.PE(sys.argv[2], fast_load=True)
    img = pe.get_memory_mapped_image()
    base = int(vt["image_base"], 16)
    target = int(sys.argv[3], 16)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def ninsn(s, e):
        return sum(1 for _ in md.disasm(img[s:e], s))

    fns, ranges, edges = closure(vt, target)
    body_end = ranges[target]
    print("target=0x%x body=0x%x-0x%x body_insn=%d" % (target, target, body_end, ninsn(target, body_end)))
    print("closure functions=%d insn=%d direct_call_edges=%d" % (
        len(fns), sum(ninsn(f, ranges[f]) for f in fns), sum(len(edges.get(f, ())) for f in fns)))
    spans = ",".join("0x%x-0x%x" % (base + f, base + ranges[f]) for f in fns)
    open(sys.argv[4], "w").write(spans + "\n")


if __name__ == "__main__":
    main()
