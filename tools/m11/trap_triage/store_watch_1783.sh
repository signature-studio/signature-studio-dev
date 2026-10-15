#!/usr/bin/env bash
# #1783: wasm 側で 410320 の間接 call スロット (wasm 番地 0x1ac308 = native VA 0x5ac308) への書込みを全 store 計装で捕まえる.
#   watch_addr_1046.c の固定番地版を M11_WATCH_ADDR で差し替えて使う (監視は読取りのみ・IR の値と分岐は不変).
#   usage: [M11_FIX_682=0|1] [ALLOCA_SKIP=0|1] [M11_WATCH_SRC=trap_triage/watch_addr_2769.c] [M11_SW_LIMIT=n] store_watch_1783.sh <tag>  (survey は全 unit を順に実行する)
#   M11_WATCH_SRC: 監視の C 版 (既定 watch_addr_1046.c。#2769 の site 上限版 watch_addr_2769.c を選ぶと、上限超過の unit だけ trap する)。M11_SW_LIMIT は 2769 版の上限。
#   出力: work/probe1783/<tag>.aw (`unit N [aw] ...` 行 = 書込み検出), work/probe1783/<tag>.err (進捗 `unit N` 行), work/probe1783/sites.json, work/probe1783/<tag>.out (survey 結果)
#   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し sw1783.o / ov.o を消す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
: "${EMSDK_ENV:?EMSDK_ENV を設定してください ([EMSDK]・docs/REFERENCES.md §4)}"
source "$EMSDK_ENV" > /dev/null 2>&1
W=${M11_WATCH_1783:-0x1ac308}
FIX=${M11_FIX_682:-1}   # #2769: m11_ov.c の既定 (1) と揃える。0 だと計装版だけ別の ov.o になる (計測対象が base と違う)
WSRC=${M11_WATCH_SRC:-trap_triage/watch_addr_1046.c}   # #2769: 監視の C 版 (2769 版の再現は M11_WATCH_SRC=trap_triage/watch_addr_2769.c)
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
tag=$1
restore() { rm -f work/obj/sw1783.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe1783
ALLOCA_SKIP=${ALLOCA_SKIP:-1} python3 trap_triage/watch_store_682.py --out work/probe1783 || exit 1   # #2769: スタックスロット直接の store は計装しない (REPORT_1783 §8)
emcc -c work/probe1783/boot_sw.ll -o work/obj/boot.o $CF || exit 1
emcc -c "$WSRC" -o work/obj/sw1783.o $CF -DM11_WATCH_ADDR=$W ${M11_SW_LIMIT:+-DM11_SW_LIMIT=$M11_SW_LIMIT} || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=$FIX -DM11_NOTIFY_682=0 || exit 1
bash m11_build.sh > work/probe1783/build_$tag.log 2>&1 || { tail -5 work/probe1783/build_$tag.log; exit 1; }
SV_PROG=1 SV_ERR_LOG=work/probe1783/$tag.aw node trap_triage/survey_units.mjs work/probe1783/$tag.json > work/probe1783/$tag.out 2> work/probe1783/$tag.err || { echo "[store_watch_1783] survey failed (rc=$?)" >&2; exit 1; }
grep -a -o "^SURVEY_UNITS .\{0,160\}" work/probe1783/$tag.out   # #2769: survey_units.mjs の出力行 (旧 M11_SURVEY は実出力に無く常に空だった)
{ grep -a -c "\[aw\] " work/probe1783/$tag.aw || true; } | sed 's/^/[aw] hits: /'   # #2769: 0 件のときも rc 0 (pipefail 下で grep の rc 1 を伝えない)
