#!/usr/bin/env bash
# MSVC C++ の x64 DLL (engine / 単体本体) の全 .pdata 関数を RetDec+pass 鎖で lift → emcc -c (到達性のみ; 正しさは別)
#   bash tools/plugins/synth/cpp_lift.sh <block> [timeout_sec]
# 出力: work/synth/cpp<block>/ と summary.csv の 1 行:
#   block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,i256_trap,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"; TMO="${2:-2400}"
OUT="work/synth/cpp$B"; rm -rf "$OUT"; mkdir -p "$OUT/tmp"
python3 synth/engine_ranges.py "$B" > "$OUT/ranges.txt" 2> "$OUT/ranges.info"
t0=$(date +%s)
bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d "$B")_PE.bin" "$OUT/ranges.txt" "$OUT" e "$TMO" > "$OUT/lift.log" 2>&1
rc=$?
t1=$(date +%s)
DEF=$(grep -c '^define' "$OUT/e.final.ll" 2>/dev/null || true); DEF=${DEF:--1}; [ -f "$OUT/e.final.ll" ] || DEF=-1
read -r UNI I256 < <(python3 synth/simd_stats.py "$OUT/e.simd.log")
F80=$(python3 synth/f80_count.py "$OUT/e.final.ll")
erc=-1; erc2=-1; NP=0
emcc_c() { ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$1" -o "$OUT/e.o" -w -O0 -msimd128 > "$2" 2>&1 ); echo $?; }
if [ -f "$OUT/e.final.ll" ]; then
  erc=$(emcc_c "$OUT/e.final.ll" "$OUT/emcc.log")
  # 局所修復 (icmp ptr/i64 型不整合) を当てた後の再試行。 clang は最初の型エラーで止まるため、次に露見する欠陥類型を記録する
  NP=$(python3 synth/engine_fixcmp.py "$OUT/e.final.ll" "$OUT/e.fixcmp.ll" 2>&1 | sed 's/.*= //')
  erc2=$(emcc_c "$OUT/e.fixcmp.ll" "$OUT/emcc_fixcmp.log")
  { echo "[final.ll]"; grep -m1 'error' "$OUT/emcc.log" || true; echo "[fixcmp.ll]"; grep -m1 'error' "$OUT/emcc_fixcmp.log" || true; } > "$OUT/first_errors.txt"
fi
DEFS=$(python3 synth/engine_defs.py "$OUT/ranges.txt" "$OUT/e.final.ll" 2>/dev/null || echo "-1,-1,-1,-1,-1")
echo "$B,$(cut -d' ' -f1 "$OUT/ranges.info"),$rc,$DEF,$F80,$UNI,$I256,$erc,$NP,$erc2,$((t1-t0)),$DEFS" | tee "$OUT/summary.csv"
