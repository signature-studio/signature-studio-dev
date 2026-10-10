#!/usr/bin/env bash
# pump ビルド共通: shimx (読取専用) と winstubs (読取専用) のオブジェクトを
# **本 dir 専用の work/** (tools/startup/pump/work) に別 prefix でビルドする
# (winstubs.sh の work/ は共有しない — 並走検収と衝突させない / CAB-102 範囲)。
#
#   build.sh objs <ST|MT>                          → work/obj_<mode>/{shimx,ws,pump}/*.o
#   build.sh link <ST|MT> <out.js> <mode> src...   mode:
#     unit    : main 付きテストをその場で実行 (非 modularize)
#     pumpmod : modularize + INVOKE_RUN=0 (e2e 用。ホスト JS が export を叩く)
#     weak    : 置換前対照 (winstubs weak のみ。pump TU をリンクしない)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"          # tools/startup/pump
STARTUP="$HERE/.."
WORK="$HERE/work"
SHIMX="$STARTUP/../shimx"
WINSTUBS="$STARTUP/winstubs"
mkdir -p "$WORK"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
source "$SHIMX/flags.sh"

cmd="$1"; mode="${2:-ST}"
CF=("${SHIMX_CLANG_FLAGS[@]}")
[ "$mode" = MT ] && CF+=(-pthread)

compile_one() {   # $1=src.c $2=out dir
    local f="$1" out="$2" b o
    b="$(basename "$f" .c)"; o="$out/$b.o"
    if [ -f "$o" ] && [ "$o" -nt "$f" ] && [ -z "$(find "$(dirname "$f")" "$SHIMX/src" "$WINSTUBS/src" -name '*.h' -newer "$o" 2>/dev/null | head -1)" ]; then return 0; fi
    emcc -c "${CF[@]}" "$f" -o "$o"
}
export -f compile_one
export SHIMX WINSTUBS HERE
compile_dir() {   # $1=src dir  $2=out dir
    mkdir -p "$2"
    export CF_STR="${CF[*]}"
    ls "$1"/*.c | xargs -P 8 -I{} bash -c 'IFS=" " read -r -a CF <<< "$CF_STR"; compile_one "$1" "$2"' _ {} "$2"
}

case "$cmd" in
objs)
    compile_dir "$SHIMX/src" "$WORK/obj_$mode/shimx"
    compile_dir "$WINSTUBS/src" "$WORK/obj_$mode/ws"
    compile_dir "$HERE/src" "$WORK/obj_$mode/pump"
    ;;
link)
    out="$3"; lmode="$4"; shift 4
    FL=("${CF[@]}")
    if [ "$mode" = MT ]; then FL+=("${SHIMX_EMCC_MT[@]}"); else FL+=("${SHIMX_EMCC_ST[@]}"); fi
    FL+=(-sEXPORTED_RUNTIME_METHODS=HEAP32,HEAPF64)
    case "$lmode" in
        unit)    : ;;                                                          # main をその場で実行
        pumpmod) FL+=(-sINVOKE_RUN=0 -sMODULARIZE=1 -sEXPORT_NAME=PumpMod) ;;
        pumpchrome) FL+=(-sINVOKE_RUN=0 -sMODULARIZE=1 -sEXPORT_NAME=PumpMod -sEXPORT_ES6=1 \
                         -sENVIRONMENT=web,worker -sEXIT_RUNTIME=0 -sPTHREAD_POOL_SIZE=2) ;;
        weak)    : ;;
        *) echo "unknown link mode: $lmode" >&2; exit 2;;
    esac
    OBJS=("$WORK/obj_$mode"/shimx/*.o "$WORK/obj_$mode"/ws/*.o)
    if [ "$lmode" != weak ]; then OBJS+=("$WORK/obj_$mode"/pump/*.o); fi
    emcc "${FL[@]}" "$@" "${OBJS[@]}" -o "$out"
    ;;
*) echo "usage: build.sh objs|link ..." >&2; exit 2;;
esac
