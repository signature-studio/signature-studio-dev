#!/usr/bin/env bash
# #2203 (M11-N144): unit 158 の j=12 が読む 2 区間の OFF/ON 比較 (dest 値・412c20 前後の指紋・ok/trap)。
#   usage: bash trap_triage/dest_2203.sh <off|on> <out_dir>
#   計装は読取りのみ (M11_PRINT_DEST_2118=1・M11_INSTR_413060=0 = probe 無し)。ON は m11_ov.c の C 版、OFF は dest_2203.py が
#   boot_final3.ll に同名の観測呼出しを入れた boot.o を使う。同じ build で 2 回実行し、出力が一致するか見る (決定性)。
#   出力: <out_dir>/<mode>_run1.txt・<mode>_run2.txt。終了時に boot.o を消して既定 build を作り直す。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
MODE=${1:?off|on}; OUT=${2:?out_dir}
case "$MODE" in off) GATE=0;; on) GATE=1;; *) echo "mode off|on"; exit 2;; esac
mkdir -p "$OUT" work/probe2203
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -I."
restore() { rm -f work/obj/boot.o; touch work/boot_final3.ll; M11_OV_413060=0 M11_INSTR_413060=0 M11_DEST_READ=1 bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT

B="M11_PRINT_DEST_2118=1 M11_OV_413060=$GATE M11_INSTR_413060=0 M11_DEST_READ=1"
env $B bash m11_build.sh > "$OUT/build_$MODE.log" 2>&1 || { tail -5 "$OUT/build_$MODE.log"; exit 1; }
if [ "$MODE" = off ]; then
  python3 trap_triage/dest_2203.py work/boot_final3.ll work/probe2203/boot_pd.ll || exit 1
  emcc -c work/probe2203/boot_pd.ll -o work/obj/boot.o $CF || exit 1
  env M11_KEEP_BOOT_O=1 $B bash m11_build.sh > "$OUT/build_${MODE}_pd.log" 2>&1 || { tail -5 "$OUT/build_${MODE}_pd.log"; exit 1; }
fi
for R in 1 2; do
  S=$(date +%s%N); L=$(cut -d' ' -f1 /proc/loadavg)
  M11_DIR="$HERE" OUT_LOG="$OUT/${MODE}_run$R.txt" node trap_triage/run_dest_2203.mjs 0,1,158 > "$OUT/${MODE}_run$R.stderr" 2>&1
  RC=$?
  echo "[dest_2203] $MODE run$R rc=$RC elapsed_ms=$(( ($(date +%s%N) - S) / 1000000 )) load_start=$L"
done
cmp -s "$OUT/${MODE}_run1.txt" "$OUT/${MODE}_run2.txt" && echo "[dest_2203] $MODE run1==run2" || echo "[dest_2203] $MODE run1!=run2"
grep -E '^(RES|\[d413060\]|\[r2118\])' "$OUT/${MODE}_run1.txt" | head -120
