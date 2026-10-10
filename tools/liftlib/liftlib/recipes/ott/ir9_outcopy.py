#!/usr/bin/env python3
"""ir9_outcopy.py (M9 [F7]): processReplacing 最終出力 copy の deref 脱落修復.

dsm 0x180120632 (proc_true.dsm, function_18011ec20 内):
    mov rax, qword ptr [r12]            ; rax = outputs[0] pointer (deref!)
    movss dword ptr [rax + rsi*4], ...  ; L 出力 store
これが IR では store base `%add %mul(rsi,4), %r8.3.reload` (= %arg3 直接) と
    訳され deref 1 個が欠落。result: L store が outputs pointer 配列の内部
    (arg3 + 0..255*4 = 1 KB) を f32 破壊 → pointer 配列破損 + L junk 巨大値。
修復: その add 1 式を `arg3 deref load + rsi*4` へ置換し, 後続 store の ptr 参照も
    新 var 名へ揃える (dsm 忠実化)。
"""
import argparse
import json
import re

ap = argparse.ArgumentParser()
ap.add_argument('src')
ap.add_argument('dst')
ap.add_argument('--report', default=None)
args = ap.parse_args()

lines = open(args.src).read().splitlines()


def fn_range(fname):
    for i, l in enumerate(lines):
        if l.startswith('define ') and '@' + fname + '(' in l:
            j = i
            while j < len(lines) and not lines[j].startswith('}'):
                j += 1
            return i, j
    raise SystemExit(f'define {fname} not found')


di, dj = fn_range('function_18011ec20')
cands = []
for i in range(di, dj):
    l = lines[i]
    if l.startswith('  ') and '= add i64 ' in l and l.endswith(', %r8.3.reload'):
        cands.append(i)
if len(cands) != 1:
    raise SystemExit(f'r8.3.reload add candidate = {len(cands)} (expect 1): {cands}')
k = cands[0]
old = lines[k].strip()
mulvar = old.split('= add i64 ')[1].split(',')[0].strip()
# 旧 add dest 名
m = re.match(r'^  %(f\d|x\d+) = ', lines[k])
oldname = old.split(' = ')[0].strip()
fix = [
    f'  ; ir9 [F7] 出力 copy deref 修復 (旧: {old})',
    '  %f7p = inttoptr i64 %arg3 to ptr',
    '  %f7b = load i64, ptr %f7p',
]
fix = [
    f'  ; ir9 [F7] 出力 copy deref 修復 (旧: {old})',
    '  %f7p = inttoptr i64 %arg3 to ptr',
    '  %f7b = load i64, ptr %f7p',
]
# dest 名は維持 (旧 %2119 を後続 inttoptr → store がそのまま参照)
lines[k:k + 1] = fix + ['  ' + oldname + ' = add i64 ' + mulvar + ', %f7b']
rep = {'fixes': [f'out copy L base deref: mul={mulvar}, add={oldname} (dest 名維持)']}
with open(args.dst, 'w') as f:
    f.write('\n'.join(lines) + '\n')
if args.report:
    with open(args.report, 'w') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
print(f'[ir9_outcopy] {rep["fixes"][0]} -> {args.dst}')
