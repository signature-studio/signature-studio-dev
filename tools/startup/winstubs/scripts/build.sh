#!/usr/bin/env bash
# winstubs ビルド共通: shimx(読取専用)と winstubs のオブジェクトを work/ 配下に作り、テスト用 wasm をリンクする。
#   build.sh objs <ST|MT>                      → work/obj_<mode>/{shimx,ws}/*.o
#   build.sh link <ST|MT> <out.cjs> <mode> src...  mode: wrap(winstubs+--wrap) | base(shimx のみ)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
SHIMX="$HERE/../../shimx"
WORK="$HERE/../work/winstubs"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
source "$SHIMX/flags.sh"

cmd="$1"; mode="${2:-ST}"
CF=("${SHIMX_CLANG_FLAGS[@]}")
[ "$mode" = MT ] && CF+=(-pthread)

compile_one() {   # $1=src.c $2=out dir
    local f="$1" out="$2" b o
    b="$(basename "$f" .c)"; o="$out/$b.o"
    if [ -f "$o" ] && [ "$o" -nt "$f" ] && [ -z "$(find "$(dirname "$f")" "$SHIMX/src" "$HERE/src" -name '*.h' -newer "$o" 2>/dev/null | head -1)" ]; then return 0; fi
    emcc -c "${CF[@]}" "$f" -o "$o"
}
export -f compile_one
export SHIMX HERE
compile_dir() {   # $1=src dir  $2=out dir
    mkdir -p "$2"
    export CF_STR="${CF[*]}"
    ls "$1"/*.c | xargs -P 8 -I{} bash -c 'IFS=" " read -r -a CF <<< "$CF_STR"; compile_one "$1" "$2"' _ {} "$2"
}

case "$cmd" in
objs)
    compile_dir "$SHIMX/src" "$WORK/obj_$mode/shimx"
    compile_dir "$HERE/src" "$WORK/obj_$mode/ws"
    ;;
link)
    out="$3"; lmode="$4"; shift 4
    FL=("${CF[@]}")
    if [ "$mode" = MT ]; then FL+=("${SHIMX_EMCC_MT[@]}"); else FL+=("${SHIMX_EMCC_ST[@]}"); fi
    OBJS=("$WORK/obj_$mode"/shimx/*.o)
    EXTRA=()
    if [ "$lmode" = wrap ]; then
        OBJS+=("$WORK/obj_$mode"/ws/*.o)
        while read -r s; do [ -z "$s" ] || EXTRA+=("-Wl,--wrap=$s"); done < <(grep -v '^#' "$HERE/wrap_list.txt")
    fi
    CCOPT=()
    for a in "$@"; do case "$a" in -D*|-I*|-s*|-Wl,*) CCOPT+=("$a");; esac; done
    SRCS=(); for a in "$@"; do case "$a" in -D*|-I*|-s*|-Wl,*) ;; *) SRCS+=("$a");; esac; done
    emcc "${FL[@]}" "${CCOPT[@]}" "${EXTRA[@]}" "${SRCS[@]}" "${OBJS[@]}" -o "${out%.cjs}.js"
    mv "${out%.cjs}.js" "$out"
    ;;
*) echo "usage"; exit 2;;
esac
