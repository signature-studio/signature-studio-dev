#!/usr/bin/env python3
"""ildsp (block24360_PE.bin) の export ごとに、CreateInstance が置く vtable を辿って実体の到達集合を数える。

usage: ildsp_vtable.py [PE] [--out <json>]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
  既定 out: tools/shared/work/raw/ildsp_vtable.json (gitignore)

手順:
  1. CreateInstance (.pdata 境界) の中で、`lea reg, [rip+X]` の直後に `mov qword ptr [reg2], reg` と格納する
     最初の箇所を探し、X を vtable の RVA とする (wrapper object の vtable)。
  2. vtable の先頭から、.text 内を指すポインタを slot として数える (最初に .text 外を指す所で打ち切り)。
  3. slot の先が thunk (`mov rcx, [rcx+8]` から始まり、直接 `jmp` で終わる 4 命令以下) なら、jmp 先を実体とする。
  4. 実体から直接 call / 直接 tail jmp を辿った到達集合を、slot の和集合で数える。
     間接 call は辿らず件数のみ。直接先が .pdata に無い場合 (leaf 関数など) は、その先頭を関数とし、
     次の .pdata 先頭までを範囲とする近似で辿る (ildsp_survey.py の closure は .pdata の無い先を捨てるため、
     その数値は下限になる)。同一関数の範囲内の jmp (内部分岐) は関数として数えない。
  5. 命令数・SIMD 比・間接 call 数は到達関数の命令開始アドレスの和集合で数える (重なる範囲の二重計上を避ける)。
     集計は CreateInstance の closure と slot 先 closure の和集合。比較用に CreateInstance 単体の closure も出す。
"""
import sys, os, re, json, argparse, struct, bisect
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR
import pefile, capstone
import ildsp_survey as S

RIP_RE = re.compile(r"\[rip \+ (0x[0-9a-f]+)\]")
STORE_RE = re.compile(r"qword ptr \[(\w+)\], (\w+)$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    ap.add_argument("--out", default=os.path.join(S.ROOT, "work", "raw", "ildsp_vtable.json"))
    a = ap.parse_args()

    pe = pefile.PE(a.pe, fast_load=True)
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

    def find_vtable(entry):
        f = owner(entry) or entry
        tails = [owner(int(o, 16)) or int(o, 16) for _, m, o in func_insns(f) if m == "jmp" and S.is_direct(o)]
        for g in [f] + tails:
            vt, site = scan_store(g)
            if vt is not None:
                return vt, site
        return None, None

    def scan_store(f):
        ins = func_insns(f)
        for i in range(len(ins) - 1):
            addr, m, ops = ins[i]
            if m != "lea":
                continue
            mm = RIP_RE.search(ops)
            if not mm:
                continue
            reg = ops.split(",")[0].strip()
            after_lea = ins[i + 1][0]
            for _, nm, nops in ins[i + 1:i + 5]:
                st = STORE_RE.search(nops) if nm == "mov" else None
                if st and st.group(2) == reg:
                    return after_lea + int(mm.group(1), 16), addr
        return None, None

    def vtable_slots(va):
        out = []
        for k in range(256):
            p = struct.unpack_from("<Q", image, va + 8 * k)[0] - ib
            if not (t_lo <= p < t_hi):
                break
            out.append(p)
        return out

    def resolve(rva):
        ins = func_insns(rva)
        if not ins or ins[0][1] != "mov" or ins[0][2] != "rcx, qword ptr [rcx + 8]":
            return rva, False
        for addr, m, ops in ins[1:4]:
            if m == "jmp":
                return (int(ops, 16), True) if S.is_direct(ops) else (rva, False)
            if m == "ret" or m.startswith("j") or m.startswith("call"):
                break
        return rva, False

    def closure(entries):
        seen, stack = set(), list(entries)
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
        return seen

    def stats(seen):
        insns = {}
        for f in seen:
            for addr, m, ops in func_insns(f):
                insns.setdefault(addr, (m, ops))
        simd = dc = ic = 0
        for m, ops in insns.values():
            if S.classify(m, ops) == "simd":
                simd += 1
            if m.startswith("call"):
                if S.is_direct(ops):
                    dc += 1
                else:
                    ic += 1
        ins_n = len(insns)
        return {"functions": len(seen), "nonpdata_functions": sum(1 for f in seen if f not in funcs),
                "instructions": ins_n,
                "simd_ratio": round(simd / max(ins_n, 1), 4),
                "direct_calls": dc, "indirect_calls": ic,
                "indirect_ratio": round(ic / max(dc + ic, 1), 4)}

    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    exp = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
    exports = []
    if exp:
        for s in exp.symbols:
            name = s.name.decode(errors="replace") if s.name else f"#{s.ordinal}"
            exports.append((name, s.address))

    table = []
    for name, rva in sorted(exports):
        vt, site = find_vtable(rva)
        row = {"export": name, "entry_rva": hex(rva)}
        row["entry_only"] = stats(closure([owner(rva) or rva]))
        if vt is None:
            row["vtable"] = None
            table.append(row)
            continue
        slots = vtable_slots(vt)
        targets = []
        thunks = 0
        for k, s in enumerate(slots):
            t, is_thunk = resolve(s)
            thunks += is_thunk
            targets.append({"slot": k, "slot_rva": hex(s), "target_rva": hex(t), "thunk": is_thunk})
        entries = [int(t["target_rva"], 16) for t in targets]
        seen = closure([owner(rva) or rva] + [owner(e) or e for e in entries])
        row["vtable"] = {"rva": hex(vt), "store_site": hex(site), "slots": len(slots), "thunks": thunks,
                         "targets": targets, **stats(seen), "function_rvas": [hex(f) for f in sorted(seen)]}
        table.append(row)

    res = {"pe": a.pe, "exports": table}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)

    print(f"# ildsp vtable closure: {os.path.basename(a.pe)}")
    print("| export | entry | vtable | slots | thunk | 関数数 | 命令数 | SIMD 比 | 間接 call | 間接比 | entry-only 命令数 |")
    print("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in table:
        v = r["vtable"]
        if v is None:
            print(f"| {r['export']} | {r['entry_rva']} | (未検出) | - | - | - | - | - | - | - | {r['entry_only']['instructions']} |")
            continue
        print(f"| {r['export']} | {r['entry_rva']} | {v['rva']} | {v['slots']} | {v['thunks']} | {v['functions']} | "
              f"{v['instructions']} | {v['simd_ratio']:.1%} | {v['indirect_calls']} | {v['indirect_ratio']:.1%} | "
              f"{r['entry_only']['instructions']} |")


if __name__ == "__main__":
    main()
