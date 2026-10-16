# PERF-P28 (#5403): wasm func 75 (calloc 形: malloc(262144) → memory.fill 0) の dest のうち、
# guest image (0x30000000〜0x30284124) を指すものを記録する。memory.fill の直前に挟むチェッカは動作を変えない。
# LOG = 0x35F86000: +0 image 内の呼び出し回数 / +4 + 4*k: k 番目の dest (最大 512 件)
#   wasm2wat tools/ott/work/lift/ottl.wasm -o <in.wat>
#   python3 tools/perf/p15/instr_calloc.py <in.wat> <out.wat>
#   wat2wasm <out.wat> -o <out.wasm>
#   node tools/perf/p15/ctor_calloc_image.mjs <out.wasm>
import sys

src, out = sys.argv[1], sys.argv[2]
LOG = 0x35F86000
ANCHOR = '      local.get 1\n      i32.const 0\n      local.get 3\n      memory.fill\n'
CHK = (
    '  (func $mflog (param i32 i32 i32) (result i32 i32 i32) (local i32)\n'
    f'    i32.const {LOG}\n    i32.load\n    local.set 3\n'
    '    local.get 0\n    i32.const 805306368\n    i32.ge_u\n'
    '    local.get 0\n    i32.const 807944484\n    i32.lt_u\n'
    '    i32.and\n'
    '    if\n'
    '      local.get 3\n      i32.const 512\n      i32.lt_u\n'
    '      if\n'
    f'        i32.const {LOG + 4}\n        local.get 3\n        i32.const 2\n        i32.shl\n        i32.add\n        local.get 0\n        i32.store\n'
    '      end\n'
    f'      i32.const {LOG}\n      local.get 3\n      i32.const 1\n      i32.add\n      i32.store\n'
    '    end\n'
    '    local.get 0\n    local.get 1\n    local.get 2)\n'
)
text = open(src).read()
assert text.count(ANCHOR) == 1, text.count(ANCHOR)
text = text.replace(ANCHOR, '      local.get 1\n      i32.const 0\n      local.get 3\n      call $mflog\n      memory.fill\n')
tail = text.rindex('\n  (table ')
text = text[:tail] + '\n' + CHK + text[tail + 1:]
open(out, 'w').write(text)
print('ok')
