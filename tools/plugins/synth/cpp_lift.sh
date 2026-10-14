#!/usr/bin/env bash
# MSVC C++ の x64 DLL (engine / 単体本体) の全 .pdata 関数を RetDec+pass 鎖で lift → emcc -c (到達性のみ; 正しさは別)
#   bash tools/plugins/synth/cpp_lift.sh <block> [timeout_sec]
# RetDec は IR (.ll) を出力した後に C (HLL) 生成へ進むが、後段の pass 鎖は .ll しか使わない。 巨大 DLL (Morphine) では HLL 生成が終わらないため、
#   e.drc.ll の最終更新から HLL_CAP 秒 (既定 300) 経っても RetDec が生きていれば RetDec だけを kill し、後段 pass 鎖を .ll から再開する
#   (kill した場合は summary.csv 末尾の hll_killed_s にその時点の経過秒、しなければ 0)。 RESUME=1 なら RetDec を呼ばず既存の e.drc.ll から再開。
#   再開は lift/lift_ranges.sh を PLUG_REUSE_DRC=1 で直接呼び、既存の e.drc.ll から後段だけを回す (RetDec は飛ばす。本体の更新にそのまま追従する)。
# 出力: work/synth/cpp<block>/ と summary.csv の 1 行:
#   block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,i256_trap,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines,hll_killed_s
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"; TMO="${2:-2400}"
# C++ DLL 9 本 (#534) の結果列を #535 の fix_avx256 で変えない (shell 12 本だけが対象)。 resume / 通常の両経路に効く
export PLUG_AVX256="${PLUG_AVX256:-0}"
# 21202 のみ E3 修復 (fix_i32_ptr_arg.py の opt-in; #1509)。 他の block は従来どおり修復無し
if [ "$B" = 21202 ]; then export PLUG_I32PTR_FUNCS="${PLUG_I32PTR_FUNCS:-function_180049450 function_180056120 function_1800599bc}"; fi
# 21202 のみ名前 define 2 件の function_<VA> 正規化 (#1537; PLUG_NAME_DEFS は lift_ranges.sh の既定 0 のまま)。 他の block は従来どおり
if [ "$B" = 21202 ]; then export PLUG_NAME_DEFS="${PLUG_NAME_DEFS:-1}"; fi
OUT="work/synth/cpp$B"
HLLCAP="${HLL_CAP:-300}"
resume_lift() {
  PLUG_REUSE_DRC=1 bash lift/lift_ranges.sh "$PE" "$OUT/ranges.txt" "$OUT" e "$TMO" > "$OUT/lift.log" 2>&1
}
if [ "${RESUME:-0}" = 1 ]; then
  [ -f "$OUT/e.drc.ll" ] || { echo "RESUME=1 だが $OUT/e.drc.ll が無い" >&2; exit 2; }
  rm -f "$OUT"/e.[!d]*.ll "$OUT"/e.final.ll "$OUT"/summary.csv
  mkdir -p "$OUT/tmp"
else
  rm -rf "$OUT"; mkdir -p "$OUT/tmp"
fi
python3 synth/engine_ranges.py "$B" > "$OUT/ranges.txt" 2> "$OUT/ranges.info"
PE="$FL_WIN64_DIR/extracted/block$(printf %05d "$B")_PE.bin"
t0=$(date +%s)
killed=0
if [ "${RESUME:-0}" = 1 ]; then
  resume_lift
  rc=$?
else
  bash lift/lift_ranges.sh "$PE" "$OUT/ranges.txt" "$OUT" e "$TMO" > "$OUT/lift.log" 2>&1 &
  lp=$!
  while kill -0 "$lp" 2>/dev/null; do
    if [ -f "$OUT/e.drc.ll" ] && [ $(( $(date +%s) - $(stat -c %Y "$OUT/e.drc.ll") )) -gt "$HLLCAP" ]; then
      killed=$(( $(date +%s) - t0 ))
      for p in $(pgrep -f "retdec-decompiler $PE"); do kill "$p" 2>/dev/null || true; done
      break
    fi
    sleep 3
  done
  wait "$lp"; rc=$?
  if [ "$killed" != 0 ]; then
    resume_lift
    rc=$?
  fi
fi
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
echo "$B,$(cut -d' ' -f1 "$OUT/ranges.info"),$rc,$DEF,$F80,$UNI,$I256,$erc,$NP,$erc2,$((t1-t0)),$DEFS,$killed" | tee "$OUT/summary.csv"
