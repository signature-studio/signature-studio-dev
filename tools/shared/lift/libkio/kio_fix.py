#!/usr/bin/env python3
"""kio_fix.py IN.ll OUT.ll [DSM] — RetDec 型復元欠陥 [A]-[E] の修復 pass (関数名を見ない)。
  引数の型は demangle 署名 (sig.py)、符号は機械語 (DSM の mnemonic) から決める。
  [C] 署名に C++ `long` (値渡し) がある関数: RetDec は i32 に復元する → 関数内の i32 を i64 に拡幅。
  [E] 機械語に idiv (符号付き除算) がある関数: IR の urem を srem に直す。DSM 省略時は行わない。
  [A] 参照引数 (long const& / double const&) の deref 落ち: ptrtoint %argN → load i64 %argN。
      ポインタ引数 (P / PK) の `trunc i64 %argN` + icmp は deref (cmp <M>[ptr N], 0) として load に直す。
  [A'] 引数レジスタ接続の欠落: 未初期化 alloca からの k 番目の load を、署名の k 番目がポインタなら %argK に接続。
  [B] 浮動小数点引数落ち: fp 引数が 1 つだけの関数は xmm0 を %argK のビット列で置換。
  [B][D] fp 引数 2 つ以上 (xmm_fix): IR から xmm 番号が消えるため、DSM の __asm_* 命令の xmm オペランドで load を fp 引数に接続し、
         DSM の jcc と分岐の真偽から ucomiss の flags を fcmp に接続する (DSM 省略時は行わない)。
  KIO_ARGREG=0 で [A'] を無効化 (ネガティブコントロール)。"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sig import params, idiv_fns

def fns_in(s): return sorted(set(re.findall(r"(?m)^define [^\n]*@(__Z\w+)\(", s)))
def body_of(s, fn):
    m = re.search(r"(?ms)^define [^\n]*@" + re.escape(fn) + r"\(.*?^}\n", s)
    return m.group(0) if m else None

s = open(sys.argv[1]).read()
dsm = sys.argv[3] if len(sys.argv) > 3 else None
SIGS = {fn: params(fn) for fn in fns_in(s)}
n = 0
def patch(fn, fnc):
    global s, n
    body = body_of(s, fn)
    if body is None: return
    new = fnc(body)
    if new != body: s = s.replace(body, new); n += 1

# [C] 値渡し long (i64 kind) を含む関数は i32 → i64
for fn, kinds in SIGS.items():
    if not kinds or "i64" not in kinds: continue
    def widen(body):
        new = re.sub(r"\bi32\b", "i64", body)
        new = re.sub(r"sext i64 (\S+) to i64", r"add i64 \1, 0", new)
        return re.sub(r"zext i64 (\S+) to i64", r"add i64 \1, 0", new)
    patch(fn, widen)
# [E] idiv を持つ関数は urem → srem
if dsm:
    for fn in idiv_fns(dsm) & set(SIGS):
        patch(fn, lambda b: b.replace("urem i64", "srem i64"))
# [A] 参照引数 (ref64 / f64ref) の deref: ptrtoint → load i64
for fn, kinds in SIGS.items():
    if not kinds: continue
    idxs = [i + 1 for i, k in enumerate(kinds) if k in ("ref64", "f64ref")]
    if not idxs: continue
    def deref(body, idxs=idxs):
        for i in idxs:
            body = re.sub(r"(%\w+) = ptrtoint \S+ %arg" + str(i) + r" to i64", r"\1 = load i64, ptr %arg" + str(i) + ", align 8", body)
        return body
    patch(fn, deref)
# [A] ポインタ引数の trunc+icmp → deref load (cmp <M>[ptr N], 0)
BITS = {"i8": 1, "i16": 2, "i32": 4, "i64": 8}
PTR = ("buf", "str16", "str32", "str8")
for fn, kinds in SIGS.items():
    if not kinds: continue
    idxs = [i + 1 for i, k in enumerate(kinds) if k in PTR]
    if not idxs: continue
    def trunc_deref(body, idxs=idxs):
        for i in idxs:
            for ty in ("i16", "i32", "i8"):
                pat = r"(%\w+) = trunc i64 %arg" + str(i) + " to " + ty + r"\n"
                if not (re.search(pat, body) and re.search(r"icmp eq " + ty + r" %\w+, 0", body)): continue
                def rep(k, i=i, ty=ty):
                    v, p = k.group(1), "%ptr" + k.group(1)[1:]
                    return f"{p} = inttoptr i64 %arg{i} to ptr\n  {v} = load {ty}, ptr {p}, align {BITS[ty]}\n"
                body = re.sub(pat, rep, body)
        return body
    patch(fn, trunc_deref)
# [B] 浮動小数点引数落ち: fp 引数が 1 つだけなら、その alloca の load を %argK のビット列で置換
for fn, kinds in SIGS.items():
    if not kinds: continue
    fl = [i for i, k in enumerate(kinds) if k in ("f32", "f64")]
    if len(fl) != 1: continue
    k = fl[0] + 1; bits, fty = (32, "float") if kinds[fl[0]] == "f32" else (64, "double")
    def fpfix(body, k=k, bits=bits, fty=fty):
        for al in sorted(set(re.findall(r"(%\w+) = alloca i128", body))):
            if re.search(r"store [^\n]*, ptr " + re.escape(al) + r"[,\s]", body): continue
            pat = r"(%\w+) = load i128, ptr " + re.escape(al) + r"\n"
            def rep(mm, k=k, bits=bits, fty=fty):
                v = mm.group(1)
                return f"%fpbits{k} = bitcast {fty} %arg{k} to i{bits}\n  {v} = zext i{bits} %fpbits{k} to i128\n"
            body = re.sub(pat, rep, body)
        return body
    patch(fn, fpfix)
# [B][D] fp 引数 2 つ以上: xmm 番号と ucomiss flags の接続 (IR から番号が消えるため DSM で決める)
#   xmm 番号: IR の __asm_* 引数は DSM 命令の末尾オペランドに対応する (Intel: dest 先頭)。SysV では j 番目の fp 引数が xmm j。
#   flags: 分岐 (!insn.addr = jcc) の条件を DSM の jcc から決め、ucomiss の a,b (fp 引数) の fcmp に置く。
JCC = {"ja": ("ogt", "ule"), "jae": ("oge", "ult"), "jb": ("ult", "oge"), "jbe": ("ule", "ogt"), "je": ("ueq", "one"), "jne": ("one", "ueq")}
def dsm_insns(path):
    out = {}
    for line in open(path, errors="replace"):
        m = re.match(r"0x([0-9a-f]+):\s[^\t]*\t(\S+)(.*)$", line)
        if m: out[int(m.group(1), 16)] = (m.group(2), [o.strip() for o in re.sub(r"<[^>]*>", "", m.group(3)).split(",") if o.strip()])
    return out
META = {m.group(1): int(m.group(2)) for m in re.finditer(r"(?m)^!(\d+) = !\{i64 (\d+)\}", s)}
def stored(body, ptr): return re.search(r"store [^\n]*, ptr " + re.escape(ptr) + r"[,\s]", body)
def xmm_fix(body, kinds, insns):
    fp = [i for i, k in enumerate(kinds) if k in ("f32", "f64")]
    bind = {}
    for mm in re.finditer(r"call \w+ @__asm_\w+\(([^)]*)\), !insn\.addr !(\d+)", body):
        ins = insns.get(META.get(mm.group(2)))
        if ins is None: continue
        args = [a.strip().split()[-1] for a in mm.group(1).split(",") if a.strip()]
        if not args or len(args) > len(ins[1]): continue
        for a, op in zip(args, ins[1][-len(args):]):
            if a.startswith("%") and re.fullmatch(r"xmm\d+", op):
                r = int(op[3:])
                bind[a] = None if bind.setdefault(a, r) != r else r
    xarg = {j: (i + 1, kinds[i]) for j, i in enumerate(fp)}
    for name, r in bind.items():
        if r not in xarg: continue
        ld = re.search(re.escape(name) + r" = load i128, ptr (%\w+)\n", body)
        if not ld or stored(body, ld.group(1)): continue
        k, kind = xarg[r]; bits, fty = (32, "float") if kind == "f32" else (64, "double")
        fb = "%fb" + name[1:]
        body = body.replace(ld.group(0), f"{fb} = bitcast {fty} %arg{k} to i{bits}\n  {name} = zext i{bits} {fb} to i128\n")
    ucs = re.findall(r"call void @__asm_ucomiss\(i128 (%\w+), i128 (%\w+)\), !insn\.addr !\d+", body)
    br = re.search(r"br i1 (%\w+), label %dec_label_pc_([0-9a-f]+), label %dec_label_pc_[0-9a-f]+, !insn\.addr !(\d+)", body)
    if len(ucs) != 1 or not br or ucs[0][0] not in bind or ucs[0][1] not in bind: return body
    ra, rb = bind[ucs[0][0]], bind[ucs[0][1]]
    if ra not in xarg or rb not in xarg: return body
    orm = re.search(re.escape(br.group(1)) + r" = or i1 (%\w+), (%\w+)(?=,|\n)", body)
    flags = list(orm.groups()) if orm else [br.group(1)]
    ins = insns.get(META.get(br.group(3)))
    if ins is None or ins[0] not in JCC or not ins[1]: return body
    C, N = JCC[ins[0]]
    pred = C if int(br.group(2), 16) == int(ins[1][0], 16) else N
    lds = [re.search(re.escape(f) + r" = load i1, ptr (%\w+)\n", body) for f in flags]
    if any(ld is None for ld in lds) or len({ld.group(1) for ld in lds}) != 1 or stored(body, lds[0].group(1)): return body
    for f, ld in zip(flags, lds):
        body = body.replace(ld.group(0), f"{f} = fcmp {pred} float %arg{xarg[ra][0]}, %arg{xarg[rb][0]}\n")
    return re.sub(r"(?m)^  uselistorder [^\n]*\n", "", body)
if dsm:
    INSNS = dsm_insns(dsm)
    for fn, kinds in SIGS.items():
        if not kinds or sum(k in ("f32", "f64") for k in kinds) < 2 or any(k in ("ref64", "f64ref") for k in kinds): continue
        patch(fn, lambda b, kinds=kinds: xmm_fix(b, kinds, INSNS))
# [A'] 引数レジスタ接続の欠落: 単一 alloca から読まれる整数 load を、DSM のレジスタ参照で署名の引数に接続する。
#   署名の整数クラス引数 (fp 以外) の j 番目は SysV の SYSV[j] に入る。load の値が inttoptr されて DSM の
#   メモリ参照 [reg] になる命令 (!insn.addr) から reg を得る。その命令に束縛できない load は、ロード幅 (i8/i16/…) と
#   同幅の [reg] (byte/word/… ptr) を関数内で参照する未束縛ポインタ引数のレジスタが 1 つに定まるときに限り束縛する。判定できなければ変更しない。
SYSV = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
FN_RANGE = {m.group(1): (int(m.group(2), 16), int(m.group(3), 16)) for m in re.finditer(r"(?m)^; function: (\S+) at 0x([0-9a-f]+) -- 0x([0-9a-f]+)", open(dsm, errors="replace").read())} if dsm else {}
def mem_regs(a):
    return {r for o in INSNS.get(a, ("", []))[1] for r in re.findall(r"\[(r\w+)", o)}
def insn_of(body, v):
    for line in body.split("\n"):
        if re.search(r"inttoptr i64 " + re.escape(v) + r" to ", line):
            m = re.search(r"!insn\.addr !(\d+)", line)
            return META.get(m.group(1)) if m else None
    return None
WIDTH = {"i8": "byte", "i16": "word", "i32": "dword", "i64": "qword"}
def ptr_width(body, v):
    m = re.search(r"(%\w+) = inttoptr i64 " + re.escape(v) + r" to ptr", body)
    if not m: return None
    ws = set(re.findall(r"= load (i\d+), ptr " + re.escape(m.group(1)) + r"[,\s]", body))
    return WIDTH.get(ws.pop()) if len(ws) == 1 else None
def arg_reg(body, kinds, fn):
    lo, hi = FN_RANGE.get(fn, (0, 0))
    ptr_arg, j = {}, 0
    for i, k in enumerate(kinds):
        if k in ("f32", "f64"): continue
        if j < len(SYSV) and k in PTR: ptr_arg[SYSV[j]] = i + 1
        j += 1
    for al in sorted(set(re.findall(r"(%\w+) = alloca i64", body))):
        if re.search(r"store [^\n]*, ptr " + re.escape(al) + r"[,\s]", body): continue
        loads = re.findall(r"(%\w+) = load i64, ptr " + re.escape(al) + r"\n", body)
        if not loads: continue
        bound, free = {}, []
        for v in loads:
            regs = mem_regs(insn_of(body, v)) & set(ptr_arg)
            if len(regs) == 1: bound[v] = ptr_arg[regs.pop()]
            else: free.append(v)
        for v in list(free):
            w = ptr_width(body, v)
            cand = {m.group(1) for a in INSNS if lo <= a < hi for o in INSNS[a][1] if w for m in [re.search(rf"{w} ptr \[(r\w+)", o)] if m}
            cand = {r for r in cand if r in ptr_arg and ptr_arg[r] not in bound.values()}
            if len(cand) == 1: bound[v] = ptr_arg[cand.pop()]; free.remove(v)
        if free or not bound: continue
        for v, k in bound.items():
            body = body.replace(f"{v} = load i64, ptr {al}\n", f"{v} = ptrtoint ptr %arg{k} to i64\n")
    return re.sub(r"(?m)^  uselistorder [^\n]*\n", "", body)
if os.environ.get("KIO_ARGREG", "1") != "0" and dsm:
    for fn, kinds in SIGS.items():
        if not kinds or not any(k in PTR for k in kinds): continue
        if any(k in ("f32", "f64", "f64ref") for k in kinds): continue
        patch(fn, lambda b, kinds=kinds, fn=fn: arg_reg(b, kinds, fn))
open(sys.argv[2], "w").write(s)
print(f"[kio_fix] widened {n} functions")
