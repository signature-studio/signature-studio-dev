#!/usr/bin/env python3
"""kio_fix.py IN.ll OUT.ll — RetDec 型復元欠陥 [C] の最小修復 pass (PoC)。
  [C] C++ `long` (LP64 では 64bit) を RetDec が i32 として復元する → 該当関数の i32 を i64 に拡幅。
      対象は demangle 署名 (Z9Limit_RCSlll / Z9FixHi_RCSll / Z9CBool_RCSl) の `l` 引数のみ。
  [E] idiv (符号付き除算) が urem に化ける符号欠陥: FixHi_RCS の `urem i64` を `srem i64` へ。
  [A] deref 落ち ([rsi] が rsi そのものに化ける): 参照渡し引数を持つ Get*/Set*Intel 6 関数のみ修復。
      unilen/wcslen16/str*compare の `cmp word ptr [rdi],0` 系は [A] 汎用 pass の対象外 (REPORT §4)。
      [D] ucomiss flags 落ちは LimitFloat_RCSfff のみ FLOAT_XMM (関数名直書き PoC) で修復する。汎用化は #1129。
      [A'] 引数レジスタ接続の欠落は汎用 pass で修復する (str2compare/str4compare の 2nd arg, REPORT §4)。"""
import os, re, sys
WIDEN = ["__Z9Limit_RCSlll", "__Z9FixHi_RCSll", "__Z9CBool_RCSl"]
s = open(sys.argv[1]).read()
n = 0
for fn in WIDEN:
    m = re.search(r"(?ms)^define [^\n]*@" + re.escape(fn) + r"\(.*?^}\n", s)
    if not m: continue
    body = m.group(0)
    new = re.sub(r"\bi32\b", "i64", body)
    new = re.sub(r"sext i64 (\S+) to i64", r"add i64 \1, 0", new)
    new = re.sub(r"zext i64 (\S+) to i64", r"add i64 \1, 0", new)
    if fn == "__Z9FixHi_RCSll": new = new.replace("urem i64", "srem i64")
    s = s.replace(body, new); n += 1
# [A] 参照渡し引数 (const long& / const double&) の deref 復元: 元 asm は `mov rax,[rsi]` / `mov rax,[rdx]` だが
#     RetDec IR は ptrtoint(%argN) (= ポインタ値そのもの) を使っている。 N は関数ごとの `&` 引数位置。
DEREF = {"__Z12GetFourIntelPhRKl": [2], "__Z13GetEightIntelPhRKl": [2], "__Z13GetFloatIntelPhRKl": [2], "__Z14GetDoubleIntelPhRKl": [2],
         "__Z12SetFourIntelPhRKlS1_": [2, 3], "__Z20SetDoubleIntelDoublePhRKlRKd": [2, 3]}
for fn, idxs in DEREF.items():
    m = re.search(r"(?ms)^define [^\n]*@" + re.escape(fn) + r"\(.*?^}\n", s)
    if not m: continue
    body = m.group(0); new = body
    for i in idxs:
        new = re.sub(r"(%\w+) = ptrtoint \S+ %arg" + str(i) + r" to i64", r"\1 = load i64, ptr %arg" + str(i) + ", align 8", new)
    s = s.replace(body, new); n += 1
# [A] 汎用: マングル名の引数型が P/PK (ポインタ) の引数 N について、RetDec が `trunc i64 %argN to iM` と
#     整数化して `icmp eq iM _, 0` している箇所は、元機械語の `cmp <M>[ptr N], 0` (deref) である。
#     名前ではなく署名から位置とポインタ性を決め、該当 trunc を inttoptr+load に置換する。
def ptr_params(fn):
    m = re.match(r"__Z(\d+)", fn)
    if not m: return None
    rest = fn[m.end() + int(m.group(1)):]
    toks = re.findall(r"PK[a-zA-Z]|P[a-zA-Z]|[a-zA-Z]", rest)
    if "".join(toks) != rest: return None
    return [i + 1 for i, t in enumerate(toks) if t.startswith("P")]
BITS = {"i8": 1, "i16": 2, "i32": 4, "i64": 8}
for fn in sorted(set(re.findall(r"(?m)^define [^\n]*@(__Z\w+)\(", s))):
    idxs = ptr_params(fn)
    if not idxs: continue
    m = re.search(r"(?ms)^define [^\n]*@" + re.escape(fn) + r"\(.*?^}\n", s)
    body = m.group(0); new = body
    for i in idxs:
        for ty in ("i16", "i32", "i8"):
            pat = r"(%\w+) = trunc i64 %arg" + str(i) + " to " + ty + r"\n"
            if not (re.search(pat, new) and re.search(r"icmp eq " + ty + r" %\w+, 0", new)): continue
            def rep(k, i=i, ty=ty):
                v, p = k.group(1), "%ptr" + k.group(1)[1:]
                return f"{p} = inttoptr i64 %arg{i} to ptr\n  {v} = load {ty}, ptr {p}, align {BITS[ty]}\n"
            new = re.sub(pat, rep, new)
    if new != body: s = s.replace(body, new); n += 1
# [B] 浮動小数点引数落ち: 署名に f/d 引数が 1 つだけの関数では、RetDec は xmm0 を初期化されていない alloca から読む
#     (store が無い)。唯一の fp 引数は SysV で xmm0 に入るので、その alloca の load を %argK のビット列で置換する。
#     fp 引数が複数の関数は xmm 番号が IR から失われるため対象外 (LimitFloat_RCSfff は別途)。
def fp_params(fn):
    m = re.match(r"__Z(\d+)", fn)
    if not m: return None
    rest = fn[m.end() + int(m.group(1)):]
    toks = re.findall(r"RK[a-zA-Z]|R[a-zA-Z]|PK[a-zA-Z]|P[a-zA-Z]|[a-zA-Z]", rest)
    if "".join(toks) != rest: return None
    return toks
for fn in sorted(set(re.findall(r"(?m)^define [^\n]*@(__Z\w+)\(", s))):
    toks = fp_params(fn)
    if not toks: continue
    fl = [i for i, t in enumerate(toks) if t in ("f", "d")]
    if len(fl) != 1: continue
    m = re.search(r"(?ms)^define [^\n]*@" + re.escape(fn) + r"\(.*?^}\n", s)
    body = m.group(0); new = body
    k = fl[0] + 1; bits, fty = (32, "float") if toks[fl[0]] == "f" else (64, "double")
    for al in sorted(set(re.findall(r"(%\w+) = alloca i128", new))):
        if re.search(r"store [^\n]*, ptr " + re.escape(al) + r"[,\s]", new): continue
        pat = r"(%\w+) = load i128, ptr " + re.escape(al) + r"\n"
        def rep(mm, k=k, bits=bits, fty=fty):
            v = mm.group(1)
            return f"%fpbits{k} = bitcast {fty} %arg{k} to i{bits}\n  {v} = zext i{bits} %fpbits{k} to i128\n"
        new = re.sub(pat, rep, new)
    if new != body: s = s.replace(body, new); n += 1
# [B'] 個別規則 (xmm 番号が既知の関数, PoC): 逆アセンブル確認済みの対応 (xmm0=arg1, xmm1=arg2, xmm2=arg3)。
# LimitFloat_RCSfff は fp 引数 3 つのため汎用 [B] の対象外。Fix_RCSf は汎用 [B] で処理済みのため規則を置かない。
def xmm_of(v, arg): return f"%fbits{v} = bitcast float %arg{arg} to i32\n  %{v} = zext i32 %fbits{v} to i128"
FLOAT_XMM = {
  "__Z14LimitFloat_RCSfff": {
    "%2 = load i128, ptr %0": xmm_of("2", 3),
    "%3 = load i128, ptr %0": xmm_of("3", 2),
    "%4 = load i128, ptr %0": xmm_of("4", 1),
    # [D] ucomiss flags 落ち: `ucomiss xmm1,xmm0` の flags を fcmp に接続する。極性 (ja/jbe) は .ll の br で未検証 (要素材)
    "%5 = load i1, ptr %1": "%5 = fcmp ule float %arg2, %arg1",
    "%6 = load i1, ptr %1": "%6 = fcmp ule float %arg2, %arg1",
  },
}
for fn, rules in FLOAT_XMM.items():
    m = re.search(r"(?ms)^define [^\n]*@" + re.escape(fn) + r"\(.*?^}\n", s)
    if not m: continue
    body = m.group(0); new = body
    for old, rep in rules.items():
        new = new.replace(old, rep)
    new = re.sub(r"(?m)^  uselistorder .*\n", "", new)
    if new != body: s = s.replace(body, new); n += 1
# [A'] 引数レジスタ接続の欠落 (汎用): RetDec は整数引数 k 番目を、store の無い未初期化 alloca からの k 番目の load
#     として読むことがある (str2compare: %1=rdi, %2=rsi が同じ %0 を読み %arg2 が未参照)。SysV では k 番目の
#     整数クラス引数は k 番目の整数レジスタ = 署名の k 番目の引数。署名の k 番目が P/PK のときだけ
#     `ptrtoint ptr %argK` に置換する。f/d を含む署名は対象外。R は対象外にしない (参照引数は整数レジスタ 1 本を
#     使うポインタ。ただし置換は P/PK 位置のみ)。前提: 単一 alloca に全引数が spill され、その k 番目の load が
#     整数引数 k。R/K は独立トークンとして添字を数えるため、R/K の後ろに P が来る署名では添字がずれる。
#     KIO_ARGREG=0 で無効化 (ネガティブコントロール)。
def int_params(fn):
    m = re.match(r"__Z(\d+)", fn)
    if not m: return None
    rest = fn[m.end() + int(m.group(1)):]
    toks = re.findall(r"PK[a-zA-Z]|P[a-zA-Z]|[a-zA-Z]", rest)
    if "".join(toks) != rest or any(t in ("f", "d") for t in toks): return None
    return toks
for fn in (sorted(set(re.findall(r"(?m)^define [^\n]*@(__Z\w+)\(", s))) if os.environ.get("KIO_ARGREG", "1") != "0" else []):
    toks = int_params(fn)
    if not toks or not any(t.startswith("P") for t in toks): continue
    m = re.search(r"(?ms)^define [^\n]*@" + re.escape(fn) + r"\(.*?^}\n", s)
    body = m.group(0); new = body
    for al in sorted(set(re.findall(r"(%\w+) = alloca i64", new))):
        if re.search(r"store [^\n]*, ptr " + re.escape(al) + r"[,\s]", new): continue
        cnt = [0]
        def rep(mm, toks=toks, cnt=cnt):
            j = cnt[0]; cnt[0] += 1
            if j < len(toks) and toks[j].startswith("P"):
                return f"{mm.group(1)} = ptrtoint ptr %arg{j + 1} to i64\n"
            return mm.group(0)
        new = re.sub(r"(%\w+) = load i64, ptr " + re.escape(al) + r"\n", rep, new)
    if new != body:
        new = re.sub(r"(?m)^  uselistorder [^\n]*\n", "", new)
        s = s.replace(body, new); n += 1
open(sys.argv[2], "w").write(s)
print(f"[kio_fix] widened {n} functions")
