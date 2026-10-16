# PERF-P28 (#5403): 全ての call 命令の直後に、call site id を ring に積み、vtable (0x30203BD0) 先頭語を検査する。
# 記録先 (ctor_call_window.mjs が読む):
#   0x35F81008: call 戻りの通算回数 (CNT)・0x35F82000: site id の ring (1024 entry)
#   0x35F81004: vtable 先頭語が 0 を最初に観測した時点の CNT (DET)
#   wasm2wat tools/ott/work/lift/ottl.wasm -o <in.wat>
#   python3 tools/perf/p15/instr_calls.py <in.wat> <out.wat> <sites.json>
#   wat2wasm <out.wat> -o <out.wasm>
import json
import re
import sys

src, out, sites_path = sys.argv[1], sys.argv[2], sys.argv[3]
VT = 0x30203BD0
DET = 0x35F81004
CNT = 0x35F81008
RING = 0x35F82000
CHK = (
    '  (func $vtchk (param i32)\n'
    f'    i32.const {CNT}\n    i32.const {CNT}\n    i32.load\n    i32.const 1\n    i32.add\n    i32.store\n'
    f'    i32.const {RING}\n    i32.const {CNT}\n    i32.load\n    i32.const 1023\n    i32.and\n'
    '    i32.const 2\n    i32.shl\n    i32.add\n    local.get 0\n    i32.store\n'
    f'    i32.const {DET}\n    i32.load\n    i32.eqz\n'
    '    if\n'
    f'      i32.const {VT}\n      i32.load\n      i32.eqz\n'
    '      if\n'
    f'        i32.const {DET}\n        i32.const {CNT}\n        i32.load\n        i32.store\n'
    '      end\n'
    '    end)\n'
)
lines = open(src).read().split('\n')
func_re = re.compile(r'^  \(func \(;(\d+);\)')
call_re = re.compile(r'^(\s*)call (\d+)\s*$')
res = []
sites = {}
func = None
site = 0
for l in lines:
    if l.startswith('  (memory (;0;)'):
        res.append(CHK.rstrip('\n'))
    m = func_re.match(l)
    if m:
        func = int(m.group(1))
    res.append(l)
    cm = call_re.match(l)
    if cm and func is not None:
        site += 1
        sites[site] = {'caller': func, 'callee': int(cm.group(2))}
        res.append(f'{cm.group(1)}i32.const {site}')
        res.append(f'{cm.group(1)}call $vtchk')
open(out, 'w').write('\n'.join(res))
json.dump(sites, open(sites_path, 'w'))
print('call sites', site)
