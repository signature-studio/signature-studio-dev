#!/usr/bin/env python3
# 9b4b00 / 9b5450 の書込みマスク測定 (#2085). m11_ov.c を一時的に書き換え, 変種ごとに ov.o を作り直して survey する.
import json, os, re, shutil, subprocess, sys
TOOL = sys.argv[1]  # tools/m11 の絶対パス
SRC = os.path.join(TOOL, 'm11_ov.c')
ORIG = os.path.join(os.environ['RUNNER_TEMP'], 'm11_ov.orig.c')
OUT = os.path.join(TOOL, 'work', 's2085')
os.makedirs(OUT, exist_ok=True)
shutil.copy(SRC, ORIG)
src0 = open(ORIG).read()

def patch(mask):
    s = src0
    stmts = [
        ('    Q(rbx + 0x54) = rax;', 0),
        ('    *(volatile u8*)(uintptr_t)(rbx + 0x34) = 0;', 1),
        ('    function_9b5450(rbx);', 2),
        ('    function_4133f0(rbx + 0x48, R(0x5b4b74));', 3),
        ('    function_412d60(rbx + 0x80, 0);', 4),
        ('    D(rbx + 0x3c) = 0;', 5),
        ('    function_412d60(rbx + 0x28, 0);', 6),
        ('    D(rbx + 0x30) = 0xffffff9d;', 7),
    ]
    for txt, bit in stmts:
        assert s.count(txt) == 1, txt
        s = s.replace(txt, '    if (M11_9B_MASK & 0x%x) %s' % (1 << bit, txt.strip()))
    body_start = '    Q(rcx + 0x5c) = 0;\n'
    body_end = '    function_412d60(rcx + 0x28, 0);\n'
    assert s.count(body_start) == 1 and s.count(body_end) == 1
    i = s.index(body_start); j = s.index(body_end) + len(body_end)
    s = s[:i] + '    if (M11_9B_MASK & 0x100) {\n' + s[i:j] + '    }\n' + s[j:]
    anchor = '/* function_9b5450  VA 0x9b5450'
    assert s.count(anchor) == 1
    s = s.replace(anchor, '#define M11_9B_MASK %s\n' % mask + anchor)
    return s

def run(tag, mask):
    open(SRC, 'w').write(patch(mask))
    env = dict(os.environ, M11_OV_CLASSCREATE='1', FL_WIN64_DIR=os.environ['FL_WIN64_DIR'], RETDEC_ROOT=os.environ['RETDEC_ROOT'])
    ov = os.path.join(TOOL, 'work', 'obj', 'ov.o')
    if os.path.exists(ov): os.remove(ov)
    b = subprocess.run(['bash', 'm11_build.sh'], cwd=TOOL, env=env, capture_output=True, text=True, timeout=300)
    if b.returncode != 0:
        print(tag, 'BUILD FAIL', b.stdout[-300:], b.stderr[-300:], flush=True); return
    out = os.path.join(OUT, 'mask_%s.json' % tag)
    s = subprocess.run(['node', 'trap_triage/survey_units.mjs', out], cwd=TOOL, env=dict(env, SV_RAW='1'),
                       capture_output=True, text=True, timeout=300)
    line = [l for l in s.stdout.splitlines() if 'SURVEY_UNITS' in l]
    rows = {r['unit']: r for r in json.load(open(out))}
    print(tag, 'mask=' + mask, line[-1] if line else 'NO SUMMARY', 'unit190=' + rows[190]['kind'], flush=True)

variants = [('full', '0x1ff')] + [('no%d' % b, '0x1ff & ~0x%x' % (1 << b)) for b in range(8)] + [('no9', '0x0ff'), ('none', '0x0')]
only = sys.argv[2].split(',') if len(sys.argv) > 2 else None
try:
    for tag, m in variants:
        if only and tag not in only: continue
        run(tag, m)
finally:
    shutil.copy(ORIG, SRC)
    print('restored m11_ov.c', flush=True)
