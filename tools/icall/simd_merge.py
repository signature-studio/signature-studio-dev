#!/usr/bin/env python3
"""simd_merge.py GEN.c OUT.c EXTRA.c [EXTRA.c ...] [--report R.json]
m11_simd2.py が生成した __asm_* helper C から、
  1. EXTRA (icall_simd_extra.c) が定義している名前の stub 定義を除く (EXTRA 側の実装を使う)
  2. 残った「未実装 stub (m11_simd_unimpl_once: stderr に出して 0 を返す = silent)」を fail-fast (abort) に差し替える
を行う。route は OUT.c と EXTRA を別々にリンクする (EXTRA の重複定義が出ない)。"""
import json, re, sys

args = [a for a in sys.argv[1:] if not a.startswith('--')]
if '--report' in sys.argv: args.remove(sys.argv[sys.argv.index('--report') + 1])
gen, out, extras = args[0], args[1], args[2:]
src = open(gen).read()
names = set()
for e in extras:
    names |= set(re.findall(r'^(?:EMSCRIPTEN_KEEPALIVE )?[\w ]+?\s\**(__asm_\w+)\(', open(e).read(), re.M))
kept, dropped = [], []
for line in src.split('\n'):
    m = re.match(r'^EMSCRIPTEN_KEEPALIVE .*?\b(__asm_\w+)\(', line)
    if m and m.group(1) in names:
        dropped.append(m.group(1))
        continue
    kept.append(line)
text = '\n'.join(kept)
FF = 'static int m11_simd_unimpl_once(const char* n) { fprintf(stderr, "[icall][FAIL-FAST] unimplemented SIMD helper %s\\n", n); abort(); return 0; }'
text, n_fix = re.subn(r'^static int m11_simd_unimpl_once\(const char\* n\) \{.*\}$', lambda m: FF, text, flags=re.M)
remaining = sorted(set(re.findall(r'm11_simd_unimpl_once\("(__asm_\w+)"\)', text)))
open(out, 'w').write(text)
rep = {'extra_names': len(names), 'stubs_replaced_by_extra': len(dropped), 'fail_fast_installed': n_fix, 'remaining_unimpl_stubs': remaining}
if '--report' in sys.argv:
    json.dump(rep, open(sys.argv[sys.argv.index('--report') + 1], 'w'), indent=1)
print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in rep.items()}))
