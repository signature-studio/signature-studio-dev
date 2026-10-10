#!/usr/bin/env python3
"""gvraw.py: RetDec 産の VA 名付き global (`@global_var_3025f530 = constant [8 x i8] ...`) を全廃し,
参照を生の linear address (`inttoptr (i64 0x3025f530 to ptr)`) に置換する。

根拠 (ott 差分デバッグで確定): RetDec は「観測された access 幅」だけの小 global (多くは [8 x i8]/[4 x i8]) を作る。
ところが lift 後の IR はその global を base にした pointer 演算 (例: ctor の param 既定値表 20 x f32 を
`rsi += 4` で走査, 16B xmm 定数 load = `load i128 @G` で上位 8B が隣接 global) で範囲外を読む。
実データは m6_data_install が同アドレス (0x30000000 + RVA) に DLL .rdata/.data 実体を敷設済みなので,
名前付き global を介さず生アドレスを参照すれば実データを正しい幅・正しい隣接関係で読める。
usage: gvraw.py in.ll out.ll"""
import re, sys
src = open(sys.argv[1]).read().split('\n')
defre = re.compile(r'^@global_var_([0-9a-f]+) = ')
useref = re.compile(r'@global_var_([0-9a-f]+)\b')
out = []
ndef = nuse = 0
for l in src:
    if defre.match(l):
        ndef += 1
        continue
    if '@global_var_' in l:
        def sub(m):
            global nuse
            nuse += 1
            return f'inttoptr (i64 {int(m.group(1), 16)} to ptr)'
        l = useref.sub(sub, l)
    out.append(l)
open(sys.argv[2], 'w').write('\n'.join(out))
print(f'[gvraw] globals removed: {ndef}, refs rewritten: {nuse}')
