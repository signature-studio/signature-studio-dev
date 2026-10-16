# PERF-P28 (#5403): wasm func 75 の memory.fill の直前に、[dest, val, n] をそのまま返すチェッカを挟む。
# dest..dest+n が vtable (0x30203BD0・64 byte) に重なれば LOG に記録する。
#   wasm2wat tools/ott/work/lift/ottl.wasm -o <in.wat>
#   python3 tools/perf/p15/instr_fill.py <in.wat> <out.wat>
#   wat2wasm <out.wat> -o <out.wasm>
#   node tools/perf/p15/ctor_fill_watch.mjs <out.wasm>
# LOG = 0x35F84000: +0 重なった回数 / +4 dest / +8 n (最初に重なったときの値)
import sys

src, out = sys.argv[1], sys.argv[2]
VT = 0x30203BD0
LOG = 0x35F84000
ANCHOR = '      local.get 1\n      i32.const 0\n      local.get 3\n      memory.fill\n'
CHK = (
    '  (func $mfchk (param i32 i32 i32) (result i32 i32 i32)\n'
    f'    local.get 0\n    local.get 2\n    i32.add\n    i32.const {VT}\n    i32.gt_u\n'
    f'    local.get 0\n    i32.const {VT + 64}\n    i32.lt_u\n'
    '    i32.and\n'
    '    if\n'
    f'      i32.const {LOG}\n      i32.const {LOG}\n      i32.load\n      i32.const 1\n      i32.add\n      i32.store\n'
    f'      i32.const {LOG + 4}\n      local.get 0\n      i32.store\n'
    f'      i32.const {LOG + 8}\n      local.get 2\n      i32.store\n'
    '    end\n'
    '    local.get 0\n    local.get 1\n    local.get 2)\n'
)
text = open(src).read()
assert text.count(ANCHOR) == 1, text.count(ANCHOR)
text = text.replace(ANCHOR, '      local.get 1\n      i32.const 0\n      local.get 3\n      call $mfchk\n      memory.fill\n')
assert text.count('call $mfchk') == 1
tail = text.rindex('\n  (table ')
text = text[:tail] + '\n' + CHK + text[tail + 1:]
open(out, 'w').write(text)
print('ok')
