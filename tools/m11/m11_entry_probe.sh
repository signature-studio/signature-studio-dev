#!/usr/bin/env bash
# #1894: _CopyArray (416db0) の呼出し元関数の実行時到達を survey で判定する (計測専用).
#   usage: m11_entry_probe.sh <out_dir> [SV_ONLY (省略 = 全 unit)]
#   対象 entry: 12a3ff0 417110 417b70 418030 418280 4183d0 418700 (site 1・4〜11 の呼出し元)
#   出力: <out_dir>/entry.out (SURVEY_UNITS), <out_dir>/entry.json (unit 別 kind), <out_dir>/fe.tsv (unit 別の到達フラグ)
#   終了時に probe 版 boot.o を消して m11_build.sh で既定 build に戻す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; cd "$HERE"
OUT="${1:?out_dir}"; only="${2:-}"
FNS=12a3ff0,417110,417b70,418030,418280,4183d0,418700,416750
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
restore() { rm -f work/obj/entry_probe.o; touch work/boot_final3.ll; rm -f work/obj/boot.o; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p "$OUT"
python3 m11_entry_probe.py work/boot_final3.ll "$OUT/boot_entry.ll" --fns "$FNS" --table "$OUT/entry_table.json" || exit 1
emcc -c "$OUT/boot_entry.ll" -o work/obj/boot.o $CF || exit 1
emcc -c m11_entry_probe_rt.c -o work/obj/entry_probe.o $CF || exit 1
touch work/boot_final3.ll
M11_ENTRY_PROBE=1 M11_KEEP_BOOT_O=1 bash m11_build.sh > "$OUT/build.log" 2>&1 || { tail -5 "$OUT/build.log"; exit 1; }
[ -n "$only" ] && export SV_ONLY="$only"
node trap_triage/survey_entry.mjs "$OUT/entry.json" > "$OUT/entry.out" 2>&1
grep -a SURVEY_ENTRY "$OUT/entry.out"
