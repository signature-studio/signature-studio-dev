#!/usr/bin/env python3
"""fix_rv.py IN.ll OUT.ll — libreverb (win) の RetDec IR に対する最小修復 pass。
  [D] ucomiss の flags が IR に接続されない (DEFECTS.md の ucomiss 系 / libkio REPORT §4 [D] と同型):
      元 asm は `ucomiss xmm0,xmm12(=0.0); jp L1; je L2` (= 「x == 0.0 (非 NaN) なら L2 へ」)。
      RetDec は ucomiss を no-op の `call @__asm_ucomiss` にし、分岐条件を直前の `add rax,4` の parity flag から作る
      (`%or.cond = icmp eq i1 <zero-flag-of-pointer-add>, <parity>`)。
      `__asm_ucomiss(A, B)` の直後にある最初の `%or.cond = icmp eq i1 ..` を `fcmp oeq float lane0(A), lane0(B)` で置換する。
  期待数 (Fruity 1 + UF 1 = 2 箇所) と一致しなければ exit 1 (黙って素通りしない)。 usage: fix_rv.py IN OUT [expect=2]"""
import re, sys
s = open(sys.argv[1]).read().split("\n")
expect = int(sys.argv[3]) if len(sys.argv) > 3 else 2
out, n, i = [], 0, 0
pending = None
tmp = 0
for line in s:
    if re.match(r"\s*uselistorder ", line): continue   # use-list 順序ヒント (置換で use 数が変わると不整合になる。意味は持たない)
    m = re.match(r"\s*call void @__asm_ucomiss\(i128 (%\S+), i128 (%\S+)\)", line)
    if m: pending = (m.group(1), m.group(2))
    if pending and re.match(r"\s*(%or\.cond\S*) = icmp eq i1 ", line):
        name = re.match(r"\s*(%or\.cond\S*)", line).group(1)
        a, b = pending; tmp += 1
        out += [f"  %rvfix.a{tmp} = trunc i128 {a} to i32", f"  %rvfix.af{tmp} = bitcast i32 %rvfix.a{tmp} to float",
                f"  %rvfix.b{tmp} = trunc i128 {b} to i32", f"  %rvfix.bf{tmp} = bitcast i32 %rvfix.b{tmp} to float",
                f"  {name} = fcmp oeq float %rvfix.af{tmp}, %rvfix.bf{tmp}"]
        n += 1; pending = None
        continue
    out.append(line)
open(sys.argv[2], "w").write("\n".join(out))
print(f"[fix_rv] ucomiss flag sites repaired: {n} (expected {expect})")
if n != expect: sys.exit(1)
