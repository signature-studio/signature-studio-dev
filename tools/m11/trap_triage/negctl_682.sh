#!/usr/bin/env bash
# #682 ネガコン: m11_ov.c の function_47b260 転記 (M11_FIX_682=1 既定) を外した build (IR 原形 = D4 の欠陥あり) で
# chain_682.sh (各 unit 前の [[g+8]+8] と survey の判定) を走らせる. 終了時に ov.o を既定 build から再生成して復元する (trap).
#   usage: negctl_682.sh <tag>   → work/probe682/chain_<tag>.{err,out}
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
tag=$1
restore() { rm -f work/obj/ov.o; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe682
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=0 || exit 1
bash m11_build.sh > work/probe682/build_nc_$tag.log 2>&1 || { tail -5 work/probe682/build_nc_$tag.log; exit 1; }
bash trap_triage/chain_682.sh "$tag" || exit 1
