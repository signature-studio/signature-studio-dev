#!/usr/bin/env python3
"""WaveformColouring closure の未 lift 非 padding 16 件 (REPORT_APPENDIX_3216 §7-4) の到達性を、静的な参照の種類ごとに調べる (T-SH-133 / #5072)。

usage: unlifted_reach.py PE CLOSURE_JSON LIFT_DIR
  PE           : block24360_PE.bin
  CLOSURE_JSON : ildsp_closure.py --out で出した JSON
  LIFT_DIR     : lift_wc.sh が作った work/lift/ildsp-wc/lift
出力: 16 件ごとに、所属関数・直接分岐の元 (.text 全体)・イメージ内の参照 (8 byte 絶対 VA / 4 byte RVA)・rip 相対の参照・
      閉包の間接 jmp/call の集合への含有を出す。判定は REPORT_APPENDIX_3216 §7-4 に書く。
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
T_LO, T_HI = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
funcs = {}
for i in range(exc.Size // 12):
    b, e, _ = struct.unpack_from("<III", image, exc.VirtualAddress + i * 12)
    funcs[b] = e
fn_sorted = sorted(funcs)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def owner(t):
    i = bisect.bisect_right(fn_sorted, t) - 1
    if i >= 0 and fn_sorted[i] <= t < funcs[fn_sorted[i]]:
        return fn_sorted[i]
    return None


def end_of(b):
    if b in funcs:
        return funcs[b]
    i = bisect.bisect_right(fn_sorted, b)
    return fn_sorted[i] if i < len(fn_sorted) else T_HI


row = next(r for r in json.load(open(CLO))["exports"] if r["export"] == EXPORT)
fns = [int(x, 16) for x in row["vtable"]["function_rvas"]]
closure = {}
for f in fns:
    for a, m, o in S.sweep(md, bytes(image[f:end_of(f)]), f):
        closure.setdefault(a, (m, o))

lifted = set()
for m in re.finditer(r"/\* ([0-9a-f]+): ", open(os.path.join(LIFT, "fle_lifted.c")).read()):
    lifted.add(int(m.group(1), 16) - IB)

missing = {a: v for a, v in closure.items() if a not in lifted}
iat = {a for a, (m, o) in missing.items() if m == "jmp" and "[rip" in o}
nonpad = sorted(a for a, (m, _) in missing.items()
                if m != "int3" and not m.startswith("nop") and a not in iat)
direct_tail = {a for a in nonpad if any(
    (m.startswith("j") or m.startswith("call")) and S.is_direct(o) and int(o, 16) == a
    for _, (m, o) in closure.items())}
targets = [a for a in nonpad if a not in direct_tail]
targets += [a for a in nonpad if a in direct_tail]
print(f"[unlifted_reach] closure={len(closure)} lifted_in_C={len(lifted)} missing={len(missing)} "
      f"nonpad(excl IAT)={len(nonpad)} -> {[hex(a) for a in nonpad]}")

text_ins = S.sweep(md, bytes(image[T_LO:T_HI]), T_LO)
direct_src = {a: [] for a in nonpad}
for a, m, o in text_ins:
    if (m.startswith("j") or m.startswith("call")) and S.is_direct(o):
        tg = int(o, 16)
        if tg in direct_src:
            direct_src[tg].append(a)

md2 = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md2.detail = True
rip_hits = {a: [] for a in nonpad}
data = bytes(image[T_LO:T_HI])
k = 0
while k < len(data):
    got = next(iter(md2.disasm(data[k:k + 16], T_LO + k)), None)
    if got is None:
        k += 1
        continue
    for op in got.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            tgt = got.address + got.size + op.mem.disp
            if tgt in rip_hits:
                rip_hits[tgt].append(got.address)
    k += got.size

for a in nonpad:
    f = owner(a)
    m, o = closure[a]
    pa = max((x for x in closure if x < a), default=None)
    va8 = (IB + a).to_bytes(8, "little")
    rva4 = a.to_bytes(4, "little")
    abs8 = []
    i = image.find(va8)
    while i != -1:
        abs8.append(i)
        i = image.find(va8, i + 1)
    rv4 = []
    i = image.find(rva4)
    while i != -1:
        rv4.append(i)
        i = image.find(rva4, i + 1)
    srcs = direct_src[a]
    print(f"{a:#x}: {m} {o} | owner={hex(f) if f else '-'} in_closure_fn={f in fns if f else False}")
    print(f"    direct_src(.text)={[hex(s) for s in srcs[:4]]}{' ...' if len(srcs) > 4 else ''} (n={len(srcs)})"
          f" in_closure_src={sum(1 for s in srcs if s in closure)}")
    print(f"    rip_refs={[hex(x) for x in rip_hits[a]]} abs8={[hex(x) for x in abs8]} rva4={[hex(x) for x in rv4[:6]]}"
          f"{' ...' if len(rv4) > 6 else ''} (n={len(rv4)})")
