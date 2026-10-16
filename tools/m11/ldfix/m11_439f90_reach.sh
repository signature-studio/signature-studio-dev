#!/usr/bin/env bash
# #5715 (CI-238): function_439f90 の入口計数 (計測専用・opt-in).
#   usage: m11_439f90_reach.sh <out_dir>
#   前提: work/boot_final.ll が M11_FIX_439F90=1 で生成済み (ir_conditions.json 439f90=applied)。
#   出力: <out_dir>/reach.json (unit 別の入口計数 0/1), <out_dir>/reach.out (集計)
#   既定 build は変えない: 終了時に probe 版 boot.o を消し、m11_build.sh で既定 build に戻す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
OUT="${1:?out_dir}"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
restore() { rm -f work/obj/m11_439f90_probe_rt.o; touch work/boot_final3.ll; rm -f work/obj/boot.o; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p "$OUT"
# 入力は post 後の boot_final3.ll (probe_entry.py と同じ。boot_final.ll は weak 化前で ov.o と重複定義になる)
python3 ldfix/m11_439f90_probe_insert.py work/boot_final3.ll "$OUT/boot_439f90.ll" "$OUT/probe_table.json" || exit 1
emcc -c "$OUT/boot_439f90.ll" -o work/obj/boot.o $CF || exit 1
emcc -c ldfix/m11_439f90_probe_rt.c -o work/obj/m11_439f90_probe_rt.o $CF || exit 1
touch work/boot_final3.ll
M11_ENTRY_PROBE=1 M11_KEEP_BOOT_O=1 bash m11_build.sh > "$OUT/build.log" 2>&1 || { tail -5 "$OUT/build.log"; exit 1; }
node ldfix/m11_439f90_reach_survey.mjs "$OUT/reach.json" > "$OUT/reach.out" 2>&1
grep -a REACH_439F90 "$OUT/reach.out"
