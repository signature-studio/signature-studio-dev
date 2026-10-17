#!/usr/bin/env python3
# #4882: instr.wat の `$2983` 入口 (`local.set $8` の直後) で入力 `$2` を import dbg_entry_4882 に渡す。
# hook は JS import で線形メモリには書かない。分岐・戻り値は変えない (戻り値は drop)。
# 使い方: python3 patch_entry_2983_4882.py <in instr.wat> <out.wat>
#   → wasm-as --enable-bulk-memory --enable-sign-ext --enable-mutable-globals --enable-nontrapping-float-to-int <out.wat> -o <out.wasm>
#   (`--all-features` で組むと Node が「unknown import kind 0x7e」で読めない。wasm-opt 133 の既定の組み合わせ)。
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    lines = f.read().split('\n')
S = [l.strip() for l in lines]

imp = [i for i, s in enumerate(S) if s.startswith('(import "env" "store_val_i64"')]
assert len(imp) == 1, imp
ind_imp = lines[imp[0]][:len(lines[imp[0]]) - len(lines[imp[0]].lstrip())]
lines.insert(imp[0] + 1, ind_imp + '(import "env" "dbg_entry_4882" (func $dbg_entry_4882 (param i32 i64) (result i32)))')
S.insert(imp[0] + 1, '')

fn = [i for i, s in enumerate(S) if s.startswith('(func $2983 (param $0 i64) (param $1 i32) (param $2 i32) (result i64)')]
assert len(fn) == 1, fn
setv = [i for i in range(fn[0], fn[0] + 400) if S[i] == '(local.set $8']
assert len(setv) == 1, setv
ind_set = lines[setv[0]][:len(lines[setv[0]]) - len(lines[setv[0]].lstrip())]
# `(local.set $8` ... `)` の閉じ行を探す (同じインデント)
end = next(i for i in range(setv[0] + 1, setv[0] + 40) if lines[i] == ind_set + ')')
body = [
    ind_set + '(drop',
    ind_set + ' (call $dbg_entry_4882',
    ind_set + '  (local.get $2)',
    ind_set + '  (local.get $0)',
    ind_set + ' )',
    ind_set + ')',
]
lines[end + 1:end + 1] = body

with open(dst, 'w') as f:
    f.write('\n'.join(lines))
print('patched', dst, 'set8 line', setv[0] + 1, 'close', end + 1)
