#!/usr/bin/env bash
# lift_closure_x64c.sh — 対照 Gain の before 160 閉包を x64c で lift し、emcc の compile・link・smoke まで通す (#850 / KH-19d)。
#   usage: KH_CORE=<HeartCore.core_64 のパス> OUT=<出力先 (repo 外)> [EMSDK=<emsdk のルート>] bash scripts/lift_closure_x64c.sh
#   入力: gain_before_160.tsv の root 行 (root_class が空でない 27 行) を roots とする。
#   出力: $OUT/lift/ (lift 結果 C・fle_data.c・kh.cjs・kh.wasm)、$OUT/compile.log・link.log・smoke.log。
#   前提: python3 (pefile, capstone)・emcc (未設定なら EMSDK の emsdk_env.sh を読む)・node。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
KH="$(cd -- "$HERE/.." && pwd)"
FLE="$(cd -- "$KH/../../flelift" && pwd)"
CORE="${KH_CORE:?HeartCore.core_64 のパスを KH_CORE で指定}"
OUT="${OUT:?出力先を OUT で指定 (repo 外)}"
IMG=0x180000000
SIZE=0x625c000
SHIFT=0x17E000000
GAIN_VA=0x1804b0380
TSV="$KH/gain_before_160.tsv"
LIFT="$OUT/lift"
mkdir -p "$LIFT"
if ! command -v emcc >/dev/null 2>&1 && [ -n "${EMSDK:-}" ]; then source "$EMSDK/emsdk_env.sh" >/dev/null 2>&1; fi

python3 - "$TSV" "$OUT/entries.json" "$IMG" <<'EOF'
import json, sys
rows = [l.split('\t') for l in open(sys.argv[1]).read().splitlines()[1:]]
base = int(sys.argv[3], 16)
roots = [base + int(r[0], 16) for r in rows if r[2]]
json.dump({'roots': roots}, open(sys.argv[2], 'w'))
print('roots', len(roots))
EOF

time python3 "$FLE/x64c.py" --pe "$CORE" --entries "$OUT/entries.json" --out "$LIFT" --closure 60 \
  --img "$IMG" --shift "$SHIFT" --img-size "$SIZE" --impbase 0x1D80000 | tail -c 400
python3 "$FLE/fle_data_gen.py" "$CORE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json" "$SHIFT"

RT="$FLE/rt"
emcc -c -O0 -ffp-contract=off -fno-fast-math -I "$RT" "$LIFT/fle_lifted.c" -o /dev/null > "$OUT/compile.log" 2>&1
echo "compile: warnings=$(grep -c 'warning:' "$OUT/compile.log") errors=$(grep -c 'error:' "$OUT/compile.log")"

EXPORTS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc
time emcc -O0 -ffp-contract=off -fno-fast-math -I "$RT" "$LIFT/fle_lifted.c" "$LIFT/fle_data.c" \
  "$RT/fle_cpu.c" "$RT/fle_glue.c" -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) -o "$LIFT/kh.cjs" > "$OUT/link.log" 2>&1
ls -la "$LIFT/kh.wasm" | awk '{print "wasm bytes:", $5}'

ENTRY=$(printf '0x%x' $((GAIN_VA - SHIFT)))
cat > "$OUT/smoke.cjs" <<EOF
const createModule = require('./lift/kh.cjs');
(async () => {
  const m = await createModule();
  const step = (name, f) => { try { const r = f(); console.log(name, 'ok', r === undefined ? '' : String(r)); } catch (e) { console.log(name, 'EXC', String(e).slice(0, 200)); } };
  step('init', () => m._fle_init());
  step('data_install', () => m._fle_data_install());
  step('fle_run(gain process, zero args)', () => m._fle_run($ENTRY, 0n, 0n, 0n, 0n, 0n, 0n, 0n, 0n));
})();
EOF
(cd "$OUT" && node smoke.cjs) | tee "$OUT/smoke.log"
N_OK=$(grep -cw 'ok' "$OUT/smoke.log" || true)
N_EXC=$(grep -cw 'EXC' "$OUT/smoke.log" || true)
echo "smoke: ok=$N_OK (3 が成功) EXC=$N_EXC (0 が成功)"
if [ "$N_OK" != 3 ] || [ "$N_EXC" != 0 ]; then echo "smoke: 失敗" >&2; exit 1; fi
