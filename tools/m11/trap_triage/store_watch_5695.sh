#!/usr/bin/env bash
# #5695: e3ef60 の arg1 (0x12ba808) の +0x778〜+0x814 への書込みを、IR store (watch_arg1_5695.c・`[a1]`)・
#   copy 関数 409c80 の入口 (`[a1cp]`)・rep 系 helper の入口 (`[a1rp]`) の 3 経路で全 unit (survey) に対して監視する.
#   store_watch_1783.sh の派生。監視は読取りのみ (IR の値・分岐は不変)。C の runtime (m11_rt/m11_win) 内の直接 store は映らない。
#   usage: store_watch_5695.sh <tag>   (前提: 素材 work-m11 を展開済み・EMSDK_ENV を設定 (既定 /opt/emsdk/emsdk_env.sh))
#   出力: work/probe5695/<tag>.err (`[a1]` `[a1cp]` `[a1rp]` 行), work/probe5695/<tag>.out (survey 結果), work/probe5695/sites.json
#   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し、計装の .o を消す (trap で必ず復元)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" > /dev/null 2>&1   # [EMSDK] (docs/REFERENCES.md)
LO=${WATCH_LO:-0x12ba808}   # 陽性対照では WATCH_LO=0x10aa1428 WATCH_SPAN=32 のように差し替える
SPAN=${WATCH_SPAN:-$((0x814 - 0x778))}
BASE=${WATCH_BASE:-0x778}
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -DM11_WATCH_LO=${LO}+${BASE} -DM11_WATCH_HI=${LO}+${BASE}+${SPAN} -I."
tag=${1:?tag}
restore() { rm -f work/obj/sw5695.o work/obj/cp5695.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
[ -f work/boot_final3.ll ] || { echo "work/boot_final3.ll が無い (bash m11_gen_ir2.sh を先に実行)"; exit 1; }
mkdir -p work/probe5695
ALLOCA_SKIP=1 python3 trap_triage/watch_store_682.py --out work/probe5695 || exit 1
python3 trap_triage/copy_watch_3972.py work/probe5695/boot_sw.ll work/probe5695/boot_sw_cp.ll || exit 1
python3 trap_triage/rep_watch_3972.py work/probe5695/boot_sw_cp.ll work/probe5695/boot_sw_rp.ll work/probe5695/rep_sites.txt || exit 1
mv work/probe5695/boot_sw_rp.ll work/probe5695/boot_sw_cp.ll
emcc -c work/probe5695/boot_sw_cp.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_arg1_5695.c -o work/obj/sw5695.o $CF || exit 1
emcc -c trap_triage/watch_copy_5695.c -o work/obj/cp5695.o $CF || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=1 -DM11_NOTIFY_682=0 || exit 1
bash m11_build.sh > work/probe5695/build_$tag.log 2>&1 || { tail -5 work/probe5695/build_$tag.log; exit 1; }
SV_PROG=1 SV_ERR_LOG=work/probe5695/$tag.aw node trap_triage/survey_units.mjs work/probe5695/$tag.json > work/probe5695/$tag.out 2> work/probe5695/$tag.err || { echo "[store_watch_5695] survey failed (rc=$?)" >&2; exit 1; }
grep -a -o "^SURVEY_UNITS .\{0,160\}" work/probe5695/$tag.out
for p in '\[a1\] ' '\[a1cp\] ' '\[a1rp\] '; do printf '%s hits: ' "$p"; { grep -a -c "$p" work/probe5695/$tag.err || true; }; done
