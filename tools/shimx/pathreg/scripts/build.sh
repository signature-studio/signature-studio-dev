#!/usr/bin/env bash
# pathreg ビルド (CAB-168)。成果物は tools/shimx/pathreg/build/ (gitignore)。
#   build.sh test      : C 単体テスト (ST/MT) → build/test_pathreg_{st,mt}.cjs
#   build.sh module-a  : 本番構成モジュール = shimx src (reg.c 含む; CAB-214 で vreg 拡張取込済み) + vreg probe.c + pathreg、
#                        vreg_* 運用フック (通知/世代/ルート export) を export (build/module_a.mjs, ES6 SINGLE_FILE。JS bridge / e2e 用)
#   build.sh module-b  : 代替構成モジュール = shimx src + pathreg、vreg_* フック・probe 非 export = 通知口なし経路 (build/module_b.mjs)
#   build.sh nc         : ネガティブコントロール (規則 41)。修正を 1 つずつ外した ablate 版を build して FAIL を確認
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
      emcc "${SHIMX_CLANG_FLAGS[@]}" "${FL[@]}" "${INC[@]}" "$SHIMX"/src/*.c "${PSRC[@]}" "$HERE"/test/test_defaults.c \
        -o "$B/test_defaults_$mode.js"
      mv "$B/test_defaults_$mode.js" "$B/test_defaults_$mode.cjs"
      node "$B/test_defaults_$mode.cjs" 2> "$B/test_defaults_$mode.err" | tee "$B/test_defaults_$mode.out" > /dev/null
      grep -q "PATHREG DEFAULTS ALL PASS" "$B/test_defaults_$mode.out" || { tail -5 "$B/test_defaults_$mode.err" >&2; exit 1; }
      echo "[pathreg] test defaults $mode OK"
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
  nc)
    # ネガティブコントロール (規則 41・CAB-271): 修正/既定経路を 1 つずつ外した ablate 版を作り、
    # 該当テストが FAIL することを確認する (PASS したら照合が空振り = 不合格)。
    #   nc1: pathreg_set_paths() の g_defaults_blocked = 1 を外す (修正のみ取消)      → test_pathreg
    #   nc2: pr_ensure_defaults() の既定ロードを無効化 (既定経路の否定)              → test_defaults
    mkdir -p "$B/nc"
    sed 's/g_defaults_blocked = 1;/\/* ablated CAB-271 nc1 *\//' "$HERE/src/pathmap.c" > "$B/nc/pathmap_nc1.c"
    sed 's/if (g_defaults_loaded || g_defaults_blocked) return;/if (1) return; \/* ablated CAB-271 nc2 *\//' \
        "$HERE/src/pathmap.c" > "$B/nc/pathmap_nc2.c"
    grep -q "ablated CAB-271 nc1" "$B/nc/pathmap_nc1.c" || { echo "[pathreg] FAIL: nc1 の sed が効いていない" >&2; exit 2; }
    grep -q "ablated CAB-271 nc2" "$B/nc/pathmap_nc2.c" || { echo "[pathreg] FAIL: nc2 の sed が効いていない" >&2; exit 2; }
    fail=0
    for nc in nc1 nc2; do
      tc=test_pathreg; [ "$nc" = nc2 ] && tc=test_defaults
      SD="$B/nc/src_$nc"; mkdir -p "$SD"
      cp "$HERE"/src/*.c "$HERE"/src/*.h "$SD"/
      cp "$B/nc/pathmap_$nc.c" "$SD/pathmap.c"          # ablate 版で置換
      emcc "${SHIMX_CLANG_FLAGS[@]}" "${INC[@]}" "$SHIMX"/src/*.c "$SD"/*.c "$HERE"/test/$tc.c \
        -o "$B/nc/${tc}_$nc.js"
      mv "$B/nc/${tc}_$nc.js" "$B/nc/${tc}_$nc.cjs"
      if node "$B/nc/${tc}_$nc.cjs" > "$B/nc/${tc}_$nc.out" 2> "$B/nc/${tc}_$nc.err"; then
        echo "[pathreg] nc $nc: UNEXPECTED PASS ($tc) — 照合が空振りしています" >&2; fail=1
      else
        echo "[pathreg] nc $nc: FAIL as expected ($tc): $(grep -m1 'FAIL' "$B/nc/${tc}_$nc.err" || echo '(no FAIL line)')"
      fi
    done
    [ "$fail" = 0 ] || exit 1
    echo "[pathreg] nc OK (2 ablations が FAIL を検出)" ;;
  all) "$0" test; "$0" module-a; "$0" module-b ;;
  *) echo "usage: build.sh test|module-a|module-b|nc|all"; exit 2 ;;
esac
