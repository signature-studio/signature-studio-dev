#!/usr/bin/env python3
"""WaveformColouring_CreateInstance の closure (ildsp_closure.py の 70 関数) のうち、x64c の C に出ていない命令を数える (T-SH-52 / #3216 の REPORT §5-3・§5-4)。

usage: count_unlifted.py PE CLOSURE_JSON LIFT_DIR
  PE           : block24360_PE.bin
  CLOSURE_JSON : ildsp_closure.py --out で出した JSON (export WaveformColouring_CreateInstance の vtable.function_rvas を使う)
  LIFT_DIR     : lift_wc.sh が作った work/lift/ildsp-wc/lift (fle_lifted.c の `/* VA: insn */` 注釈を数える)
出力: closure の命令数・C に出た数・C に無い命令の内訳 (int3 / nop / 非 padding)・直接分岐の先でない非 padding の一覧。
"""
import sys, os, re, json, struct, bisect
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import pefile, capstone
import ildsp_survey as S

PE, CLO, LIFT = sys.argv[1], sys.argv[2], sys.argv[3]
EXPORT = "WaveformColouring_CreateInstance"

pe = pefile.PE(PE, fast_load=True)
image = pe.get_memory_mapped_image()
IB = pe.OPTIONAL_HEADER.ImageBase
text = {s.Name.rstrip(b"\0").decode(): s for s in pe.sections}[".text"]
T_HI = text.VirtualAddress + text.Misc_VirtualSize
exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
funcs = {}
for i in range(exc.Size // 12):
    b, e, _ = struct.unpack_from("<III", image, exc.VirtualAddress + i * 12)
    funcs[b] = e
fn_sorted = sorted(funcs)


def end_of(b):
    if b in funcs:
        return funcs[b]
    i = bisect.bisect_right(fn_sorted, b)
    return fn_sorted[i] if i < len(fn_sorted) else T_HI


md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
row = next(r for r in json.load(open(CLO))["exports"] if r["export"] == EXPORT)
fns = [int(x, 16) for x in row["vtable"]["function_rvas"]]
closure = {}
for f in fns:
    for addr, m, ops in S.sweep(md, bytes(image[f:end_of(f)]), f):
        closure.setdefault(addr, (m, ops))

lifted = set()
for m in re.finditer(r"/\* ([0-9a-f]+): ", open(os.path.join(LIFT, "fle_lifted.c")).read()):
    lifted.add(int(m.group(1), 16) - IB)

missing = {a: v for a, v in closure.items() if a not in lifted}
pads = sorted(a for a, (m, _) in missing.items() if m == "int3")
nops = sorted(a for a, (m, _) in missing.items() if m.startswith("nop"))
nonpad = sorted(a for a, (m, _) in missing.items() if m != "int3" and not m.startswith("nop"))
iat = [a for a in nonpad if missing[a][0] == "jmp" and "[rip" in missing[a][1]]
srcs = {}
for a, (m, o) in closure.items():
    if (m.startswith("j") or m.startswith("call")) and S.is_direct(o):
        srcs.setdefault(int(o, 16), []).append(a)
prev = {}
ordered = sorted(closure)
for i, a in enumerate(ordered[1:], 1):
    prev[a] = closure[ordered[i - 1]][0]
unreached = [a for a in nonpad if a not in iat and a not in srcs]
targeted = [a for a in nonpad if a not in iat and a in srcs]

print(f"[count_unlifted] functions={len(fns)} closure_insns={len(closure)} lifted_in_C={len(lifted)} "
      f"C_not_in_closure={len(lifted - set(closure))} missing={len(missing)}")
print(f"[count_unlifted] missing: int3={len(pads)} nop={len(nops)} nonpad={len(nonpad)} (IAT thunk jmp [rip+IAT]={len(iat)} {' '.join(hex(a) for a in iat)})")
print(f"[count_unlifted] nonpad not a direct branch target (excl. IAT thunk) = {len(unreached)}")
for a in unreached:
    m, o = missing[a]
    print(f"  {a:#x}: {m} {o}   (prev: {prev.get(a, '-')})")
print(f"[count_unlifted] nonpad that is a direct branch target (excl. IAT thunk) = {len(targeted)}")
for a in targeted:
    m, o = missing[a]
    print(f"  {a:#x}: {m} {o}   (direct from: {', '.join(hex(s) + ('(in C)' if s in lifted else '(not in C)') for s in srcs[a])})")
