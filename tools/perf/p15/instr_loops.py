# PERF-P28 (#5403): ottl.wat の全 loop 先頭に実行回数カウンタと budget (0 で unreachable) を差し込む。
#   wasm2wat tools/ott/work/lift/ottl.wasm -o <in.wat>
#   python3 tools/perf/p15/instr_loops.py <in.wat> <out.wat>
#   wat2wasm <out.wat> -o tools/ott/work/lift/ottl_lc.wasm
# 計装後の loop 番号は、入力 wat の loop 出現順 (0 始まり)。ctor_loop_trace.mjs が読む counter 領域は 0x35f80100 以降。
import re
import sys

src, out = sys.argv[1], sys.argv[2]
CNT = 0x35F80100  # loop head ごとの実行回数 (u32 x 209)
BUD = 0x35F80000  # 残り budget (i32)
lines = open(src).read().split('\n')
res = []
n = 0
for l in lines:
    res.append(l)
    if re.match(r'^\s*loop\b', l):
        ind = re.match(r'^(\s*)', l).group(1) + '  '
        a = CNT + 4 * n
        res.append(f'{ind}i32.const {a}\n{ind}i32.const {a}\n{ind}i32.load\n{ind}i32.const 1\n{ind}i32.add\n{ind}i32.store')
        res.append(f'{ind}i32.const {BUD}\n{ind}i32.const {BUD}\n{ind}i32.load\n{ind}i32.const 1\n{ind}i32.sub\n{ind}i32.store')
        res.append(f'{ind}i32.const {BUD}\n{ind}i32.load\n{ind}i32.eqz\n{ind}if\n{ind}  unreachable\n{ind}end')
        n += 1
open(out, 'w').write('\n'.join(res))
print('loops', n)
