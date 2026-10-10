#!/usr/bin/env bash
# pathreg ビルド (CAB-168)。成果物は tools/shimx/pathreg/build/ (gitignore)。
#   build.sh test      : C 単体テスト (ST/MT) → build/test_pathreg_{st,mt}.cjs
#   build.sh module-a  : 本番構成モジュール = shimx src (reg.c 含む; CAB-214 で vreg 拡張取込済み) + vreg probe.c + pathreg、
#                        vreg_* 運用フック (通知/世代/ルート export) を export (build/module_a.mjs, ES6 SINGLE_FILE。JS bridge / e2e 用)
#   build.sh module-b  : 代替構成モジュール = shimx src + pathreg、vreg_* フック・probe 非 export = 通知口なし経路 (build/module_b.mjs)
#   build.sh all       : 上記全て
# 使う emcc フラグは tools/shimx/flags.sh を流用 (shimx 既存ファイルは無変更)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
SHIMX="$HERE/.."
VREG="$SHIMX/../startup/vreg"
B="$HERE/build"; mkdir -p "$B"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
source "$SHIMX/flags.sh"

INC=(-I"$SHIMX/src" -I"$VREG/src" -I"$HERE/include")
PSRC=("$HERE"/src/*.c)

case "${1:-all}" in
  test)
    for mode in st mt; do
      FL=("${SHIMX_EMCC_ST[@]}"); [ $mode = mt ] && FL=("${SHIMX_EMCC_MT[@]}")
      emcc "${SHIMX_CLANG_FLAGS[@]}" "${FL[@]}" "${INC[@]}" "$SHIMX"/src/*.c "${PSRC[@]}" "$HERE"/test/test_pathreg.c \
        -o "$B/test_pathreg_$mode.js"
      mv "$B/test_pathreg_$mode.js" "$B/test_pathreg_$mode.cjs"
      node "$B/test_pathreg_$mode.cjs" 2> "$B/test_pathreg_$mode.err" | tee "$B/test_pathreg_$mode.out" > /dev/null
      grep -q "PATHREG ALL PASS" "$B/test_pathreg_$mode.out" || { tail -5 "$B/test_pathreg_$mode.err" >&2; exit 1; }
      echo "[pathreg] test $mode OK"
    done ;;
  module-a)
    EXP='_malloc,_free,_shimx_init,_shimx_reg_import_text,_shimx_reg_export_text,_shimx_reg_reset,_shimx_reg_set,_shimx_reg_set_sz,_shimx_reg_set_dword,_shimx_reg_stats'
    EXP="$EXP,_shimx_path_to_posix,_pathreg_map,_pathreg_normalize,_pathreg_unmap,_pathreg_install,_pathreg_add_mount,_pathreg_remove_mount,_pathreg_clear_mounts,_pathreg_mount_count"
    EXP="$EXP,_pathreg_reg_hash,_pathreg_reg_changed,_pathreg_reg_mark_saved,_pathreg_reg_saved_hash,_pathreg_reg_seed_text"
    EXP="$EXP,_RegDeleteValueW,_RegDeleteKeyW,_RegOpenKeyExW,_RegCloseKey"
    EXP="$EXP,_vreg_export_root,_vreg_clear_root,_vreg_clear_all,_vreg_generation,_vreg_set_notify"
    EXP="$EXP,$(grep -o 'vreg_probe_[a-z_]*' "$VREG/src/vreg.h" | sort -u | sed 's/^/_/' | paste -sd,)"
    emcc "${SHIMX_CLANG_FLAGS[@]}" -sALLOW_MEMORY_GROWTH=1 -sGLOBAL_BASE=1048576 -sENVIRONMENT=web,worker,node \
      -sMODULARIZE=1 -sEXPORT_ES6=1 -sEXPORT_NAME=createPathregModule -sSINGLE_FILE=1 -sALLOW_TABLE_GROWTH=1 \
      -sEXIT_RUNTIME=0 -sINITIAL_MEMORY=33554432 -sERROR_ON_UNDEFINED_SYMBOLS=1 \
      -sEXPORTED_FUNCTIONS="$EXP" \
      -sEXPORTED_RUNTIME_METHODS=UTF8ToString,stringToUTF8,lengthBytesUTF8,stringToUTF16,UTF16ToString,HEAPU32,HEAPU16,addFunction,removeFunction \
      "${INC[@]}" "$SHIMX"/src/*.c "$VREG/src/probe.c" "${PSRC[@]}" -o "$B/module_a.mjs"
    ls -l "$B/module_a.mjs" ;;
  module-b)
    EXP='_malloc,_free,_shimx_init,_shimx_reg_import_text,_shimx_reg_export_text,_shimx_reg_reset,_shimx_reg_set,_shimx_reg_set_sz,_shimx_reg_set_dword,_shimx_reg_stats'
    EXP="$EXP,_shimx_path_to_posix,_pathreg_map,_pathreg_normalize,_pathreg_unmap,_pathreg_install,_pathreg_add_mount,_pathreg_remove_mount,_pathreg_clear_mounts,_pathreg_mount_count"
    EXP="$EXP,_pathreg_reg_hash,_pathreg_reg_changed,_pathreg_reg_mark_saved,_pathreg_reg_saved_hash,_pathreg_reg_seed_text"
    EXP="$EXP,_RegDeleteValueW,_RegDeleteKeyW,_RegOpenKeyExW,_RegCloseKey"
    emcc "${SHIMX_CLANG_FLAGS[@]}" -sALLOW_MEMORY_GROWTH=1 -sGLOBAL_BASE=1048576 -sENVIRONMENT=web,worker,node \
      -sMODULARIZE=1 -sEXPORT_ES6=1 -sEXPORT_NAME=createPathregModule -sSINGLE_FILE=1 \
      -sEXIT_RUNTIME=0 -sINITIAL_MEMORY=33554432 -sERROR_ON_UNDEFINED_SYMBOLS=1 \
      -sEXPORTED_FUNCTIONS="$EXP" \
      -sEXPORTED_RUNTIME_METHODS=UTF8ToString,stringToUTF8,lengthBytesUTF8,stringToUTF16,UTF16ToString,HEAPU32,HEAPU16 \
      "${INC[@]}" "$SHIMX"/src/*.c "${PSRC[@]}" -o "$B/module_b.mjs"
    ls -l "$B/module_b.mjs" ;;
  all) "$0" test; "$0" module-a; "$0" module-b ;;
  *) echo "usage: build.sh test|module-a|module-b|all"; exit 2 ;;
esac
