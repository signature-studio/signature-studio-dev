#!/usr/bin/env bash
# #682: 全 store 計装 build (watch_store_682.py) で survey を走らせ, [[g+8]+8] への書込みを site 単位で出す.
#   usage: [M11_FIX_682=0|1] [M11_NOTIFY_682=0|1] store_watch_682.sh <tag>  (survey は全 942 unit を順に実行する)
#   既定は M11_FIX_682=1 (修復あり) / M11_NOTIFY_682=0 (notify 省略)。REPORT_682 §2.1 の抜粋は M11_FIX_682=0 で出す。
#   出力: work/probe682/<tag>.err (`unit N` 行と `[sw]`/`[esc]` 行), work/probe682/sites.json, work/probe682/<tag>.out (survey 結果)
#   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し sw682.o / ov.o を消す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
# emsdk は docs/REFERENCES.md の [EMSDK] (toolchain-emsdk 素材の展開先) を使う。store_watch_682.sh と同じ既定パス。
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
FIX=${M11_FIX_682:-1}; NOTIFY=${M11_NOTIFY_682:-0}
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
tag=$1
restore() { rm -f work/obj/sw682.o work/obj/boot.o work/obj/ov.o; touch work/boot_final3.ll; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
mkdir -p work/probe682
python3 trap_triage/watch_store_682.py --out work/probe682 || exit 1
emcc -c work/probe682/boot_sw.ll -o work/obj/boot.o $CF || exit 1
emcc -c trap_triage/watch_addr_1046.c -o work/obj/sw682.o $CF || exit 1
emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_FIX_682=$FIX -DM11_NOTIFY_682=$NOTIFY || exit 1
bash m11_build.sh > work/probe682/build_$tag.log 2>&1 || { tail -5 work/probe682/build_$tag.log; exit 1; }
# m11_survey.mjs の複製 (unit 開始行 `unit N` と C 側 fprintf の stderr 転送だけを足す; 判定ロジックは同一)
sed -e "s|new URL('./', import.meta.url).pathname|'$HERE'|" \
    -e "s|  const va = hex(i);|  const va = hex(i); if (process.env.SV_PROG) fs.writeSync(2, 'unit ' + i + '\\\\n');|" \
    -e "s|printErr: (s) => { errs.push(String(s)); }|printErr: (s) => { errs.push(String(s)); if (process.env.SV_PROG) fs.writeSync(2, String(s) + '\\\\n'); }|" \
    m11_survey.mjs > survey_sv_1046.mjs
grep -c "SV_PROG" survey_sv_1046.mjs | sed 's/^/[survey_sv] SV_PROG lines: /'
SV_PROG=1 SV_ONLY=${SV_ONLY:-} node trap_triage/survey_units.mjs work/probe682/$tag.json > work/probe682/$tag.out 2> work/probe682/$tag.err || { echo "[store_watch] survey failed (rc=$?)" >&2; exit 1; }
grep -a -o "^M11_SURVEY .\{0,120\}" work/probe682/$tag.out
grep -a -c "^\[sw\]" work/probe682/$tag.err | sed 's/^/[sw] hits: /'
