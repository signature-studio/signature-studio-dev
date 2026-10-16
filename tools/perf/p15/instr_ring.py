# PERF-P28 (#5403): ottl.wat の各 func 本体の先頭 (local 宣言の後) に、関数入りの ring 記録を差し込む。
#   wasm2wat tools/ott/work/lift/ottl.wasm -o <in.wat>
#   python3 tools/perf/p15/instr_ring.py <in.wat> <out.wat>
#   wat2wasm <out.wat> -o <out.wasm>
# 記録先 (ctor_vtable_ring.mjs が読む):
#   0x35F81008: 関数入りの通算回数 (カウンタ) / 0x35F82000: ring (1024 entry, func 番号)
#   0x35F81004: vtable (0x30203BD0) 先頭語が 0 を最初に観測した時点の通算回数
# 入力は素材 work-m6-ott の ottl.wasm (sha e8fb06203811ff1f) を想定する。
import re
import sys

src, out = sys.argv[1], sys.argv[2]
VT = 0x30203BD0
DET = 0x35F81004
CNT = 0x35F81008
RING = 0x35F82000
lines = open(src).read().split('\n')
res = []
n = 0
pending = None
for l in lines:
    if pending is not None and not re.match(r'^\s*\((local|param|result)\b', l):
        ind, fn = pending
        res.append(
            f'{ind}i32.const {CNT}\n{ind}i32.const {CNT}\n{ind}i32.load\n{ind}i32.const 1\n{ind}i32.add\n{ind}i32.store\n'
            f'{ind}i32.const {RING}\n{ind}i32.const {CNT}\n{ind}i32.load\n{ind}i32.const 1023\n{ind}i32.and\n'
            f'{ind}i32.const 2\n{ind}i32.shl\n{ind}i32.add\n{ind}i32.const {fn}\n{ind}i32.store\n'
            f'{ind}i32.const {DET}\n{ind}i32.load\n{ind}i32.eqz\n{ind}if\n'
            f'{ind}  i32.const {VT}\n{ind}  i32.load\n{ind}  i32.eqz\n{ind}  if\n'
            f'{ind}    i32.const {DET}\n{ind}    i32.const {CNT}\n{ind}    i32.load\n{ind}    i32.store\n'
            f'{ind}  end\n{ind}end'
        )
        pending = None
        n += 1
    res.append(l)
    m = re.match(r'^(\s*)\(func \(;(\d+);\)', l)
    if m and l.count('(') != l.count(')'):
        pending = (m.group(1) + '    ', int(m.group(2)))
open(out, 'w').write('\n'.join(res))
print('funcs', n)
