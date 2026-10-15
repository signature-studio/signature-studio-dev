#!/usr/bin/env python3
"""ildsp vtable 転送先 1 件の closure (直接 call / 関数外への直接 jmp で到達する関数集合) を求める。

usage: closure_select.py <ildsp_vtable.json> <pe> <target_rva_hex> <ranges_out>
  入力: tools/shared/scripts/ildsp_vtable.py の出力 (closure_with_slots の function_starts と
        direct_call_sites / direct_jmp_sites) と block24360_PE.bin (命令数の数え直し用)。
  出力: ranges_out に RetDec --select-ranges 用の絶対 VA (`0x180xxxxxx-0x180yyyyyy`, ',' 区切り) を書く。
  標準出力: target の body (.pdata 範囲) の命令数、closure の関数数・命令数・直接 call / jmp 辺数、
        閉包内の間接 call / 間接 jmp の箇所。
"""
import sys, json, bisect
import pefile, capstone


def closure(vt, target):
    cw = vt["closure_with_slots"]
    fs = {}
    for f in cw["function_starts"]:
        fs[int(f["start"], 16)] = [(int(r[0], 16), int(r[1], 16)) for r in f["ranges"]]
    spans = sorted((lo, hi, s) for s, rs in fs.items() for lo, hi in rs)
    los = [sp[0] for sp in spans]

    def owner(addr):
        i = bisect.bisect_right(los, addr) - 1
        return spans[i][2] if i >= 0 and addr < spans[i][1] else None

    cedges, jedges, unresolved = {}, {}, 0
    for key, edges in (("direct_call_sites", cedges), ("direct_jmp_sites", jedges)):
        for site, tgt in cw.get(key, []):
            f, t = owner(int(site, 16)), owner(int(tgt, 16))
            if f is None:
                continue
            if t is None:
                unresolved += 1
                continue
            edges.setdefault(f, set()).add(t)
    seen, todo = set(), [owner(target)]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        todo.extend(cedges.get(f, ()))
        todo.extend(jedges.get(f, ()))
    ends = {f: max(hi for _, hi in fs[f]) for f in seen}
    ind = {
        "calls": [c for c in cw["indirect_calls"] if int(c["in_func"], 16) in seen],
        "jmps": [j for j in cw["indirect_jmps"] if int(j["in_func"], 16) in seen],
    }
    return sorted(seen), ends, cedges, jedges, unresolved, ind


def main():
    vt = json.load(open(sys.argv[1]))
    pe = pefile.PE(sys.argv[2], fast_load=True)
    img = pe.get_memory_mapped_image()
    base = int(vt["image_base"], 16)
    target = int(sys.argv[3], 16)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def ninsn(s, e):
        return sum(1 for _ in md.disasm(img[s:e], s))

    fns, ends, cedges, jedges, unresolved, ind = closure(vt, target)
    body_end = ends[target]
    print("target=0x%x body=0x%x-0x%x body_insn=%d" % (target, target, body_end, ninsn(target, body_end)))
    print("closure functions=%d insn=%d direct_call_edges=%d direct_jmp_edges=%d unresolved_edges=%d" % (
        len(fns), sum(ninsn(f, ends[f]) for f in fns),
        sum(len(cedges.get(f, ())) for f in fns), sum(len(jedges.get(f, ())) for f in fns), unresolved))
    print("closure indirect_calls=%d indirect_jmps=%d" % (len(ind["calls"]), len(ind["jmps"])))
    for c in ind["calls"]:
        print("  indirect call %s in %s: %s" % (c["site"], c["in_func"], c["op"]))
    for j in ind["jmps"]:
        print("  indirect jmp %s in %s: %s" % (j["site"], j["in_func"], j["op"]))
    spans = ",".join("0x%x-0x%x" % (base + f, base + ends[f]) for f in fns)
    open(sys.argv[4], "w").write(spans + "\n")


if __name__ == "__main__":
    main()
