#!/usr/bin/env bash
# #856: unit 56 の 8c5eb0 fail-fast 辺 (件数0 ∧ arg3==0 ∧ arg2下位byte≠0 → llvm.trap) の到達可否を実測する.
# 判定: (1) unit 56 の trap が wasm-function[TRAP_FN] (8c5eb0 の fail-fast) を通るか
#       (2) 全 trap unit のうち同 frame を通る unit の数 (他に到達する unit が無いか)
# 前提: work/boot_final.ll と work/ir_conditions.json (m11_gen_ir2.sh), m11_build.sh 済み, FL_WIN64_DIR 設定済み.
set -u
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$HERE"
OUT=work/v856
TRAP_FN=${TRAP_FN:-3471}
mkdir -p "$OUT"
M11_SURVEY_UNITS="$OUT/units_all.json" timeout 600 node m11_survey.mjs > "$OUT/survey_all.out" 2> "$OUT/stack_all.txt" || { echo "FAIL: survey rc!=0"; exit 1; }
grep '^M11_SURVEY ' "$OUT/survey_all.out" | cut -c1-200
T=$(python3 -c "import json,sys;u=json.load(open('$OUT/units_all.json'));print(','.join(str(i) for i,x in enumerate(u) if x in('trap','oom')))")
M11_SURVEY_STACK="$T" M11_SURVEY_UNITS="$OUT/units_all2.json" timeout 900 node m11_survey.mjs > "$OUT/survey_stack.out" 2> "$OUT/stack_trapped.txt" || { echo "FAIL: stack survey rc!=0"; exit 1; }
python3 - "$OUT/stack_trapped.txt" "$TRAP_FN" <<'PYEOF'
import sys
path, fn = sys.argv[1], sys.argv[2]
blocks = []; cur = None
for line in open(path):
    if line.startswith('[survey][stack] unit'):
        cur = [line.strip()]; blocks.append(cur)
    elif cur is not None and line.startswith('    at '):
        cur.append(line.strip())
hits = [b[0] for b in blocks if any(f'wasm-function[{fn}]' in x for x in b[1:])]
print(f'trapped units with stack={len(blocks)} / through wasm-function[{fn}] = {len(hits)}')
for h in hits: print('  HIT', h[:110])
PYEOF
