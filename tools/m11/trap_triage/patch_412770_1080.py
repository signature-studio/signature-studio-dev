#!/usr/bin/env python3
"""patch_412770_1080.py IN.ll OUTDIR : function_412770 の null memcpy 源を差し替えた IR を 2 本作る (#1080)。
  patchA.ll: source を native 機械語どおり `load i64, ptr %arg1` (= *arg1) にする。
  patchB.ll: source を 0 埋め領域 (memset 済み alloca) にする。null 読みの意味論だけを変える対照。
"""
import sys, os

src_path, outdir = sys.argv[1], sys.argv[2]
src = open(src_path).read()
a = src.index('define i64 @function_412770(')
b = src.index('\n}\n', a) + 3
body = src[a:b]
old = '  call void @__asm_rep_movsq_memcpy(ptr %4, ptr null, i64 37)\n'
assert body.count(old) == 1, body.count(old)

newA = ('  %m11src = load i64, ptr %arg1, align 8\n'
        '  %m11srcp = inttoptr i64 %m11src to ptr\n'
        '  call void @__asm_rep_movsq_memcpy(ptr %4, ptr %m11srcp, i64 37)\n')
newB = ('  %m11zero = alloca [37 x i64], align 8\n'
        '  %m11zp = bitcast ptr %m11zero to ptr\n'
        '  call void @llvm.memset.p0.i64(ptr align 8 %m11zp, i8 0, i64 296, i1 false)\n'
        '  call void @__asm_rep_movsq_memcpy(ptr %4, ptr %m11zp, i64 37)\n')
decl = 'declare void @llvm.memset.p0.i64(ptr nocapture writeonly, i8, i64, i1 immarg)\n'

for name, new in (('A', newA), ('B', newB)):
    out = src[:a] + body.replace(old, new) + src[b:]
    if name == 'B':
        i = out.index('\ndefine ')
        out = out[:i] + '\n' + decl + out[i:]
    with open(os.path.join(outdir, f'patch{name}.ll'), 'w') as f:
        f.write(out)
print('patch written:', outdir)
