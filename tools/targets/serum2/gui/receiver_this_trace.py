#!/usr/bin/env python3
"""SR-43 #2174: 間接 call [R+disp] (disp = 0x30/0x38/0x88) の呼出先オブジェクトを、所属関数の中で this / 引数まで遡って分類する (静的・関数内のみ)。

入力: Serum2_win64.vst3 (PE, x64 MSVC)。
方法: 候補 call ごとに
  1. R の値を後ろ向きに遡る (mov/lea/load/copy)。copy は読み替え、rsp 相対の spill (store → load) は store 元へ読み替える。
  2. R が [B+0] (vptr の読み出し) なら呼出先オブジェクトは B。B の値を同様に遡る。
  3. 遡りが関数先頭まで届けば引数 (rcx = this、rdx/r8/r9 = 引数)。途中の [X+d] は X を遡る (深さ上限 5)。
分類 (category):
  THIS       呼出先オブジェクト = 所属関数の this (rcx の受け取り値そのまま)
  THIS-EMB   this + lea オフセット (埋め込み子オブジェクトのアドレス)
  THIS-CHILD this からロードを 1 段以上経由した子オブジェクト
  ARG / ARG-EMB / ARG-CHILD  this 以外の引数 (rdx/r8/r9) 由来
  CALLRET / GLOBAL / STACK / STACKSLOT / CLOBBER / ARITH / OTHER / INDEX / NODOM / DEPTH 他: 未解決の理由
strict: 遡りで見つけた定義が使用を支配しない (使用へ定義を通らずに到達できる) なら NODOM として未解決にする。
        間接 jmp を含む関数は全て NODOM 扱い (分岐先が見えないため)。
loose : 支配関係を見ず線形に遡る (参考値。分岐の反対側の定義を誤って拾い得る)。
限界: 関数間の追跡 (呼出元の引数) はしない。
      this の型は証明しない。THIS と判定された関数が slot 関数 (vtable の登録関数) なら SerumController の this。
usage: receiver_this_trace.py <pe> [--vtable 0x180a2bf58] [--tsv out.tsv]
"""
import bisect
import re
import struct
import sys
from collections import Counter, defaultdict

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

ARGS = sys.argv
pe = pefile.PE(ARGS[1])
data = open(ARGS[1], "rb").read()
IMG = pe.OPTIONAL_HEADER.ImageBase
DISPS = {0x30, 0x38, 0x88}
HEAD = int(ARGS[ARGS.index("--vtable") + 1], 16) if "--vtable" in ARGS else 0x180A2BF58
TSV = ARGS[ARGS.index("--tsv") + 1] if "--tsv" in ARGS else None
MAXLOAD = 5
MAXSTEP = 64
MEM = re.compile(r"\[([^\]]*)\]")


def sec(name):
    return next(s for s in pe.sections if s.Name.rstrip(b"\0") == name)


def rva_to_off(va):
    rva = va - IMG
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return rva - s.VirtualAddress + s.PointerToRawData
    return None


def rq(va):
    return struct.unpack_from("<Q", data, rva_to_off(va))[0]


text = sec(b".text")
t_base = IMG + text.VirtualAddress
pdata = sec(b".pdata")
pd = data[pdata.PointerToRawData:pdata.PointerToRawData + pdata.SizeOfRawData]
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, _ = struct.unpack_from("<III", pd, i)
    if b == 0:
        break
    funcs.append((IMG + b, IMG + e))
funcs.sort()
starts = [f[0] for f in funcs]


def func_of(va):
    k = bisect.bisect_right(starts, va) - 1
    if k >= 0 and funcs[k][0] <= va < funcs[k][1]:
        return funcs[k][0]
    return None


slot_fns = set()
for k in range(64):
    v = rq(HEAD + 8 * k)
    if v == 0:
        break
    slot_fns.add(v)

ALIAS = {}
for x in "abcd":
    ALIAS |= {f"r{x}x": (f"r{x}x", 64), f"e{x}x": (f"r{x}x", 32), f"{x}x": (f"r{x}x", 16),
              f"{x}l": (f"r{x}x", 8), f"{x}h": (f"r{x}x", 8)}
for x in ["si", "di", "bp", "sp"]:
    ALIAS |= {f"r{x}": (f"r{x}", 64), f"e{x}": (f"r{x}", 32), x: (f"r{x}", 16), f"{x}l": (f"r{x}", 8)}
for i in range(8, 16):
    ALIAS |= {f"r{i}": (f"r{i}", 64), f"r{i}d": (f"r{i}", 32), f"r{i}w": (f"r{i}", 16), f"r{i}b": (f"r{i}", 8)}
CALLER = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
ARGNAME = {"rcx": "this", "rdx": "arg", "r8": "arg", "r9": "arg"}
NOWRITE = {"push", "cmp", "test", "call", "ret", "nop", "bt", "endbr64", "int3", "jmp"}
IMPLICIT1 = {"cqo": {"rdx"}, "cdq": {"rdx"}, "cwd": {"rdx"}, "cdqe": {"rax"}, "cwde": {"rax"},
             "cbw": {"rax"}, "rdtsc": {"rax", "rdx"}, "cpuid": {"rax", "rbx", "rcx", "rdx"},
             "syscall": {"rax", "rcx", "r11"}, "cmpxchg": {"rax"}}


def implicit(ins):
    mn = ins.mnemonic.split()[-1]
    if mn in ("mul", "imul", "div", "idiv") and "," not in ins.op_str:
        return {"rax", "rdx"}
    if mn in IMPLICIT1:
        return IMPLICIT1[mn]
    if ins.mnemonic.startswith("rep ") or mn in ("stosb", "stosw", "stosd", "stosq", "movsb", "movsw", "movsq"):
        if mn.startswith("stos"):
            return {"rdi", "rcx"}
        if mn.startswith("movs"):
            return {"rdi", "rsi", "rcx"}
    return set()


def parse_mem(op, ins):
    mm = MEM.search(op)
    if mm is None:
        return None
    inner = mm.group(1).replace(" ", "")
    size = op.split(" ptr")[0].strip() if " ptr" in op else None
    rip = re.search(r"rip([+-])(0x[0-9a-f]+)", inner)
    if rip:
        d = int(rip.group(2), 16) * (1 if rip.group(1) == "+" else -1)
        return {"base": None, "disp": d, "index": False, "rip": True,
                "target": ins.address + ins.size + d, "size": size}
    base, disp, index = None, 0, False
    for sign, term in re.findall(r"([+-]?)([^+-]+)", inner):
        if "*" in term or (term not in ALIAS and not term.startswith("0x")):
            index = True
        elif term.startswith("0x"):
            disp += -int(term, 16) if sign == "-" else int(term, 16)
        elif sign != "-" and base is None:
            base = ALIAS[term][0]
        else:
            index = True
    return {"base": base, "disp": disp, "index": index, "rip": False, "target": None, "size": size}


def write_kind(ins, reg):
    if reg in implicit(ins):
        return "impl"
    mn = ins.mnemonic.split()[-1]
    if mn in NOWRITE or mn.startswith("j"):
        return None
    ops = [o.strip() for o in ins.op_str.split(",")]
    if mn == "xchg":
        return "xchg" if any(ALIAS.get(o, ("", 0))[0] == reg for o in ops) else None
    a = ALIAS.get(ops[0])
    if a and a[0] == reg:
        return "full" if a[1] >= 32 else "partial"
    return None


def classify(ins, wk):
    mn = ins.mnemonic.split()[-1]
    if wk == "impl":
        return ("other", mn)
    if wk == "partial":
        return ("other", "partial:" + mn)
    if wk == "xchg":
        return ("other", "xchg")
    if mn in ("mov", "movzx", "movsx", "movsxd", "movabs", "lea"):
        ops = ins.op_str.split(",", 1)
        dst, src = ops[0].strip(), ops[1].strip()
        if "[" in src:
            m = parse_mem(src, ins)
            if m is None or m["index"]:
                return ("index", mn) if m else ("other", mn)
            if m["rip"]:
                return ("global", m["target"]) if mn == "lea" else ("gload", m["target"])
            if m["base"] is None:
                return ("other", mn)
            if mn == "lea":
                if m["base"] in ("rsp", "rbp"):
                    return ("stack", m["disp"])
                return ("lea", (m["base"], m["disp"]))
            if m["size"] != "qword" or ALIAS[dst][1] != 64:
                return ("other", mn)
            return ("load", (m["base"], m["disp"]))
        if src in ALIAS and mn in ("mov", "movabs") and ALIAS[src][1] == 64 and ALIAS[dst][1] == 64:
            return ("copy", ALIAS[src][0])
        return ("other", mn)
    return ("arith", mn)


class Fn:
    def __init__(self, ins):
        self.ins = ins
        idx = {x.address: i for i, x in enumerate(ins)}
        self.index = idx
        self.indirect = False
        self.succ = []
        n = len(ins)
        for i, x in enumerate(ins):
            mn = x.mnemonic.split()[-1]
            s = []
            if mn.startswith("j"):
                if re.fullmatch(r"0x[0-9a-f]+", x.op_str):
                    if int(x.op_str, 16) in idx:
                        s.append(idx[int(x.op_str, 16)])
                else:
                    self.indirect = True
            if mn not in ("jmp", "ret", "retq", "int3", "ud2", "hlt") and i + 1 < n:
                s.append(i + 1)
            self.succ.append(s)
        self.cache = {}

    def reach(self, avoid):
        """関数先頭から avoid の命令を通らずに到達できる命令 index の集合 (avoid < 0 なら制限なし)。"""
        if avoid in self.cache:
            return self.cache[avoid]
        seen = {0} if avoid != 0 else set()
        stack = list(seen)
        while stack:
            x = stack.pop()
            for y in self.succ[x]:
                if y != avoid and y not in seen:
                    seen.add(y)
                    stack.append(y)
        self.cache[avoid] = seen
        return seen

    def dominated(self, d, u):
        """定義 d が使用 u を支配する (u へのどの経路も d を通る) か。間接分岐を含む関数は安全側で偽。"""
        if self.indirect:
            return False
        return u not in self.reach(d) and u in self.reach(-1)


def resolve(fn, pos, reg):
    for k in range(pos - 1, -1, -1):
        ins = fn.ins[k]
        if ins.mnemonic == "call":
            if reg == "rax":
                return ("callret", None, k)
            if reg in CALLER:
                return ("clobber", None, k)
            continue
        wk = write_kind(ins, reg)
        if wk is None:
            continue
        kind, info = classify(ins, wk)
        return (kind, info, k)
    return ("entry", reg, None)


def find_store(fn, k, mem):
    base, disp = mem
    for j in range(k - 1, max(-1, k - 600), -1):
        ins = fn.ins[j]
        mn = ins.mnemonic.split()[-1]
        if mn == "call" or (mn in ("push", "pop") and base == "rsp"):
            return None
        ops = ins.op_str.split(",", 1)
        if mn == "mov" and len(ops) == 2 and "[" in ops[0]:
            m = parse_mem(ops[0], ins)
            if m and m["base"] == base and m["disp"] == disp and not m["index"]:
                src = ops[1].strip()
                if m["size"] == "qword" and src in ALIAS and ALIAS[src][1] == 64:
                    return (j, ALIAS[src][0])
                return None
        if write_kind(ins, base) is not None:
            return None
    return None


def value(fn, pos, reg, strict):
    for _ in range(MAXSTEP):
        kind, info, k = resolve(fn, pos, reg)
        if k is None:
            return ("entry", info, None)
        if strict and not fn.dominated(k, pos):
            return ("nodom", None, k)
        if kind == "copy":
            pos, reg = k, info
            continue
        if kind == "load" and info[0] in ("rsp", "rbp"):
            sp = find_store(fn, k, info)
            if sp is None:
                return ("stackslot", info, k)
            s, src = sp
            if strict and not fn.dominated(s, k):
                return ("nodom", None, s)
            pos, reg = s, src
            continue
        return (kind, info, k)
    return ("depth", None, None)


def origin(fn, pos, reg, strict, depth=0):
    if depth > MAXLOAD:
        return ("depth", [])
    kind, info, k = value(fn, pos, reg, strict)
    if kind == "entry":
        return (ARGNAME.get(info, "entry-" + info), [])
    if kind in ("load", "lea"):
        base, d = info
        root, steps = origin(fn, k, base, strict, depth + 1)
        return (root, steps + [("[+%#x]" if kind == "load" else "+%#x") % d])
    return (kind, [])


def category(root, steps):
    if root in ("this", "arg"):
        pre = "THIS" if root == "this" else "ARG"
        if not steps:
            return pre
        if all(s.startswith("+") for s in steps):
            return pre + "-EMB"
        return pre + "-CHILD"
    return root.upper()


def receiver(fn, i, base, strict):
    kind, info, k = value(fn, i, base, strict)
    if kind == "load" and info[0] not in ("rsp", "rbp"):
        ob, d = info
        root, steps = origin(fn, k, ob, strict)
        if d == 0:
            return ("vptr", root, steps)
        return ("vptr-emb", root, steps + [f"+{d:#x}"])
    return ("R-" + kind, "-", [])


ctor_fns = set()
fns = {}
ins_all = list(Cs(CS_ARCH_X86, CS_MODE_64).disasm(text.get_data(), t_base))
by_func = defaultdict(list)
for ins in ins_all:
    f = func_of(ins.address)
    if f is not None:
        by_func[f].append(ins)
for ins in ins_all:
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", ins.op_str)
    if m:
        d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
        if ins.address + ins.size + d == HEAD:
            ctor_fns.add(func_of(ins.address))


def get_fn(f):
    if f not in fns:
        fns[f] = Fn(by_func[f])
    return fns[f]


def sc_closure():
    """SerumController の this を持つ関数の集合。起点 = slot 関数 (S) と ctor 形 (K)。
    起点から、this (rcx) をそのまま渡して直接 call している先も this を SerumController とみなし、不動点まで伸ばす (C)。"""
    sc = set(slot_fns) | {f for f in ctor_fns if f}
    frontier = list(sc)
    stat = Counter()
    while frontier:
        g = frontier.pop()
        if g not in by_func:
            continue
        fn = get_fn(g)
        for i, ins in enumerate(fn.ins):
            if ins.mnemonic != "call" or not re.fullmatch(r"0x[0-9a-f]+", ins.op_str):
                continue
            f = int(ins.op_str, 16)
            if f in sc or func_of(f) != f:
                continue
            stat["direct-call-to-new-fn"] += 1
            cat = origin(fn, i, "rcx", True)
            stat[cat[0] + ("" if not cat[1] else "-child")] += 1
            if cat == ("this", []):
                sc.add(f)
                frontier.append(f)
    print(f"SC 伝播: 直接 call (宛先が未登録の関数) の rcx の遡り結果 {dict(stat)}")
    return sc


def analyze(strict):
    rows = []
    for ins in ins_all:
        if ins.mnemonic != "call":
            continue
        mm = parse_mem(ins.op_str.strip(), ins)
        if mm is None or mm["disp"] not in DISPS or mm["index"] or mm["rip"] or mm["base"] is None:
            continue
        f = func_of(ins.address)
        if f is None:
            rows.append((ins.address, None, mm["base"], mm["disp"], "NOFUNC", "", ""))
            continue
        fn = get_fn(f)
        i = fn.index[ins.address]
        mode, root, steps = receiver(fn, i, mm["base"], strict)
        cat = category(root, steps) if mode.startswith("vptr") else mode
        if mode.startswith("vptr"):
            cat = mode + ":" + cat
        path = root + "".join(steps)
        ev = "S" if f in slot_fns else "K" if f in ctor_fns else "C" if f in SC else "-"
        rows.append((ins.address, f, mm["base"], mm["disp"], cat, path, ev))
    return rows


SC = sc_closure()
rows_s = analyze(True)
rows_l = analyze(False)
cs = Counter(r[4] for r in rows_s)
cl = Counter(r[4] for r in rows_l)
print(f"candidates (disp 0x30/0x38/0x88): {len(rows_s)}")
print("== strict (分岐越えの定義は未解決) ==")
for k, n in cs.most_common():
    print(f"{n:5d}  {k}")
print("== loose (分岐を無視・参考) ==")
for k, n in cl.most_common(12):
    print(f"{n:5d}  {k}")
this_rows = [r for r in rows_s if r[4] == "vptr:THIS"]
by_f = Counter((r[1], r[6]) for r in this_rows)
print(f"SerumController this 集合 (S/K/C): {len(SC)} 関数")
print(f"== strict THIS (vptr:THIS): {len(this_rows)} 件, 所属関数 {len(by_f)} 個, 証拠別 {dict(Counter(r[6] for r in this_rows))} ==")
for (f, sl), n in by_f.most_common(20):
    print(f"{n:5d}  F={f:#x} evidence={sl}")
paths = Counter(r[5] for r in rows_s if "CHILD" in r[4])
print("== strict CHILD の経路 (上位 15) ==")
for p, n in paths.most_common(15):
    print(f"{n:5d}  {p}")
if TSV:
    with open(TSV, "w") as fh:
        fh.write("call_va\tfunc\treg\tdisp\tcat_strict\tcat_loose\tpath_strict\tevidence\n")
        loose = {r[0]: r for r in rows_l}
        for r in rows_s:
            lr = loose.get(r[0])
            fh.write(f"{r[0]:#x}\t{(r[1] or 0):#x}\t{r[2]}\t{r[3]:#x}\t{r[4]}\t{lr[4] if lr else ''}\t{r[5]}\t{r[6]}\n")
