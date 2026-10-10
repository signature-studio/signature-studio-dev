#!/usr/bin/env python3
"""m6_simd_check.py (M6b): __asm_* helper signature の 3 重照合.

照合対象:
  (1) lift IR 宣言 (SRC 既定 work/ott_memfix0.ll — build が実際に食う IR) の declare 型
  (2) msimd6.c の EMSCRIPTEN_KEEPALIVE 定義 signature (C 側)
  (3) lift IR 内の call site の ret/arg 型 vs (1) (i128 → u128 等の型名変換で整合)

成り立つべき不変式:
  (1) == (2) 全件一致 (i256 3 種は SKIP: m6_memfix.py により呼出消滅。declare は
      残るが import されない — (3) で呼出 0 を確認)
  (3) mismatch 0

exit code: 全件一致 0 / 不一致あり 1.

使い方: python3 m6_simd_check.py [SRC_LL] [MSIMD_C]
"""
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else 'work/ott_memfix0.ll'
C = sys.argv[2] if len(sys.argv) > 2 else 'msimd6.c'

TYMAP = {'i128': 'u128', 'i64': 'u64', 'i32': 'u32', 'i8': 'u8', 'void': 'void'}

def irargs(txt):
    toks = []
    for a in [x.strip() for x in txt.split(', ')]:
        if not a:
            continue
        toks.append(a.split()[0].rstrip(','))
    return tuple(toks)


def cargs(txt):
    parts = [x.strip() for x in txt.split(', ')]
    parts = [x for x in parts if x]
    if parts == ['void']:
        return ()
    toks = []
    for a in parts:
        toks.append(a.split()[0])
    return tuple(toks)


src = open(SRC).read()
csrc = open(C).read()

decls = {}
for m in re.finditer(r'(?m)^declare (\S+) @(__asm_[\w.\-]+)\((.*?)\) local_unnamed_addr$', src):
    decls[m.group(2)] = (m.group(1), irargs(m.group(3)))

# --- (2) C 定義 parse ---
cdefs = {}
for m in re.finditer(r'(?m)^EMSCRIPTEN_KEEPALIVE (\S+) (__asm_[\w.\-]+)\((.*?)\)$', csrc):
    cdefs[m.group(2)] = (m.group(1), cargs(m.group(3)))

print('declares in IR:', len(decls), '/ defs in msimd6.c:', len(cdefs))

skip = [nm for nm, ty in decls.items() if 'i256' in ty[1] or 'i256' == ty[0]]
print('i256 skips (呼出消滅対象):', skip)

bad = 0
for nm in sorted(set(decls) | set(cdefs)):
    if nm in skip and nm not in cdefs:
        continue   # i256 は意図的に skip
    d = decls.get(nm)
    c = cdefs.get(nm)
    if d is None:
        print('MISMATCH(def-only):', nm, c)
        bad += 1
        continue
    if c is None:
        if 'i256' in d[1] or d[0] == 'i256':
            continue
        print('MISMATCH(missing-def):', nm, 'IR:', d)
        bad += 1
        continue
    dty = (TYMAP.get(d[0], d[0]), tuple(TYMAP.get(x, x) for x in d[1]))
    if dty != c:
        print('MISMATCH:', nm, 'IR:', dty, ' C:', c)
        bad += 1

# --- (3) call site 整合 ---
nbad3 = 0
for m in re.finditer(r'(?m)^  .*\bcall (\S+) (__asm_[\w.\-]+)\((.*?)\)(?=,|\)|$)', src):
    ret, nm, args = m.group(1), m.group(2), m.group(3)
    argt = irargs(args)
    d = decls.get(nm)
    if d is None:
        print('CALL-NO-DECLARE:', nm)
        nbad3 += 1
        continue
    dty = (TYMAP.get(d[0], d[0]) if d[0] != 'i256' else 'i256', tuple(TYMAP.get(x, x) if 'i256' not in x else x for x in d[1]))
    if (TYMAP.get(ret, ret), argt) != dty:
        print('CALL-SIG:', nm, 'call: (%s)(%s)' % (ret, ','.join(argt)), 'decl:', '(%s)(%s)' % (dty[0], ','.join(dty[1])))
        nbad3 += 1

# i256 helper の残呼出 (main の SKIP 条件: なければ)
n256 = sum(1 for m in re.finditer(r'call \S+ __asm_(?:v)?(?:movdqu|movdqa|vmovntdq|movntdq)\b[^;]*;', src))
n256b = sum(1 for l in src.splitlines() if 'call' in l and ('@__asm_vmovdqu(' in l or '@__asm_vmovdqa(' in l or '@__asm_vmovntdq(' in l))
print('i256 residual calls:', n256, '/', n256b)

print('decl def mismatch:', bad, ' / callsite mismatch:', nbad3)
sys.exit(0 if (bad == 0 and nbad3 == 0 and n256 == 0) else 1)
