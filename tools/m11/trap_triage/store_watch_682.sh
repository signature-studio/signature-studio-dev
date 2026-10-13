#!/usr/bin/env bash
# #682: 全 store 計装 build (watch_store_682.py) で survey を走らせ, [[g+8]+8] への書込みを site 単位で出す.
#   usage: store_watch_682.sh <tag> [SV_ONLY=unit,unit... (省略 = 全 942 unit; 単体実行は前 unit の状態が無く結果が変わる)]
#   出力: work/probe682/<tag>.err (`unit N` 行と `[sw]` 行), work/probe682/sites.json, work/probe682/<tag>.out (survey 結果)
#   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し sw682.o を消す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
tag=$1; only=${2:-}
restore() { rm -f work/obj/sw682.o work/obj/boot.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe682
python3 trap_triage/watch_store_682.py --out work/probe682 || exit 1
emcc -c work/probe682/boot_sw.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_store_682.c -o work/obj/sw682.o $CF || exit 1
bash m11_build.sh > work/probe682/build_$tag.log 2>&1 || { tail -5 work/probe682/build_$tag.log; exit 1; }
cp work/probe682/sites.json work/probe682/sites.json 2>/dev/null
[ -n "$only" ] && export SV_ONLY="$only"
# m11_survey.mjs の複製 (unit 開始行 `unit N` と C 側 fprintf の stderr 転送だけを足す; 判定ロジックは同一)
sed -e "s|new URL('./', import.meta.url).pathname|'$HERE'|" \
    -e "s|  const va = hex(i);|  const va = hex(i); if (process.env.SV_PROG) fs.writeSync(2, 'unit ' + i + '\\\\n');|" \
    -e "s|printErr: (s) => { errs.push(String(s)); }|printErr: (s) => { errs.push(String(s)); if (process.env.SV_PROG) fs.writeSync(2, String(s) + '\\\\n'); }|" \
    m11_survey.mjs > work/probe682/survey_sv.mjs
grep -c "SV_PROG" work/probe682/survey_sv.mjs | sed 's/^/[survey_sv] SV_PROG lines: /'
SV_TRACE_AT=99999 SV_PROG=1 node work/probe682/survey_sv.mjs > work/probe682/$tag.out 2> work/probe682/$tag.err
grep -a -o "^M11_SURVEY .\{0,120\}" work/probe682/$tag.out
grep -a -c "^\[sw\]" work/probe682/$tag.err | sed 's/^/[sw] hits: /'
