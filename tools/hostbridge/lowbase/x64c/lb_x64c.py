#!/usr/bin/env python3
"""lb_x64c.py — tools/ott/lift/x64c.py を無改変で呼び、V-shift 先 (LB_BASE) と関数名 prefix を引数化する薄い wrapper.
  x64c の `sh()` は module 変数 SHIFT/IMG/IMG_SIZE を呼出時に参照するので、import 後に差し替えるだけで全アドレス (ea/imm/jump table/dispatch case) が追従する.
usage: lb_x64c.py --base 0x10000 [--prefix ott] [--x64c PATH] -- <x64c.py の引数 (--pe ... --out ...)>
出力 C の関数名 f_<va> は --prefix 指定時 <prefix>_f_<va> に置換 (同一 wasm に複数 DLL を static link する時の衝突回避).
"""
import sys, os, re, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[1:]
base, prefix, x64c = 0x10000, '', os.path.join(HERE, '..', '..', '..', 'ott', 'lift', 'x64c.py')
rest = []
i = 0
while i < len(argv):
    a = argv[i]
    if a == '--base': base = int(argv[i + 1], 0); i += 2
    elif a == '--prefix': prefix = argv[i + 1]; i += 2
    elif a == '--x64c': x64c = argv[i + 1]; i += 2
    elif a == '--': rest = argv[i + 1:]; break
    else: rest.append(a); i += 1
spec = importlib.util.spec_from_file_location('x64c_orig', x64c)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.SHIFT = m.IMG - base
sys.argv = ['x64c.py'] + rest
m.main()
out = rest[rest.index('--out') + 1]
if prefix:
    p = os.path.join(out, 'ott_lifted.c')
    s = open(p).read()
    s2 = re.sub(r'\bf_([0-9a-f]{5,9})\b', prefix + r'_f_\1', s)
    s2 = re.sub(r'\bott_dispatch\b', prefix + '_dispatch', s2)   # 同一 wasm に複数 DLL を載せる時の入口も衝突回避
    s2 = s2.replace('#include "ott_cpu.h"\n', '#include "ott_cpu.h"\nvoid %s_dispatch(uint64_t);\n' % prefix, 1)
    open(p, 'w').write(s2)
    print('[lb_x64c] prefix %s_: renamed %d f_ symbols + dispatch' % (prefix, len(set(re.findall(r'\bf_[0-9a-f]{5,9}\b', s)))))
print('[lb_x64c] V-shift: 0x%x -> 0x%x (SHIFT=0x%x)' % (m.IMG, base, m.SHIFT))
