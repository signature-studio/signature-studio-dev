#!/usr/bin/env bash
# C++ engine DLL (FL Studio Mobile 系) の .pdata 窓 3 か所 (先頭 / 1/3 / 2/3 位置から各 N 関数) を RetDec+pass 鎖で lift → emcc -c (到達性のみ; 全関数ではない)
#   bash tools/plugins/hostx/engine_sample.sh <block> [N=300] [timeout_sec=900]
# 出力: work/hostx/eng<block>_w<k>/ と 窓ごとに 1 行 (block,window,start_index,funcs,bytes,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,lift_s,first_error)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"; N="${2:-300}"; TMO="${3:-900}"
TOT=$(python3 hostx/engine_window.py "$B" 0 1 2>&1 >/dev/null | awk '{print $1}')
for k in 0 1 2; do
  S=$(( TOT * k / 3 ))
  OUT="work/hostx/eng${B}_w$k"; rm -rf "$OUT"; mkdir -p "$OUT/tmp"
  python3 hostx/engine_window.py "$B" "$S" "$N" > "$OUT/ranges.txt" 2> "$OUT/ranges.info"
  t0=$(date +%s)
  bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d "$B")_PE.bin" "$OUT/ranges.txt" "$OUT" e "$TMO" > "$OUT/lift.log" 2>&1
  rc=$?
  t1=$(date +%s)
  DEF=$(grep -c '^define' "$OUT/e.final.ll" 2>/dev/null || echo 0)
  UNI=$(grep -o 'unimplemented [0-9]*' "$OUT/e.simd.log" 2>/dev/null | awk '{print $2}' | head -1)
  F80=$(python3 - "$OUT/e.final.ll" <<'PY'
import re, sys
try:
    s = open(sys.argv[1]).read()
except Exception:
    print(-1); sys.exit()
print(sum(1 for f in re.split(r'\n(?=define )', s) if f.startswith('define') and 'x86_fp80' in f))
PY
)
  erc=-1; ERR=""
  if [ -f "$OUT/e.final.ll" ]; then
    ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$OUT/e.final.ll" -o "$OUT/e.o" -w -O0 -msimd128 > "$OUT/emcc.log" 2>&1 ); erc=$?
    ERR=$(grep -m1 'error' "$OUT/emcc.log" | cut -c1-120 | tr ',' ';')
  fi
  echo "$B,w$k,$S,$(cut -d' ' -f4 "$OUT/ranges.info"),$(cut -d' ' -f8 "$OUT/ranges.info"),$rc,$DEF,$F80,${UNI:--1},$erc,$((t1-t0)),$ERR" | tee "$OUT/summary.csv"
done
