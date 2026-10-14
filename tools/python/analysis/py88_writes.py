#!/usr/bin/env python3
"""PY-88 (#2788): [rbp+0x5b8] への書込みの値の式を、後ろ向きスライスで記号化する (実機不要)。

  python3 analysis/py88_writes.py <work/py53/fn.txt> [<VA> ...]

入力は analysis/py53_dispatch.py が出す fn.txt (capstone 逆アセンブル・関数内の連続命令列)。
引数 VA を省略すると、0x1047497 と 0x104aa87 の到達範囲 (py64_branch_regions.py と同じ region) にある `mov dword ptr [rbp + 0x5b8], reg` の一意な 65 件を対象にする。

各書込み命令について、ソースのレジスタの値を直前の命令へ遡って式にする。
- レジスタ: 直前の定義命令へ遡る (呼出しは eax だけ戻り値、他の caller-saved は clob)
- フレーム変数 [rbp+X]: 直前の同アドレス store のレジスタへ遡る (store 転送)。無ければ入力値 (M_rbp+X)
- 非フレームのメモリ: M32[式] / M64[式] / M8[式]。rip 相対は G[VA]
- call 0x40c660 は cvtsd2si (rint)、call 0x10469f0 等は CALL[VA](ecx,edx,r8d)、call qword ptr [..] は VCALL
- 合流: 遡りの途中に分岐先 (jcc/jmp の target) があれば ⚠合流 を付ける (値は経路で異なり得る)
"""
import re
import sys

sys.setrecursionlimit(20000)

FAM = {}
for fam, names in {
    "a": ["rax", "eax", "ax", "al", "ah"],
    "b": ["rbx", "ebx", "bx", "bl", "bh"],
    "c": ["rcx", "ecx", "cx", "cl", "ch"],
    "d": ["rdx", "edx", "dx", "dl", "dh"],
    "si": ["rsi", "esi", "si", "sil"],
    "di": ["rdi", "edi", "di", "dil"],
    "bp": ["rbp", "ebp"],
    "sp": ["rsp", "esp"],
}.items():
    for n in names:
        FAM[n] = fam
for i in range(8, 16):
    for suf in ["", "d", "w", "b"]:
        FAM[f"r{i}{suf}"] = f"r{i}"
for i in range(16):
    FAM[f"xmm{i}"] = f"xmm{i}"

CALLER_SAVED = {"a", "c", "d", "r8", "r9", "r10", "r11"} | {f"xmm{i}" for i in range(6)}
MOVLIKE = {"mov", "movzx", "movsx", "movsxd", "movsd", "movq", "movd", "movss", "cvtss2sd", "cvtsd2ss"}
ARITH = {"imul", "shl", "shr", "sar", "and", "or", "xor", "neg", "not", "inc", "dec", "sal"}
FLOATOP = {"mulsd": "*", "addsd": "+", "subsd": "-", "divsd": "/"}
WRITE_FIRST = MOVLIKE | ARITH | FLOATOP.keys() | {"add", "sub", "lea", "cvtsi2sd", "cvttsd2si", "cvtsd2si"}
SIZE_RE = re.compile(r"^(byte|word|dword|qword) ptr \[(.*)\]$")
TARGET_RE = re.compile(r"0x[0-9a-f]+")
INNER_RE = re.compile(r"([+-]?)\s*([^\s+-]+)")
DEPTH_LIMIT = 60
ACC_SLOT = 0x5B8


def load(path):
    ins, order = {}, []
    for ln in open(path):
        ln = ln.rstrip("\n")
        if not ln.strip():
            continue
        addr, rest = ln.split(": ", 1)
        parts = rest.split(None, 1)
        a = int(addr, 16)
        ins[a] = (parts[0], parts[1] if len(parts) > 1 else "")
        order.append(a)
    return ins, order


def parse_ops(s):
    return [] if not s else [x.strip() for x in s.split(", ")]


class Slicer:
    def __init__(self, ins, order):
        self.ins = ins
        self.order = order
        self.idx = {a: i for i, a in enumerate(order)}
        self.lines = [(a, ins[a][0], parse_ops(ins[a][1])) for a in order]
        self.targets = set()
        for a in order:
            m, o = ins[a]
            if m.startswith("j") and TARGET_RE.fullmatch(o.strip()):
                self.targets.add(int(o, 16))
        self.addr_taken = set()
        for a in order:
            m, o = ins[a]
            if m == "lea" and "[rbp + " in o:
                mm = re.search(r"\[rbp \+ (0x[0-9a-f]+)\]", o)
                if mm:
                    self.addr_taken.add(int(mm.group(1), 16))
        self.memo = {}

    def dst_fam(self, op):
        if op in FAM:
            return FAM[op]
        return None

    def writes_fam(self, mnem, ops):
        if not ops:
            return None
        d = ops[0]
        if mnem in WRITE_FIRST and d in FAM:
            return FAM[d]
        return None

    def resolve(self, fam, pos, depth=0):
        key = (fam, pos)
        if key in self.memo:
            return self.memo[key]
        if depth > DEPTH_LIMIT:
            return "…"
        i = pos - 1
        res = None
        while i >= 0:
            a = self.order[i]
            m, ops_s = self.ins[a]
            ops = parse_ops(ops_s)
            if m == "call":
                if fam == "a":
                    res = self.call_expr(i, depth + 1)
                    break
                if fam in CALLER_SAVED:
                    res = f"clob@{a:#x}"
                    break
            elif m in ("cmp", "test", "jmp", "ret", "nop") or m.startswith("j") or m.startswith("set") and False:
                pass
            elif m.startswith("cmov") and ops and FAM.get(ops[0]) == fam:
                res = f"CMOV@{a:#x}({self.ev(ops[1], i, depth + 1)})"
                break
            elif self.writes_fam(m, ops) == fam or (ops and m in FLOATOP and ops[0].startswith("xmm") and FAM.get(ops[0]) == fam):
                res = self.def_value(i, depth + 1)
                break
            elif m in ("cvtsi2sd",) and ops and FAM.get(ops[0]) == fam:
                res = self.def_value(i, depth + 1)
                break
            i -= 1
        if res is None:
            res = f"{fam}_in"
        if i >= 0 and self.order[i] not in ():
            pass
        for j in range(i + 1, pos):
            if self.order[j] in self.targets:
                res = res + f" ⚠合流@{self.order[j]:#x}"
                break
        if len(res) > 400:
            res = res[:400] + "…"
        self.memo[key] = res
        return res

    def def_value(self, i, depth):
        a = self.order[i]
        m, ops_s = self.ins[a]
        ops = parse_ops(ops_s)
        if m in MOVLIKE and len(ops) == 2:
            return self.ev(ops[1], i, depth + 1)
        if m == "lea":
            return "&" + self.addr_expr(ops[1].split("[", 1)[1].rstrip("]"), i, depth + 1)
        if m == "add" and len(ops) == 2:
            return f"({self.reg_or_mem(ops[0], i, depth + 1)} + {self.ev(ops[1], i, depth + 1)})"
        if m == "sub" and len(ops) == 2:
            return f"({self.reg_or_mem(ops[0], i, depth + 1)} - {self.ev(ops[1], i, depth + 1)})"
        if m == "xor" and len(ops) == 2 and ops[0] == ops[1]:
            return "0"
        if m in ARITH and len(ops) >= 1:
            rhs = self.ev(ops[1], i, depth + 1) if len(ops) == 2 else ""
            return f"{m}({self.reg_or_mem(ops[0], i, depth + 1)}{', ' + rhs if rhs else ''})"
        if m == "cvtsi2sd" and len(ops) == 2:
            return f"f64({self.ev(ops[1], i, depth + 1)})"
        if m in FLOATOP and len(ops) == 2:
            return f"({self.reg_or_mem(ops[0], i, depth + 1)} {FLOATOP[m]} {self.ev(ops[1], i, depth + 1)})"
        return f"<{m} {ops_s}>"

    def reg_or_mem(self, op, pos, depth):
        if op in FAM:
            return self.resolve(FAM[op], pos, depth)
        return self.ev(op, pos, depth)

    def call_expr(self, i, depth):
        a = self.order[i]
        m, o = self.ins[a]
        if o.strip() == "0x40c660":
            return f"rint({self.resolve('xmm0', i, depth + 1)})"
        if TARGET_RE.fullmatch(o.strip()):
            return (f"CALL[{o}](ecx={self.resolve('c', i, depth + 1)}, edx={self.resolve('d', i, depth + 1)}, "
                    f"r8d={self.resolve('r8', i, depth + 1)})@{a:#x}")
        return f"VCALL[{o}]@{a:#x}"

    def ev(self, op, pos, depth):
        """op (ソースオペランド) の、命令 pos 実行前の値。pos はオペランドを持つ命令の添字。"""
        op = op.strip()
        mm = SIZE_RE.match(op)
        if mm:
            size, inner = mm.group(1), mm.group(2)
            addr = self.addr_expr(inner, pos, depth + 1)
            return self.mem_read(addr, size, pos, depth + 1)
        if op in FAM:
            return self.resolve(FAM[op], pos, depth + 1)
        if op.startswith("xmm") or op.startswith("0x") or op.lstrip("-").isdigit():
            return op
        return op

    def addr_expr(self, inner, pos, depth):
        toks = INNER_RE.findall(inner)
        if any(t == "rip" for _, t in toks):
            disp = [int(t, 16) for s, t in toks if t.startswith("0x")][0]
            nxt = self.order[pos + 1] if pos + 1 < len(self.order) else self.order[pos] + 1
            return f"G[{nxt + disp:#x}]"
        terms = []
        for sign, tok in toks:
            if tok == "rbp":
                terms.append(sign + "rbp")
            elif "*" in tok:
                r, sc = tok.split("*")
                terms.append(sign + f"({self.resolve(FAM[r], pos, depth + 1)}*{sc})")
            elif tok in FAM:
                terms.append(sign + self.resolve(FAM[tok], pos, depth + 1))
            else:
                terms.append(sign + tok)
        return " ".join(terms) if terms else inner

    def mem_read(self, addr, size, pos, depth):
        size_name = {"byte": "M8", "word": "M16", "dword": "M32", "qword": "M64"}[size]
        if addr.startswith("rbp"):
            off = addr[3:].replace(" ", "")
            if off == "":
                off = "0"
            try:
                offv = int(off, 16) if off.startswith(("0x", "+0x")) else None
            except ValueError:
                offv = None
            if offv is None and off.startswith("+0x"):
                offv = int(off[1:], 16)
            if offv is not None:
                j = pos - 1
                while j >= 0:
                    m, o = self.ins[self.order[j]]
                    ops = parse_ops(o)
                    if len(ops) == 2 and ops[0].startswith(("dword ptr [rbp + ", "qword ptr [rbp + ")) and ops[0].split("[", 1)[1].rstrip("]") == f"rbp + {offv:#x}":
                        break
                    j -= 1
                joined = j >= 0 and any(self.order[k] in self.targets for k in range(j + 1, pos + 1))
                if offv == ACC_SLOT:
                    if j >= 0 and not joined and self.ins[self.order[j]][0] == "mov" and parse_ops(self.ins[self.order[j]][1])[1] in FAM:
                        return self.resolve(FAM[parse_ops(self.ins[self.order[j]][1])[1]], j, depth + 1)
                    return "ACC"
                if j < 0:
                    if offv in self.addr_taken:
                        return f"{size_name}[rbp+{offv:#x}]⚠addr-taken"
                    return f"IN[rbp+{offv:#x}]"
                m, o = self.ins[self.order[j]]
                ops = parse_ops(o)
                if m == "mov" and ops[1] in FAM and not joined:
                    return self.resolve(FAM[ops[1]], j, depth + 1)
                return f"SLOT[rbp+{offv:#x}]?@{self.order[j]:#x}"
        if addr.startswith("rip"):
            return f"{size_name}[G]"
        return f"{size_name}[{addr}]"


def default_targets(path):
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import py64_branch_regions as pb
    ins2, nxt = pb.load(path)
    out = set()
    for t in (0x1047497, 0x104AA87):
        for a in pb.region(ins2, nxt, t):
            if ins2[a][0] == "mov" and ins2[a][1].startswith("dword ptr [rbp + 0x5b8],"):
                out.add(a)
    return sorted(out)


def category(e):
    if e.startswith("rint("):
        return "rint(xmm0) (call 0x40c660)"
    if e.startswith("CALL["):
        return "CALL[未知の関数] の戻り値"
    if e.startswith("VCALL"):
        return "VCALL (vtbl 呼出しの戻り値)"
    if "SLOT[" in e:
        return "SLOT? (フレーム変数が合流を越える・一意に決まらない)"
    return "その他 (式は一意)"


def main():
    path = sys.argv[1]
    ins, order = load(path)
    s = Slicer(ins, order)
    targets = [int(x, 16) for x in sys.argv[2:]] or default_targets(path)
    counts = {}
    for a in targets:
        i = s.idx[a]
        m, o = ins[a]
        val = s.ev(parse_ops(o)[1], i, 0)
        counts[category(val)] = counts.get(category(val), 0) + 1
        print(f"{a:#x}: {m} {o}  ==> {val}")
    print(f"# n={len(targets)}", file=sys.stderr)
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"# {v:3d}  {k}", file=sys.stderr)


if __name__ == "__main__":
    main()
