#!/usr/bin/env python3
"""ir_kh_f7.py — RetDec が `movq (%r8),%r9` の deref を落とす silent miscompile の修復 (PoC, site 指定型)。

gain::GainDsp::process の ch0 ポインタ取得 `mov r9,[r8]` (r8 = AudioBuffer*) は、lift IR 上で
  %X = mul i64 %rax.0.reload, 4 ; %Y = add i64 %X, %arg3 ; inttoptr %Y → load/store (float)
となり arg3 (構造体自身) を sample 配列として扱う。ch1 側 (`mov r9,[r8+8]`) は正しく deref される。
差分ハーネス (native_ref vs wasm) の self_out[0x88] meter 不一致で検出。
修復: 当該 add の base を `load i64, ptr %arg3` (= *(i64*)(arg3+0)) に置換。
usage: ir_kh_f7.py in.ll out.ll
"""
import re
import sys


def main(src, dst):
    L = open(src).read().split('\n')
    out, n = [], 0
    mulvar = None
    for i, l in enumerate(L):
        m = re.match(r"^\s*(%[\w.\-]+) = mul i64 %rax\.0\.reload, 4$", l)
        if m:
            mulvar = m.group(1)
        m2 = re.match(r"^(\s*)(%[\w.\-]+) = add i64 (%[\w.\-]+), %arg3$", l)
        if m2 and mulvar and m2.group(3) == mulvar:
            n += 1
            ind, dstv = m2.group(1), m2.group(2)
            out.append(f"{ind}%f7.p{n} = inttoptr i64 %arg3 to ptr")
            out.append(f"{ind}%f7.ch0{n} = load i64, ptr %f7.p{n}, align 8")
            out.append(f"{ind}{dstv} = add i64 {mulvar}, %f7.ch0{n}")
            continue
        out.append(l)
    open(dst, 'w').write('\n'.join(out))
    print(f"[kh_f7] ch0 deref restored at {n} site(s)")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
