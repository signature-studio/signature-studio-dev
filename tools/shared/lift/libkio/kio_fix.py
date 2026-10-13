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
# [A'] 引数レジスタ接続の欠落: 単一 alloca に spill された k 番目の整数引数の load を、署名の k 番目 (ポインタ) に接続
def arg_reg(body, kinds):
    for al in sorted(set(re.findall(r"(%\w+) = alloca i64", body))):
        if re.search(r"store [^\n]*, ptr " + re.escape(al) + r"[,\s]", body): continue
        cnt = [0]
        def rep(mm, kinds=kinds, cnt=cnt):
            j = cnt[0]; cnt[0] += 1
            if j < len(kinds) and kinds[j] in PTR:
                return f"{mm.group(1)} = ptrtoint ptr %arg{j + 1} to i64\n"
            return mm.group(0)
        body = re.sub(r"(%\w+) = load i64, ptr " + re.escape(al) + r"\n", rep, body)
    return re.sub(r"(?m)^  uselistorder [^\n]*\n", "", body)
if os.environ.get("KIO_ARGREG", "1") != "0":
    for fn, kinds in SIGS.items():
        if not kinds or not any(k in PTR for k in kinds): continue
        if any(k in ("f32", "f64", "f64ref") for k in kinds): continue
        patch(fn, lambda b, kinds=kinds: arg_reg(b, kinds))
open(sys.argv[2], "w").write(s)
print(f"[kio_fix] widened {n} functions")
