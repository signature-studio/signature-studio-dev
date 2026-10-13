#!/usr/bin/env python3
"""kio_fix.py IN.ll OUT.ll — RetDec 型復元欠陥 [C] の最小修復 pass (PoC)。
  [C] C++ `long` (LP64 では 64bit) を RetDec が i32 として復元する → 該当関数の i32 を i64 に拡幅。
      対象は demangle 署名 (Z9Limit_RCSlll / Z9FixHi_RCSll / Z9CBool_RCSl) の `l` 引数のみ。
  [E] idiv (符号付き除算) が urem に化ける符号欠陥: FixHi_RCS の `urem i64` を `srem i64` へ。
  [A] deref 落ち ([rsi] が rsi そのものに化ける): 参照渡し引数を持つ Get*/Set*Intel 6 関数のみ修復。
      unilen/wcslen16/str*compare の `cmp word ptr [rdi],0` 系、[B] float 引数落ち、[D] ucomiss flags 落ちは
      この PoC では修復しない (tools/m7 ir7_argpass / m8 ir8_valueflow 相当の関数別 pass が必要; REPORT §4)。"""
import re, sys
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
# [B] float 引数落ち: 元の機械語は xmm 引数を直接読むが RetDec IR は未初期化 alloca から読んでいる。
#     逆アセンブル確認済みの対応 (xmm0=arg1, xmm1=arg2, xmm2=arg3) で alloca load を float 引数の lane0 bit 列に置換する。
# [D] ucomiss flags 落ち: `ucomiss xmm1,xmm0; ja` は xmm1 > xmm0 (順序付き・非 NaN) の分岐。flags の load を fcmp ogt に接続する。
def xmm_of(v, arg): return f"%fbits{v} = bitcast float %arg{arg} to i32\n  %{v} = zext i32 %fbits{v} to i128"
FLOAT_XMM = {
  "__Z7Fix_RCSf": {"%1 = load i128, ptr %0": xmm_of("1", 1)},
  "__Z14LimitFloat_RCSfff": {
    "%2 = load i128, ptr %0": xmm_of("2", 3),
    "%3 = load i128, ptr %0": xmm_of("3", 2),
    "%4 = load i128, ptr %0": xmm_of("4", 1),
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
open(sys.argv[2], "w").write(s)
print(f"[kio_fix] widened {n} functions")
