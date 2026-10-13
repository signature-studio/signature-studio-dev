#!/usr/bin/env python3
"""kio_fix.py IN.ll OUT.ll [DSM] — RetDec 型復元欠陥 [A]-[E] の修復 pass (関数名を見ない)。
  引数の型は demangle 署名 (sig.py)、符号は機械語 (DSM の mnemonic) から決める。
  [C] 署名に C++ `long` (値渡し) がある関数: RetDec は i32 に復元する → 関数内の i32 を i64 に拡幅。
  [E] 機械語に idiv (符号付き除算) がある関数: IR の urem を srem に直す。DSM 省略時は行わない。
  [A] 参照引数 (long const& / double const&) の deref 落ち: ptrtoint %argN → load i64 %argN。
      ポインタ引数 (P / PK) の `trunc i64 %argN` + icmp は deref (cmp <M>[ptr N], 0) として load に直す。
  [A'] 引数レジスタ接続の欠落: 未初期化 alloca からの k 番目の load を、署名の k 番目がポインタなら %argK に接続。
  [B] 浮動小数点引数落ち: fp 引数が 1 つだけの関数は xmm0 を %argK のビット列で置換。
  [B][D] 例外: fp 引数 3 つ (f32,f32,f32) の関数は IR から xmm 番号が消えるため、手で決めた対応を署名で当てる (FLOAT3)。
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
# [B][D] fp 3 つ (f32,f32,f32): xmm 番号と ucomiss flags の接続 (IR から番号が消えるため手で決めた対応)
FLOAT3 = {"%2 = load i128, ptr %0": "%fbits2 = bitcast float %arg3 to i32\n  %2 = zext i32 %fbits2 to i128",
          "%3 = load i128, ptr %0": "%fbits3 = bitcast float %arg2 to i32\n  %3 = zext i32 %fbits3 to i128",
          "%4 = load i128, ptr %0": "%fbits4 = bitcast float %arg1 to i32\n  %4 = zext i32 %fbits4 to i128",
          "%5 = load i1, ptr %1": "%5 = fcmp ule float %arg2, %arg1",
          "%6 = load i1, ptr %1": "%6 = fcmp ule float %arg2, %arg1"}
for fn, kinds in SIGS.items():
    if kinds != ["f32", "f32", "f32"]: continue
    def float3(body):
        new = body
        for old, rep in FLOAT3.items(): new = new.replace(old, rep)
        return re.sub(r"(?m)^  uselistorder .*\n", "", new)
    patch(fn, float3)
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
