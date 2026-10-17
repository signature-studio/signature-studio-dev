#!/usr/bin/env python3
"""SR-79 #4610: レジスタ値の間接 call (`call reg`) と `call [rsp+disp]` の宛先を、定義元まで遡って解決する。

手順:
  1. `call reg` の reg を、制御フロー (fall-through と direct jmp/jcc の逆辺) を全経路で後ろ向きに辿って定義元に当てる。
     全経路の定義が同じ値集合に解決できたときだけ解決とする (1 経路でも未解決なら未解決)。
     lea rip (コード/データ VA)・`mov reg, qword ptr [rip+X]` (データ先の値)・`mov reg, [reg2+off]`
     (reg2 を再帰的に解決し、データ先の値を読む) を解決する。それ以外の定義・呼出し後の volatile・引数由来は未解決。
  2. `call qword ptr [rsp+disp]` は、同じ disp へ各経路で直前に書かれた値を解決する。
  3. 解決できた宛先が R (target の direct 逆閉包) に当たるかを見る。
  4. 未解決サイトのうち閉包 C (root から direct call/jmp で到達する関数) 内のものを、
     ポインタの供給元 (vtable 読み・rip 読み・引数/スタック・その他) に分類して出す。
  5. demo bit 関数 (`0x22792` を参照する関数) と C の交わりを出す。

usage: reg_call_resolve.py <pe> <target_va_hex> <root_va_hex>
限界:
- 引数由来・呼出し後の volatile レジスタ・スタック引数は未解決として数える。
- 間接 jmp を持つ関数では、制御フローの逆辺を確定できないため、その関数内の全サイトを未解決とする。
  ただし型が合う jump table (`jump_table_targets`) の遷移先は逆辺として扱う。他の間接 jmp (pop 後の末尾呼出し等) は未解決のまま。
- 読み出す値は PE ファイル上の初期値。書込み可能な .data の実行時の値は、このスクリプトでは見ていない。
- 書込みは「同じ base レジスタ・同じ disp の別名」を見ない。memory alias は未考慮。
- 供給元の分類 (provenance) は従来どおり直線の後ろ向き走査で、経路は見ていない (分類のみ)。
- `[rsp+disp]` の書込みは、`qword ptr [rsp + disp]` と完全一致する mov 以外の、宛先が `[rsp` を含む命令 (幅の広い書込みを含む)・
  `push`/`pop`・`rsp` 自体への書込みをすべて kill とみなす (保守的)。ただし kill は範囲の重なりを見ないため、無関係な
  `[rsp+disp']` への書込みでも経路が未解決になりうる。
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
NOWRITE = SKIP | {"nop", "push", "endbr64"}
UNCOND = {"jmp", "ret", "ud2", "int3", "hlt"}
IMPL = {"cdqe": ("rax",), "cwde": ("rax",), "cdq": ("rdx",), "cqo": ("rdx",),
        "cpuid": ("rax", "rbx", "rcx", "rdx"), "rdtsc": ("rax", "rdx")}
FAMILY = {}
for _x in "abcd":
    for _n in (f"r{_x}x", f"e{_x}x", f"{_x}x", f"{_x}l", f"{_x}h"):
        FAMILY[_n] = f"r{_x}x"
for _x in ("si", "di", "bp", "sp"):
    for _n in (f"r{_x}", f"e{_x}", _x, f"{_x}l"):
        FAMILY[_n] = f"r{_x}"
for _k in range(8, 16):
    for _n in (f"r{_k}", f"r{_k}d", f"r{_k}w", f"r{_k}b"):
        FAMILY[_n] = f"r{_k}"
VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
LIMIT = 4000


def fam(n):
    return FAMILY.get(n, n)


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


def writes(w, r):
    """命令 w が 64-bit レジスタ family r (rax 等) を書くか。部分レジスタ書込みも書きとみなす。"""
    m = w.mnemonic
    if m in NOWRITE or m.startswith("j") or m in UNCOND or m == "call":
        return False
    if m in IMPL:
        return r in IMPL[m]
    if m.startswith("rep"):
        return r in ("rcx", "rsi", "rdi")
    if m.startswith("lods"):
        return r in ("rax", "rsi")
    ops = [x.strip() for x in w.op_str.split(",")] if w.op_str else []
    if m in ("mul", "imul", "div", "idiv") and len(ops) == 1:
        return r in ("rax", "rdx")
    if m in ("xchg", "xadd", "cmpxchg"):
        return any(fam(o) == r for o in ops)
    if not ops:
        return False
    return fam(ops[0]) == r


def def_value(insns, jt, q, r, depth):
    """命令 q が r を書くとき、書かれる値の集合。直接に解決できないものは None。"""
    w = insns[q]
    if w.mnemonic not in ("mov", "lea"):
        return None
    d, s = [x.strip() for x in w.op_str.split(",", 1)]
    if d != r:
        return None
    if w.mnemonic == "lea":
        ea = ripea(w, s)
        return {ea} if ea is not None else None
    if s.startswith("qword ptr") and "rip" in s:
        ea = ripea(w, s)
        v = qword_at(ea) if ea is not None else None
        return {v} if v is not None else None
    mm = mem_re.match(s)
    if mm:
        if mm.group(1) in ("rsp", "rbp"):
            return None
        base = resolve(insns, jt, q, mm.group(1), depth + 1)
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
        return resolve(insns, jt, q, s, depth + 1)
    return None


JT_MOV = re.compile(r"^(\w+), dword ptr \[(\w+) \+ (\w+)\*4\]$")
JT_CMP = re.compile(r"^(\w+), (0x[0-9a-f]+|[0-9]+)$")
ZX32 = {f"r{x}x": f"e{x}x" for x in "abcd"}
ZX32.update({f"r{x}": f"e{x}" for x in ("si", "di", "bp", "sp")})
ZX32.update({f"r{k}": f"r{k}d" for k in range(8, 16)})


def dword_at(va):
    for base, sraw in secs:
        if base <= va and va + 4 <= base + len(sraw):
            return struct.unpack_from("<i", sraw, va - base)[0]
    return None


def jump_table_targets(insns, k, addr2i):
    """`jmp R` が jump table (lea B,[rip+X]; cmp I,N; ja; movsxd R,[B+I*4]; add R,B; jmp R) なら、
    表の N+1 項の遷移先 (関数内の命令 VA) を返す。型に合わない・遷移先が関数内にない場合は None。"""
    if k < 3 or insns[k - 1].mnemonic != "add":
        return None
    ops = [x.strip() for x in insns[k - 1].op_str.split(",")]
    if len(ops) != 2 or fam(ops[0]) != fam(insns[k].op_str):
        return None
    mv = insns[k - 2]
    m = JT_MOV.match(mv.op_str)
    if mv.mnemonic != "movsxd" or not m or fam(m.group(1)) != fam(ops[0]) or fam(m.group(2)) != fam(ops[1]):
        return None
    idx = fam(m.group(3))
    base = fam(m.group(2))
    lea = None
    for q in range(k - 3, max(-1, k - 12), -1):
        if writes(insns[q], base):
            if insns[q].mnemonic == "lea" and ripea(insns[q], insns[q].op_str.split(",", 1)[1].strip()) is not None:
                lea = insns[q]
            break
    if lea is None:
        return None
    cmp_i = None
    for q in range(k - 3, max(-1, k - 14), -1):
        w = insns[q]
        if w.mnemonic == "cmp":
            c = JT_CMP.match(w.op_str)
            if c and fam(c.group(1)) == idx and q + 1 < len(insns) and insns[q + 1].mnemonic == "ja":
                cmp_i = int(c.group(2), 0)
                break
        if writes(w, idx) and not (w.mnemonic == "mov" and w.op_str == f"{ZX32[idx]}, {ZX32[idx]}"):
            break
    if cmp_i is None:
        return None
    tb_va = ripea(lea, lea.op_str.split(",", 1)[1].strip())
    out = []
    for e in range(cmp_i + 1):
        v = dword_at(tb_va + 4 * e)
        t = None if v is None else tb_va + v
        if t is None or t not in addr2i:
            return None
        out.append(t)
    return out


def preds(insns, jt, q):
    out = list(jt.get(q, ()))
    if q > 0 and insns[q - 1].mnemonic not in UNCOND:
        out.append(q - 1)
    return out


def walk(insns, jt, start, hit):
    """start より前の全経路を後ろ向きに辿る。hit(q) は ("kill"|"def"|"pass", 値 or None)。
    どの経路でも定義に届かない (関数入口・呼出し・未解決) なら None。"""
    stack = preds(insns, jt, start)
    if not stack:
        return None
    seen, out, n = set(), set(), 0
    while stack:
        q = stack.pop()
        if q in seen:
            continue
        seen.add(q)
        n += 1
        if n > LIMIT:
            return None
        kind, val = hit(q)
        if kind == "kill":
            return None
        if kind == "def":
            if val is None:
                return None
            out |= val
            continue
        p = preds(insns, jt, q)
        if not p:
            return None
        stack.extend(p)
    return out or None


def resolve(insns, jt, idx, reg, depth=0):
    """insns[idx] より前の全経路で reg の定義元を探し、値の集合を返す。未解決は None。"""
    if depth > 3:
        return None
    r = fam(reg)

    def hit(q):
        w = insns[q]
        if w.mnemonic == "call":
            return ("kill", None) if r in VOLATILE else ("pass", None)
        if not writes(w, r):
            return ("pass", None)
        return ("def", def_value(insns, jt, q, r, depth))

    return walk(insns, jt, idx, hit)


def provenance(insns, i, r):
    """未解決 call reg の供給元を分類する (直線の後ろ向き走査。分類のみ)。"""
    for j in range(i - 1, -1, -1):
        w = insns[j]
        if w.mnemonic == "call":
            return "after-call"
        if w.mnemonic in SKIP or w.mnemonic.startswith("j") or "," not in w.op_str:
            if w.mnemonic == "pop" and fam(w.op_str) == r:
                return "stack-pop"
            continue
        d, s = [x.strip() for x in w.op_str.split(",", 1)]
        if fam(d) != r:
            continue
        if w.mnemonic == "mov" and "rip" in s:
            return "global-load"
        if w.mnemonic == "mov" and mem_re.match(s):
            mm = mem_re.match(s)
            if mm.group(1) in ("rsp", "rbp"):
                return "stack-slot"
            disp = int(mm.group(2), 0) if mm.group(2) else 0
            return f"vptr-load[+{disp:#x}]" if disp in DISPS else "load[reg+other]"
        if w.mnemonic == "lea":
            return "lea"
        if w.mnemonic == "mov" and reg_re.match(s):
            return "regcopy"
        return "other:" + w.mnemonic
    return "entry-arg"


def stack_slot_value(insns, jt, i, disp):
    slot = f"qword ptr [rsp + {disp}]"

    def hit(q):
        w = insns[q]
        if w.mnemonic == "call":
            return ("kill", None)
        ops = [x.strip() for x in w.op_str.split(",", 1)]
        if w.mnemonic == "mov" and ops[0] == slot:
            if len(ops) < 2 or not reg_re.match(ops[1]):
                return ("kill", None)
            return ("def", resolve(insns, jt, q, ops[1]))
        if w.mnemonic in ("push", "pop") or (ops[0] == "rsp" and w.mnemonic not in NOWRITE):
            return ("kill", None)
        if "[rsp" in ops[0] and w.mnemonic not in NOWRITE and not w.mnemonic.startswith("j"):
            return ("kill", None)
        return ("pass", None)

    return walk(insns, jt, i, hit)


fwd = defaultdict(set)
rev = defaultdict(set)
demo = set()
sites = Counter()
resolved_hits = []
unres = []  # (VA, 所属関数, op, 供給元)
indirect_fns = 0
jt_resolved = 0
for lo, hi in funcs:
    insns = list(cs.disasm(raw[lo - tb:hi - tb], lo))
    addr2i = {ins.address: k for k, ins in enumerate(insns)}
    jt = defaultdict(list)
    indirect = False
    for k, ins in enumerate(insns):
        if "+ 0x22792]" in ins.op_str:
            demo.add(lo)
        if ins.mnemonic.startswith("j") and ins.op_str.startswith("0x"):
            t = int(ins.op_str, 16)
            if t in addr2i:
                jt[addr2i[t]].append(k)
        if ins.mnemonic == "jmp" and not ins.op_str.startswith("0x"):
            tgs = jump_table_targets(insns, k, addr2i)
            if tgs is None:
                indirect = True
            else:
                for t in tgs:
                    jt[addr2i[t]].append(k)
                jt_resolved += 1
        if ins.mnemonic in ("jmp", "call") and ins.op_str.startswith("0x"):
            t = int(ins.op_str, 16)
            if t in sset and t != lo:
                fwd[lo].add(t)
                rev[t].add(lo)
    if indirect:
        indirect_fns += 1
    for i, ins in enumerate(insns):
        if ins.mnemonic != "call":
            continue
        op = ins.op_str
        if op.startswith("0x"):
            continue
        if reg_re.match(op):
            sites["call reg"] += 1
            tg = None if indirect else resolve(insns, jt, i, op)
            if tg:
                resolved_hits.append((ins.address, lo, tg))
                for t in tg:
                    if t in sset and t != lo:
                        fwd[lo].add(t)
                        rev[t].add(lo)
            else:
                prov = "indirect-jmp-fn" if indirect else provenance(insns, i, fam(op))
                unres.append((ins.address, lo, op, prov))
        elif op.startswith("qword ptr [rsp"):
            sites["call [rsp+disp]"] += 1
            m = re.match(r"qword ptr \[rsp \+ (0x[0-9a-f]+)\]", op)
            tg = None if indirect else stack_slot_value(insns, jt, i, m.group(1))
            if tg:
                resolved_hits.append((ins.address, lo, tg))
                for t in tg:
                    if t in sset and t != lo:
                        fwd[lo].add(t)
                        rev[t].add(lo)
            else:
                prov = "indirect-jmp-fn" if indirect else "stack-arg"
                unres.append((ins.address, lo, op, prov))


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
print(f"jump-table jmp resolved: {jt_resolved}")
print(f"functions with indirect jmp (all sites unresolved): {indirect_fns}")
hit = [(a, f, t) for a, f, t in resolved_hits if t & R]
print(f"resolved sites hitting R: {len(hit)}")
inC = [(a, f, op, p) for a, f, op, p in unres if f in C]
print(f"unresolved sites in C: {len(inC)} in {len({f for _, f, _, _ in inC})} functions")
for k, v in Counter(p for *_, p in inC).most_common():
    print(f"  {k}: {v}")
print(f"demo-bit functions: {sorted(hex(x) for x in demo)}  demo∩C={len(demo & C)}")
