#!/bin/bash
# SR-2b authstub E2E: lift → 中性化 pass → base 修復 → liftfix → wasm ハーネス → 検証一式。
# 再現: bash tools/targets/serum2/license/authstub/e2e.sh
# (RetDec lift は work/lift/authstub.drc.ll があれば再利用、無ければ ~30s で生成)
set -e
cd "$(dirname "$0")"
source ../../../../shared/env.sh
W=work
mkdir -p $W/lift $W/tmp
PE=../../work/Serum2_win64.vst3
LIFT=$W/lift/authstub.drc.ll

echo "== [1] RetDec lift (select-ranges: setState x2 + funclet + getState + process) =="
if [ ! -f "$LIFT" ]; then
  TMPDIR=$W/tmp /opt/retdec/bin/retdec-decompiler "$PE" -o $W/lift/authstub.drc.c \
    --select-ranges "0x18004fad0-0x18004ffbf,0x18004ffc0-0x1800500db,0x1800c2b50-0x1800c2f99,0x1800c6090-0x1800c69b2,0x180056670-0x18005a71e" \
    --select-decode-only --timeout 1800 2>&1 | tail -1
  rm -f $W/lift/authstub.drc.dsm $W/lift/authstub.drc.bc
fi
[ -f "$LIFT" ] || { echo "lift 失敗"; exit 1; }

echo "== [2] 中性化 IR pass (N1/N2a/N2b/N3) + 到達性 check =="
python3 authstub_irpass.py "$LIFT" $W/patched.ll --report $W/irpatch_report.json --check

echo "== [3] base 修復 (liftlib ライブラリ利用, 無改変) — patched / raw の両方 =="
python3 - <<'EOF'
import sys
import os
sys.path.insert(0, os.environ['REPO_ROOT'] + '/tools/liftlib')
from liftlib.passes import base as B
for src, dst in (('work/patched.ll', 'work/patched_base.ll'),
                 ('work/lift/authstub.drc.ll', 'work/raw_base.ll')):
    text = open(src).read()
    out, rep = B.run_base(text, B.make_args(infile=src, outfile=dst))
    open(dst, 'w').write(out)
    print(dst, {k: v for k, v in rep.items() if k in ('b1_fixed', 's1_stores', 'a9_residual_constexpr')})
EOF

echo "== [4] liftfix (LF1-LF7: 実行ハーネス用束縛) =="
python3 authstub_irpass.py $W/patched_base.ll $W/patched_base_lf.ll --liftfix --report $W/liftfix_report.json
python3 authstub_irpass.py $W/raw_base.ll $W/raw_base_lf.ll --liftfix

echo "== [5] N4 確認: process (0x180056670) / funclet (0x18004ffc0) は 1 行も非変更 =="
python3 - <<'EOF'
import re
def fn_of(path):
    lines = open(path).read().splitlines()
    out, cur = {}, None
    for i, l in enumerate(lines):
        if l.startswith('define'):
            m = re.search(r'@function_([0-9a-f]+)', l)
            cur = (m.group(1), i)
        elif l.startswith('}') and cur:
            out[cur[0]] = lines[cur[1]:i + 1]
            cur = None
    return out
a = fn_of('work/lift/authstub.drc.ll')
b = fn_of('work/patched.ll')
for f in ('180056670', '18004ffc0'):
    assert a[f] == b[f], f'function_{f} が変更されている'
changed = sorted(f for f in a if a[f] != b[f])
print('N4 OK: process/funclet identical; changed fns =', changed)
assert changed == ['18004fad0', '1800c2b50', '1800c6090'], changed
EOF

echo "== [6] 定数領域抽出 (PE 実バイト) + 実行モジュール合成 =="
python3 mkrun_merge.py $W/run_all.ll \
  $W/patched_base_lf.ll:1800c2b50 \
  $W/raw_base_lf.ll:1800c2b50:function_1800c2b50_pre \
  $W/patched_base_lf.ll:18004fad0
python3 data_globals_gen.py $W/run_all.ll "$PE" $W/dg_all.c

echo "== [7] emcc → wasm → node ハーネス =="
export EMSDK=/opt/emsdk
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc -w -O1 -sENVIRONMENT=node -sMODULARIZE=1 -sALLOW_MEMORY_GROWTH=1 \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -sEXPORTED_FUNCTIONS=_authstub_ctrl_case,_authstub_dsp_case,_malloc \
  -o $W/h_all.cjs $W/run_all.ll harness/authstub_harness.c $W/dg_all.c
node harness/authstub_harness.mjs $W/h_all.cjs --report $W/harness_report.json
