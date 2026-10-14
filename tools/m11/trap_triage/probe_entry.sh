#!/usr/bin/env bash
# #596: 指定関数の入口に引数 dump (m11_pe) を入れた build で survey を走らせ, stderr (SV_PROG の `unit N` 行 + `[pe]` 行) を work/probe/<tag>.err に残す.
#   usage: probe_entry.sh <tag> <fn_hex,fn_hex,...> [SV_ONLY=unit,unit... (省略 = 全 unit。単体実行は前 unit の状態が無く結果が変わるので省略推奨)]   例: probe_entry.sh p4f 4f9f40,4fad10 291,296
#   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し probe.o を消す (trap で必ず復元).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
tag=$1; fns=$2; only=${3:-}
restore() { rm -f work/obj/probe.o; touch work/boot_final3.ll; rm -f work/obj/boot.o; bash m11_build.sh > /dev/null 2>&1; }
trap restore EXIT
python3 trap_triage/probe_entry.py "$fns" --out work/probe ${PROBE_WATCH:+--watch $PROBE_WATCH} || exit 1
# 展開直後は m11_post.py (checkout の新しい mtime) が boot_final3.ll を作り直し, m11_build.sh が probe 版 boot.o を非 probe 版で上書きする (= [pe] が 0 件)。
# boot_final3.ll を先に新しくして post の再実行と boot.o の再コンパイルを止める。復元 (restore) は boot.o を消してから作り直すので影響しない。
touch work/boot_final3.ll
emcc -c work/probe/boot_probe.ll -o work/obj/boot.o $CF || exit 1
emcc -c work/probe/probe.c -o work/obj/probe.o $CF || exit 1
M11_KEEP_BOOT_O=1 bash m11_build.sh > work/probe/build_$tag.log 2>&1 || { tail -5 work/probe/build_$tag.log; exit 1; }
[ -n "$only" ] && export SV_ONLY="$only"
SV_TRACE_AT=99999 SV_PROG=1 node trap_triage/survey_units.mjs work/probe/$tag.json > work/probe/$tag.out 2> work/probe/$tag.err
grep -a SURVEY_UNITS work/probe/$tag.out
echo "[pe] lines: $(grep -a -c '^\[pe\]' work/probe/$tag.err)"
