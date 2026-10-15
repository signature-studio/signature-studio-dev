#!/usr/bin/env python3
"""SR-44 #2175: root 関数 (例: getState slot 7 `0x1800c6090`) の direct call / tail jmp 閉包 C と、
target (例: slot 17 `0x1800c9680`・Splice 生成 `0x180498090`) の direct 逆閉包 R を全 .text で求める (静的)。
併せて、C 内の間接 call の形と宛先の定義元、R の関数ポインタ (.rdata/.data の 8 byte スロット) の vtable head と index、
vtable head を rip 相対で指す箇所 (ctor 候補) を出す。
限界: 間接 call の宛先は解決しない。C の外へ出る間接 call は「宛先未解決」として数える (非到達の証明にはならない)。
  --offset <hex>: そのオブジェクト offset を [reg+off] で読む/書く命令を全 .text から列挙する (demo bit 0x22792 の参照関数との対照つき)。
usage: slot_reach.py <pe> <root_va_hex> [--target <va_hex>]... [--vtable-head <va_hex>]... [--offset <hex>]...
"""
import bisect
import re
import struct
import sys
from collections import Counter, defaultdict, deque

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

args = sys.argv[1:]
pe_path = args[0]
root = int(args[1], 16)
targets = []
heads = []
offsets = []
i = 2
while i < len(args):
    if args[i] == "--target":
        targets.append(int(args[i + 1], 16))
    elif args[i] == "--vtable-head":
        heads.append(int(args[i + 1], 16))
    elif args[i] == "--offset":
        offsets.append(int(args[i + 1], 16))
    else:
        raise SystemExit(f"unknown arg {args[i]}")
    i += 2

pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


text = sec(b".text")
t_base = IMG + text.VirtualAddress
t_end = t_base + text.Misc_VirtualSize
code = text.get_data()
pdata = sec(b".pdata")
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for k in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, k)
    if b == 0:
        break
    funcs.append((IMG + b, IMG + e))
funcs.sort()
starts = [f[0] for f in funcs]
start_set = set(starts)


def func_range(va):
    k = bisect.bisect_right(starts, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k]
    return None


md = Cs(CS_ARCH_X86, CS_MODE_64)
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
mem_re = re.compile(r"^qword ptr \[(r[a-z0-9]+)(?: \+ (0x[0-9a-f]+))?\]$")
REG_RE = re.compile(r"^(r[a-z0-9]+)$")
WRITE = {"mov", "movabs", "lea", "movzx", "movsxd", "movsx", "xchg", "pop", "cmove", "cmovne",
         "add", "sub", "xor", "and", "or", "shl", "shr", "sar", "imul", "neg", "not", "inc", "dec"}

fwd = defaultdict(set)
rev = defaultdict(set)
ind = defaultdict(list)  # f -> [(va, kind, reg, disp, op, src)]
rip_refs = defaultdict(list)  # 参照先 VA -> [(命令 VA, 所属関数)]
off_hits = defaultdict(list)  # offset -> [(va, 関数, W/R, 命令)]
demo_fns = set()
for lo, hi in funcs:
    ins_list = list(md.disasm(code[lo - t_base:hi - t_base], lo))
    for idx, ins in enumerate(ins_list):
        for o in [0x22792] + offsets:
            if re.search(rf"\+ {o:#x}\]", ins.op_str):
                if o == 0x22792:
                    demo_fns.add(lo)
                if o in offsets:
                    rw = "W" if ins.mnemonic.startswith("mov") and ins.op_str.split(",")[0].strip().endswith("]") else "R"
                    off_hits[o].append((ins.address, lo, rw, f"{ins.mnemonic} {ins.op_str}"))
        m = rip_re.search(ins.op_str)
        if m:
            ea = ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            rip_refs[ea].append((ins.address, lo))
        if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
            try:
                tgt = int(ins.op_str, 16)
            except ValueError:
                continue
            if tgt in start_set and tgt != lo:
                fwd[lo].add(tgt)
                rev[tgt].add(lo)
            continue
        if ins.mnemonic != "call":
            continue
        op = ins.op_str.strip()
        if "rip" in op:
            ind[lo].append((ins.address, "rip-import", None, None, op, "-"))
            continue
        mm = mem_re.match(op)
        if mm:
            disp = int(mm.group(2), 16) if mm.group(2) else 0
            ind[lo].append((ins.address, "mem", mm.group(1), disp, op, "-"))
            continue
        if REG_RE.match(op):
            src = "entry"
            for j in range(idx - 1, -1, -1):
                p = ins_list[j]
                if p.mnemonic == "call":
                    src = "call-ret"
                    break
                if p.mnemonic in ("cmp", "test", "ret", "jmp") or p.mnemonic.startswith("j"):
                    continue
                parts = [x.strip() for x in p.op_str.split(", ", 1)]
                if parts[0] == op and p.mnemonic in WRITE:
                    src = p.mnemonic + " " + p.op_str
                    break
                if p.mnemonic == "pop" and parts[0] == op:
                    src = "pop"
                    break
            src = re.sub(r"0x[0-9a-f]+", "N", src)
            ind[lo].append((ins.address, "reg", op, None, op, src))
            continue
        ind[lo].append((ins.address, "stack", None, None, op, "stack-slot"))


def closure(seeds, edges):
    seen = set(seeds)
    q = deque(seeds)
    while q:
        f = q.popleft()
        for g in edges.get(f, ()):
            if g not in seen:
                seen.add(g)
                q.append(g)
    return seen


C = closure([root], fwd)
print(f"root {root:#x}: direct closure C = {len(C)} funcs (call / tail jmp to function starts)")
for t in targets:
    if t not in C:
        print(f"  target {t:#x}: not in C")
        continue
    # 最短経路 (BFS)
    par = {root: None}
    q = deque([root])
    while q:
        f = q.popleft()
        if f == t:
            break
        for g in fwd.get(f, ()):
            if g not in par:
                par[g] = f
                q.append(g)
    path = []
    cur = t
    while par[cur] is not None:
        path.append(cur)
        cur = par[cur]
    path.append(root)
    print(f"  target {t:#x}: REACHED, path " + " -> ".join(f"{x:#x}" for x in reversed(path)))

for t in targets:
    R = closure([t], rev)
    inter = sorted(C & R)
    print(f"target {t:#x}: direct reverse closure R = {len(R)} funcs; C ∩ R = {len(inter)} {[hex(x) for x in inter[:8]]}")
    for x in sorted(R):
        if x == t:
            continue
        print(f"  R member {x:#x}")

n_ind = Counter()
src_cnt = Counter()
disp_cnt = Counter()
for f in C:
    for va, kind, reg, disp, op, src in ind.get(f, ()):
        n_ind[kind] += 1
        if kind == "mem":
            disp_cnt[disp] += 1
        elif kind == "reg":
            src_cnt[src] += 1
print("indirect call sites in C by form:", dict(n_ind))
print("  [reg+disp] disp histogram in C:", " ".join(f"{d:#x}:{n}" for d, n in sorted(disp_cnt.items())))
print("  register call sources in C:")
for s, n in src_cnt.most_common():
    print(f"    {n:3d}  {s}")
print("  register/stack call sites in C (va in function):")
for f in sorted(C):
    for va, kind, reg, disp, op, src in ind.get(f, ()):
        if kind in ("reg", "stack"):
            print(f"    {va:#x} in {f:#x}: call {op}  <- {src}")

total88 = sum(1 for f in funcs for va, kind, reg, disp, op, src in ind.get(f[0], ()) if kind == "mem" and disp == 0x88)
in_c88 = sum(1 for f in C for va, kind, reg, disp, op, src in ind.get(f, ()) if kind == "mem" and disp == 0x88)
print(f"call [reg+0x88] sites: whole .text {total88}, in C {in_c88}")

rd = sec(b".rdata")
rraw = rd.get_data()
rbase = IMG + rd.VirtualAddress
text_lo, text_hi = t_base, t_end


def rval(va):
    off = va - rbase
    if off < 0 or off + 8 > len(rraw):
        return None
    return struct.unpack_from("<Q", rraw, off)[0]


def vt_of(slot):
    h = slot
    while True:
        v = rval(h - 8)
        if v is None or not (text_lo <= v < text_hi):
            break
        h -= 8
    return h, (slot - h) // 8


R_ALL = set()
for t in targets:
    R_ALL |= closure([t], rev)
print("address-taken members of R (data slots holding the function start):")
for x in sorted(R_ALL):
    slots = []
    for s in (rd, sec(b".data")):
        raw = s.get_data()
        base = IMG + s.VirtualAddress
        for off in range(0, len(raw) - 7, 8):
            if struct.unpack_from("<Q", raw, off)[0] == x:
                slots.append(base + off)
    if not slots:
        continue
    desc = []
    for s_va in slots:
        if s_va >= rbase and s_va - rbase < len(rraw):
            h, k = vt_of(s_va)
            desc.append(f"slot {s_va:#x} = vtable head {h:#x} index {k}")
        else:
            desc.append(f"slot {s_va:#x} (.data)")
    print(f"  {x:#x}: " + "; ".join(desc))
for h in heads:
    refs = rip_refs.get(h, [])
    print(f"vtable head {h:#x}: rip-relative refs {len(refs)}; in C {sum(1 for a, f in refs if f in C)}; funcs {[hex(f) for a, f in refs][:8]}")

for o in offsets:
    hits = off_hits[o]
    print(f"offset {o:#x}: {len(hits)} memory operand sites in .text, in {len({h[1] for h in hits})} functions")
    for va, f, rw, op in hits:
        print(f"  {rw} {va:#x} in {f:#x} {op}  (demo-bit function: {f in demo_fns})")
print(f"demo-bit 0x22792 operand functions: {sorted(hex(x) for x in demo_fns)}")
