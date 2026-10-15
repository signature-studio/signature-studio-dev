#!/usr/bin/env python3
"""GeneralPitchShifter_CreateInstance (entry 0x1aa290) 単独 closure の関数範囲を出す (T-SH-62 #3300)。

usage: ci_ranges.py <block24360_PE.bin> <out.json>
辿り方は tools/shared/scripts/ildsp_closure.py の closure() と同じ (直接 call と .text 内の直接 jmp を辿る。
.pdata の無い先は次の .pdata 先頭までを範囲とする近似)。entry_only の 36 関数・961 命令と一致することを確認する。
出力 JSON: image_base / functions (RVA・範囲・命令数) / ranges_va (RetDec --select-ranges の VA 形式) /
outside_targets (範囲内の直接分岐 (call/jmp/jcc) の飛び先のうち、範囲に含まれない .text 内の番地。closure は jcc を辿らないので取りこぼしが出る)。
"""
import sys, os, struct, bisect, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import pefile, capstone
import ildsp_survey as S

ENTRY = 0x1aa290


def main():
    pe = pefile.PE(sys.argv[1], fast_load=True)
    image = pe.get_memory_mapped_image()
    ib = pe.OPTIONAL_HEADER.ImageBase
    text = {s.Name.rstrip(b"\0").decode(): s for s in pe.sections}[".text"]
    t_lo = text.VirtualAddress
    t_hi = t_lo + text.Misc_VirtualSize
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
    funcs = {}
    for i in range(exc.Size // 12):
        b, e, _ = struct.unpack_from("<III", image, exc.VirtualAddress + i * 12)
        funcs[b] = e
    fn_sorted = sorted(funcs)

    def owner(t):
        i = bisect.bisect_right(fn_sorted, t) - 1
        if i >= 0 and fn_sorted[i] <= t < funcs[fn_sorted[i]]:
            return fn_sorted[i]
        return None

    def end_of(b):
        if b in funcs:
            return funcs[b]
        i = bisect.bisect_right(fn_sorted, b)
        return fn_sorted[i] if i < len(fn_sorted) else t_hi

    fcache = {}

    def func_insns(b):
        if b not in fcache:
            fcache[b] = S.sweep(md, bytes(image[b:end_of(b)]), b)
        return fcache[b]

    seen, stack = set(), [ENTRY]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        for addr, m, ops in func_insns(f):
            if (m.startswith("call") or m == "jmp") and S.is_direct(ops):
                t = int(ops, 16)
                if t_lo <= t < t_hi and (m.startswith("call") or not (f <= t < end_of(f))):
                    stack.append(owner(t) or t)

    insns = {}
    for f in seen:
        for addr, m, ops in func_insns(f):
            insns.setdefault(addr, (m, ops))
    indirect = sum(1 for m, ops in insns.values() if m.startswith("call") and not S.is_direct(ops))
    outside = [{"to": f"{int(ops, 16):#x}", "from": f"{addr:#x}", "mnem": m}
               for addr, (m, ops) in sorted(insns.items())
               if (m.startswith("call") or m.startswith("j")) and S.is_direct(ops)
               and t_lo <= int(ops, 16) < t_hi and int(ops, 16) not in insns]
    rows = [{"rva": f"{b:#x}", "end": f"{end_of(b):#x}", "pdata": b in funcs} for b in sorted(seen)]
    ranges_va = [f"{ib + b:#x}-{ib + end_of(b):#x}" for b in sorted(seen)]
    out = {"image_base": ib, "entry": f"{ENTRY:#x}", "functions": len(seen), "instructions": len(insns),
           "indirect_calls": indirect, "rows": rows, "ranges_va": ranges_va, "outside_targets": outside}
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print(f"[ci_ranges] functions={len(seen)} instructions={len(insns)} indirect_calls={indirect} "
          f"pdata={sum(r['pdata'] for r in rows)} -> {sys.argv[2]}")
    if (len(seen), len(insns), indirect) != (36, 961, 10):
        print("[ci_ranges] FAIL: ildsp_closure.py の entry_only (36 関数・961 命令・間接 call 10) と一致しない")
        sys.exit(1)


if __name__ == "__main__":
    main()
