#!/usr/bin/env python3
"""SR-79 #4610: レジスタ値の間接 call (`call reg`) と `call [rsp+disp]` の宛先を、定義元まで遡って解決する。

手順:
  1. `call reg` の reg を、直前の命令列を後ろ向きに辿って定義元に当てる。
     lea rip (コード/データ VA) と、`mov reg, qword ptr [rip+X]` (データ先の値)、
     `mov reg, [reg2+off]` (reg2 を再帰的に解決し、データ先の値を読む) を解決する。
     それ以外の定義・呼出し後の値・引数由来の値は未解決とする。
  2. `call qword ptr [rsp+disp]` は、同じ disp へ直前に書かれた値を解決する。
  3. 解決できた宛先が R (target の direct 逆閉包) に当たるかを見る。
  4. 未解決サイトのうち閉包 C (root から direct call/jmp で到達する関数) 内のものを、
     ポインタの供給元 (vtable 読み・rip 読み・引数/スタック・その他) に分類して出す。
  5. demo bit 関数 (`0x22792` を参照する関数) と C の交わりを出す。

usage: reg_call_resolve.py <pe> <target_va_hex> <root_va_hex>
限界: 引数由来・呼出し後の volatile レジスタ・スタック引数は未解決として数える。
`resolve()` は分岐命令 (j*) とラベルを無視し、直前の 1 経路だけを後ろ向きに辿る。分岐の合流点では
他経路の定義を見ないため、単一の宛先を返す (例: `mov rax, A; jne L; mov rax, B; L: call rax` は B のみ)。
したがって『解決』の件数には合流を跨いで決めた宛先が含まれる。
`,` を含まない 1 オペランド命令 (inc/dec/neg/not/cdqe など) は読み飛ばすため、対象レジスタを変えるこれらの命令を
越えて 1 つ前の定義に届くことがある。
未解決の供給元の分類は『R の関数アドレスは rip 参照 (lea/mov) か vtable スロット (disp 0x28・0x60) からしか
コードに現れない』という前提に依存する。この前提はこのスクリプトでは検証していない (未検証)。
"""
import re
import struct
import sys
from collections import Counter, defaultdict, deque

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe_path, target, root = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
DISPS = {0x28, 0x60}
pe = pefile.PE(pe_path)
data = open(pe_path, "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
sec = {s.Name.rstrip(b"\0"): s for s in pe.sections}
text = sec[b".text"]
tb = IMG + text.VirtualAddress
raw = text.get_data()
pdata = sec[b".pdata"]
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b:
        funcs.append((IMG + b, IMG + e))
sset = {f[0] for f in funcs}
fin = dict(funcs)
secs = [(IMG + s.VirtualAddress, s.get_data()) for s in pe.sections if s.SizeOfRawData]
cs = Cs(CS_ARCH_X86, CS_MODE_64)
rip_re = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
mem_re = re.compile(r"^qword ptr \[(r[a-z0-9]+|rsp|rbp)(?: \+ (0x[0-9a-f]+|[0-9]+))?\]$")
reg_re = re.compile(r"^(r[a-z0-9]+|e[a-z0-9]+)$")
SKIP = {"cmp", "test", "bt", "ucomiss", "ucomisd", "comiss", "comisd"}
ALIAS32 = {"e" + x: "r" + x for x in ["ax", "bx", "cx", "dx", "si", "di", "bp", "sp"]}


def canon(n):
    return ALIAS32.get(n, n)


def qword_at(va):
    for base, sraw in secs:
        if base <= va and va + 8 <= base + len(sraw):
            return struct.unpack_from("<Q", sraw, va - base)[0]
    return None


def ripea(ins, src):
    m = rip_re.search(src)
    if not m:
        return None
    return ins.address + ins.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)


VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}


def resolve(insns, idx, reg, depth=0):
    """insns[idx] より前で reg の定義元を探し、値の集合を返す。未解決は None。"""
    if depth > 3:
        return None
    r = canon(reg)
    for j in range(idx - 1, -1, -1):
        w = insns[j]
        if w.mnemonic == "call":
            if r in VOLATILE:
                return None
            continue
        if w.mnemonic in SKIP or w.mnemonic.startswith("j") or w.mnemonic == "ret":
            continue
        if "," not in w.op_str:
            if w.mnemonic == "pop" and canon(w.op_str) == r:
                return None
            continue
        d, s = [x.strip() for x in w.op_str.split(",", 1)]
        if canon(d) != r:
            continue
        if w.mnemonic == "lea":
            ea = ripea(w, s)
            return {ea} if ea is not None else None
        if w.mnemonic == "mov":
            if s.startswith("qword ptr") and "rip" in s:
                ea = ripea(w, s)
                v = qword_at(ea) if ea is not None else None
                return {v} if v is not None else None
            mm = mem_re.match(s)
            if mm and mm.group(1) not in ("rsp", "rbp"):
                base = resolve(insns, j, mm.group(1), depth + 1)
                if not base:
                    return None
                off = int(mm.group(2), 0) if mm.group(2) else 0
                out = set()
                for b in base:
                    v = qword_at(b + off)
                    if v is None:
                        return None
                    out.add(v)
                return out
            if reg_re.match(s):
                return resolve(insns, j, s, depth + 1)
            return None
        return None
    return None


def provenance(insns, i, r):
    """未解決 call reg の供給元を分類する。"""
    for j in range(i - 1, -1, -1):
        w = insns[j]
        if w.mnemonic == "call":
            return "after-call"
        if w.mnemonic in SKIP or w.mnemonic.startswith("j") or "," not in w.op_str:
            if w.mnemonic == "pop" and canon(w.op_str) == r:
                return "stack-pop"
            continue
        d, s = [x.strip() for x in w.op_str.split(",", 1)]
        if canon(d) != r:
            continue
        if w.mnemonic == "mov" and mem_re.match(s):
            mm = mem_re.match(s)
            if mm.group(1) in ("rsp", "rbp"):
                return "stack-slot"
            disp = int(mm.group(2), 0) if mm.group(2) else 0
            return f"vptr-load[+{disp:#x}]" if disp in DISPS else "load[reg+other]"
        if w.mnemonic == "mov" and "rip" in s:
            return "global-load"
        if w.mnemonic == "lea":
            return "lea"
        if w.mnemonic == "mov" and reg_re.match(s):
            return "regcopy"
        return "other:" + w.mnemonic
    return "entry-arg"


fwd = defaultdict(set)
rev = defaultdict(set)
demo = set()
sites = Counter()
resolved_hits = []
unres = []  # (VA, 所属関数, op, 供給元)
for lo, hi in funcs:
    insns = list(cs.disasm(raw[lo - tb:hi - tb], lo))
    for ins in insns:
        if "+ 0x22792]" in ins.op_str:
            demo.add(lo)
        if ins.mnemonic in ("jmp", "call") and ins.op_str.startswith("0x"):
            t = int(ins.op_str, 16)
            if t in sset and t != lo:
                fwd[lo].add(t)
                rev[t].add(lo)
    for i, ins in enumerate(insns):
        if ins.mnemonic != "call":
            continue
        op = ins.op_str
        if op.startswith("0x"):
            continue
        if reg_re.match(op):
            sites["call reg"] += 1
            tg = resolve(insns, i, op)
            if tg:
                resolved_hits.append((ins.address, lo, tg))
                for t in tg:
                    if t in sset and t != lo:
                        fwd[lo].add(t)
                        rev[t].add(lo)
            else:
                unres.append((ins.address, lo, op, provenance(insns, i, canon(op))))
        elif op.startswith("qword ptr [rsp"):
            sites["call [rsp+disp]"] += 1
            m = re.match(r"qword ptr \[rsp \+ (0x[0-9a-f]+)\]", op)
            tg = None
            for j in range(i - 1, -1, -1):
                w = insns[j]
                if w.mnemonic == "call":
                    break
                if w.mnemonic == "mov" and w.op_str.startswith(f"qword ptr [rsp + {m.group(1)}]"):
                    srcw = w.op_str.split(",", 1)[1].strip()
                    if reg_re.match(srcw):
                        tg = resolve(insns, j + 1, srcw)
                    break
            if tg:
                resolved_hits.append((ins.address, lo, tg))
                for t in tg:
                    if t in sset and t != lo:
                        fwd[lo].add(t)
                        rev[t].add(lo)
            else:
                unres.append((ins.address, lo, op, "stack-arg"))


def closure(seed, edges):
    seen = {seed}
    q = deque([seed])
    while q:
        f = q.popleft()
        for g in edges.get(f, ()):
            if g not in seen:
                seen.add(g)
                q.append(g)
    return seen


R = closure(target, rev)
C = closure(root, fwd)
print(f"R={len(R)} C={len(C)} C∩R={len(C & R)}")
print("sites: " + " ".join(f"{k}={v}" for k, v in sites.items()) + f" | resolved={len(resolved_hits)} unresolved={len(unres)}")
hit = [(a, f, t) for a, f, t in resolved_hits if t & R]
print(f"resolved sites hitting R: {len(hit)}")
inC = [(a, f, op, p) for a, f, op, p in unres if f in C]
print(f"unresolved sites in C: {len(inC)} in {len({f for _, f, _, _ in inC})} functions")
for k, v in Counter(p for *_, p in inC).most_common():
    print(f"  {k}: {v}")
print(f"demo-bit functions: {sorted(hex(x) for x in demo)}  demo∩C={len(demo & C)}")
