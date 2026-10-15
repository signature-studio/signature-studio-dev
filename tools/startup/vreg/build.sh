#!/usr/bin/env bash
# vreg ビルド: shimx/src/*.c (reg.c 含む — CAB-214 で shimx が正本化) + vreg/src/probe.c (テスト専用ヘルパ) をリンク。
#   build.sh test    : C 単体テスト (build/test_vreg.cjs)
#   build.sh shimx   : shimx 既存テスト一式 (core/sys/ole_shell + M4 互換) を probe.c 同梱で実行
#   build.sh module  : node/ブラウザ共用 wasm モジュール (build/vreg_wasm.mjs, SINGLE_FILE, ES6)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SHIMX="$HERE/../../shimx"
B="$HERE/build"; mkdir -p "$B"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
source "$SHIMX/flags.sh"
SRCS=("$SHIMX"/src/*.c)
VSRC=("$HERE/src/probe.c")
INC=(-I"$SHIMX/src" -I"$HERE/src")
case "${1:-test}" in
  test)
    emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" "${INC[@]}" "${SRCS[@]}" "${VSRC[@]}" "$HERE/test/test_vreg.c" -o "$B/test_vreg.js"
    mv "$B/test_vreg.js" "$B/test_vreg.cjs"; node "$B/test_vreg.cjs" ;;
  shimx)
    for mode in st mt; do
      FL=("${SHIMX_EMCC_ST[@]}"); [ $mode = mt ] && FL=("${SHIMX_EMCC_MT[@]}")
      emcc "${SHIMX_CLANG_FLAGS[@]}" "${FL[@]}" "${INC[@]}" -I"$SHIMX/pathreg/include" "${SRCS[@]}" "${VSRC[@]}" "$SHIMX"/test/*.c "$SHIMX"/pathreg/src/pathmap.c -o "$B/shimx_$mode.js"
      mv "$B/shimx_$mode.js" "$B/shimx_$mode.cjs"
      node "$B/shimx_$mode.cjs" 2> "$B/shimx_$mode.err" | tee "$B/shimx_$mode.out"
    done
    M4T="$SHIMX/../shim/test/test_main.c"
    emcc "${SHIMX_CLANG_FLAGS[@]}" "${SHIMX_EMCC_ST[@]}" "${INC[@]}" "${SRCS[@]}" "${VSRC[@]}" "$M4T" -o "$B/m4_st.js"
    mv "$B/m4_st.js" "$B/m4_st.cjs"; node "$B/m4_st.cjs" | tail -1 ;;
  module)
    EXP='_malloc,_free,_shimx_init,_shimx_reg_import_text,_shimx_reg_export_text,_shimx_reg_reset,_shimx_reg_stats,_vreg_export_root,_vreg_clear_root,_vreg_clear_all,_vreg_generation,_vreg_set_notify'
    EXP="$EXP,$(grep -o 'vreg_probe_[a-z_]*' "$HERE/src/vreg.h" | sort -u | sed 's/^/_/' | paste -sd,)"
    emcc "${SHIMX_CLANG_FLAGS[@]}" -sALLOW_MEMORY_GROWTH=1 -sGLOBAL_BASE=1048576 -sENVIRONMENT=web,worker,node -sMODULARIZE=1 -sEXPORT_ES6=1 \
      -sEXPORT_NAME=createVregModule -sSINGLE_FILE=1 -sALLOW_TABLE_GROWTH=1 -sEXIT_RUNTIME=0 -sINITIAL_MEMORY=33554432 \
      -sEXPORTED_FUNCTIONS="$EXP" -sEXPORTED_RUNTIME_METHODS=UTF8ToString,stringToUTF8,lengthBytesUTF8,addFunction,removeFunction,HEAPU8,HEAPU32 \
      "${INC[@]}" "${SRCS[@]}" "${VSRC[@]}" -o "$B/vreg_wasm.mjs"
    ls -l "$B/vreg_wasm.mjs" ;;
  symcheck)   # vreg が要求する公開面 (shimx.h 宣言の Reg* 全て + module の EXPORTED の vreg_*/shimx_reg_*) を shimx reg.c が定義している検査
    mkdir -p "$HERE/work"
    emcc "${SHIMX_CLANG_FLAGS[@]}" -c "${INC[@]}" "$SHIMX/src/reg.c" -o "$HERE/work/shimx_reg.o"
    syms() { llvm-nm --defined-only -g "$1" | awk '$2=="T"||$2=="W"{print $3}' | sort; }
    need="$( { grep -oE '\bReg[A-Z][A-Za-z]*\(' "$SHIMX/src/shimx.h" | tr -d '(';
               sed -n 's/^ *EXP=.*_shimx_init,\(.*\)'"'"'$/\1/p' "$HERE/build.sh" | tr ',' '\n' | grep -E '^_(vreg_|shimx_reg_)' | sed 's/^_//'; } | sort -u)"
    miss="$(comm -23 <(printf '%s\n' "$need") <(syms "$HERE/work/shimx_reg.o"))"
    [ -z "$miss" ] || { echo "shimx reg.c に不足: $miss"; exit 1; }
    echo "[vreg] symcheck OK: vreg 要求 $(printf '%s\n' "$need" | wc -l) シンボルを shimx reg.c が全て定義 (reg.c 公開 $(syms "$HERE/work/shimx_reg.o" | wc -l))" ;;
  *) echo "usage: build.sh test|shimx|module|symcheck"; exit 2 ;;
esac
