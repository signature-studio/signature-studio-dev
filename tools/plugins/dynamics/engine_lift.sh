#!/usr/bin/env bash
# engine 分離型 2 本 (T2) の C++ engine DLL 全 .pdata 関数を RetDec+pass 鎖で lift → emcc -c (到達性のみ; 正しさは別)
#   bash tools/plugins/dynamics/engine_lift.sh <block> [timeout_sec]      例: 19252 (Transient Processor engine) / 19048 (Multiband Compressor comp_eng)
# 出力: work/dynamics/engine<block>/ と 1 行サマリ (block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"; TMO="${2:-1200}"
OUT="work/dynamics/engine$B"; mkdir -p "$OUT/tmp"
python3 dynamics/engine_ranges.py "$B" > "$OUT/ranges.txt" 2> "$OUT/ranges.info"
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
erc=-1; erc2=-1; NP=0
emcc_c() { ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$1" -o "$OUT/e.o" -w -O0 -msimd128 > "$2" 2>&1 ); echo $?; }
if [ -f "$OUT/e.final.ll" ]; then
  erc=$(emcc_c "$OUT/e.final.ll" "$OUT/emcc.log")
  # engine-local 修復 (icmp ptr/i64 型不整合) を当てた後の再試行。 clang は最初の型エラーで止まるため、次に露見する欠陥類型を記録する
  NP=$(python3 dynamics/engine_fixcmp.py "$OUT/e.final.ll" "$OUT/e.fixcmp.ll" 2>&1 | sed 's/.*= //')
  erc2=$(emcc_c "$OUT/e.fixcmp.ll" "$OUT/emcc_fixcmp.log")
  { echo "[final.ll]"; grep -m1 'error' "$OUT/emcc.log" || true; echo "[fixcmp.ll]"; grep -m1 'error' "$OUT/emcc_fixcmp.log" || true; } > "$OUT/first_errors.txt"
fi
echo "$B,$(cut -d' ' -f1 "$OUT/ranges.info"),$rc,$DEF,$F80,${UNI:--1},$erc,$NP,$erc2,$((t1-t0))" | tee "$OUT/summary.csv"
