#!/usr/bin/env bash
# glue ビルド (CAB-101)。読み取り元は全て読取専用 component (shimx / winstubs / pump / pathreg / vreg)。
# 成果物は **本 dir 専用の work/** (tools/startup/glue/work) に置く (他 component の work/ とは共有しない)。
#
#   build.sh objs ST|MT                              → work/obj_<mode>/{shimx,ws,pump,pathreg,vreg,glue}/*.o
#   build.sh link ST|MT <out.js> <lmode> [emcc flags...] src...
#     lmode:
#       unit    : main 付きの C 単体テストをその場で実行 (非 modularize)
#       gluemod : modularize + INVOKE_RUN=0 (TS ホスト側 e2e 用)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"          # tools/startup/glue
STARTUP="$(cd -- "$HERE/.." && pwd)"                    # tools/startup
SHIMX="$STARTUP/../shimx"
WINSTUBS="$STARTUP/winstubs"
PUMP="$STARTUP/pump"
VREG="$STARTUP/vreg"
PATHREG="$SHIMX/pathreg"
WORK="$HERE/work"
mkdir -p "$WORK"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1 || true; set -u
source "$SHIMX/flags.sh"

cmd="$1"; mode="${2:-ST}"
cd "$HERE"          # 呼出し元の相対パス (work/unit_st.cjs, test/x.c 等) を本 dir 基準で解決する
CF=("${SHIMX_CLANG_FLAGS[@]}")
[ "$mode" = MT ] && CF+=(-pthread)

INC=(-I"$SHIMX/src" -I"$VREG/src" -I"$PATHREG/include" -I"$PUMP/src" -I"$WINSTUBS/src" -I"$HERE/include")

compile_one() {   # $1=src.c $2=out dir
    local f="$1" out="$2" b o
    b="$(basename "$f" .c)"; o="$out/$b.o"
    if [ -f "$o" ] && [ "$o" -nt "$f" ] && [ -z "$(find "$(dirname "$f")" "$SHIMX/src" "$PUMP/src" "$WINSTUBS/src" -name '*.h' -newer "$o" 2>/dev/null | head -1)" ]; then return 0; fi
    emcc -c "${CF[@]}" "${INC[@]}" "$f" -o "$o"
}
compile_dir() {   # $1=src dir  $2=out dir  (並列 8・CF/INC は呼出し元シェルの配列を背景継承)
    mkdir -p "$2"
    local f n=0
    for f in "$1"/*.c; do
        [ -e "$f" ] || continue
        compile_one "$f" "$2" &
        n=$((n + 1))
        if [ $((n % 8)) -eq 0 ]; then wait; fi
    done
    wait
}

build_objs() {
    local M="$WORK/obj_$1"
    compile_dir "$SHIMX/src"   "$M/shimx"
    compile_dir "$WINSTUBS/src" "$M/ws"
    compile_dir "$PUMP/src"    "$M/pump"
    compile_dir "$PATHREG/src" "$M/pathreg"
    compile_dir "$VREG/src"    "$M/vreg"
    compile_dir "$HERE/src"    "$M/glue"
}

case "$cmd" in
objs)
    build_objs "$mode"
    echo "[glue] objs $mode: shimx $(ls "$WORK/obj_$mode"/shimx/*.o | wc -l) / ws $(ls "$WORK/obj_$mode"/ws/*.o | wc -l) / pump $(ls "$WORK/obj_$mode"/pump/*.o | wc -l) / pathreg $(ls "$WORK/obj_$mode"/pathreg/*.o | wc -l) / vreg $(ls "$WORK/obj_$mode"/vreg/*.o | wc -l) / glue $(ls "$WORK/obj_$mode"/glue/*.o | wc -l)"
    ;;
link)
    out="$3"; lmode="$4"; shift 4
    FL=("${CF[@]}")
    if [ "$mode" = MT ]; then FL+=("${SHIMX_EMCC_MT[@]}"); else FL+=("${SHIMX_EMCC_ST[@]}"); fi
    FL+=(-I"$HERE/include" -I"$SHIMX/src" -I"$VREG/src" -I"$PATHREG/include" -I"$PUMP/src" -I"$WINSTUBS/src")
    M="$WORK/obj_$mode"
    OBJS=("$M"/shimx/*.o "$M"/ws/*.o "$M"/pump/*.o "$M"/pathreg/*.o "$M"/vreg/*.o "$M"/glue/*.o)
    case "$lmode" in
        unit)    : ;;                                  # (main 実行のための _main 追加は下記 EXP 構築後)
        gluemod) FL+=(-sMODULARIZE=1 -sINVOKE_RUN=0 -sEXPORT_NAME=createGlueModule -sEXPORT_ES6=1 \
                       -sEXIT_RUNTIME=0 -sALLOW_TABLE_GROWTH=1)
                 ;;
        *) echo "unknown link mode: $lmode" >&2; exit 2;;
    esac
    # host から叩く export (pathreg.h の「C 側が JS に求めるエクスポート」+ glue + pump 結線)
    EXP='_malloc,_free,_shimx_init,_shimx_reg_import_text,_shimx_reg_export_text,_shimx_reg_reset,_shimx_reg_set,_shimx_reg_set_sz,_shimx_reg_set_dword,_shimx_reg_stats'
    EXP="$EXP,_shimx_path_to_posix,_pathreg_map,_pathreg_normalize,_pathreg_unmap,_pathreg_install,_pathreg_add_mount,_pathreg_remove_mount,_pathreg_clear_mounts,_pathreg_mount_count,_pathreg_get_mount"
    EXP="$EXP,_pathreg_reg_hash,_pathreg_reg_changed,_pathreg_reg_mark_saved,_pathreg_reg_saved_hash,_pathreg_reg_seed_text"
    EXP="$EXP,_RegDeleteValueW,_RegDeleteKeyW,_RegOpenKeyExW,_RegCloseKey"
    EXP="$EXP,_vreg_export_root,_vreg_clear_root,_vreg_clear_all,_vreg_generation,_vreg_set_notify"
    EXP="$EXP,$(grep -o 'vreg_probe_[a-z_]*' "$VREG/src/vreg.h" | sort -u | sed 's/^/_/' | paste -sd,)"
    # pump の EXPORT("…") 付き関数は export_name が JS 側の名前を決める。C 内部シンボルと
    # 同名の export_name を持つ組 (pump_calibrate / pump_clock_offset / pump_clock_calibrated /
    # pump_set_clock_offset / pump_set_wndproc) は **C シンボル名 (_e 付き) 側** を指定する
    # (JS 名は export_name どおり _pump_xxx)。
    EXP="$EXP,_pump_ring_addr,_pump_ring_capacity,_pump_set_wait_mode,_pump_get_wait_mode,_pump_step,_pump_wait_ms"
    EXP="$EXP,_pump_calibrate_e,_pump_clock_offset_e,_pump_clock_calibrated_e,_pump_now_raw,_pump_set_clock_offset_e,_pump_set_wndproc_e"
    EXP="$EXP,_pump_stats_addr,_pump_pop_log_addr,_pump_pop_log_count,_pump_ctrl_req_addr,_pump_ctrl_resp_addr"
    EXP="$EXP,$(grep -o 'glue_[a-z_]*(' "$HERE/include/glue.h" | tr -d '(' | sort -u | sed 's/^/_/' | paste -sd,)"
    # EXPORTED_FUNCTIONS を明示すると emscripten が callMain を落とす (実測: callMain 2→0) ため、
    # unit モードでは _main を足して main をその場で実行する。
    [ "$lmode" = unit ] && EXP="$EXP,_main"
    FL+=(-sEXPORTED_FUNCTIONS="$EXP")
    RTM='UTF8ToString,stringToUTF8,lengthBytesUTF8,stringToUTF16,UTF16ToString,HEAP32,HEAPU32,HEAPU16,HEAPU8,HEAPF64,addFunction,removeFunction'
    # FS は wvfs mount (createWvfsFs + FS.syncfs) のために必要 (Emscripten FS アダプタ結線)
    [ "$lmode" = gluemod ] && RTM="$RTM,FS"
    FL+=(-sEXPORTED_RUNTIME_METHODS="$RTM")
    emcc "${FL[@]}" "$@" "${OBJS[@]}" -o "$out"
    ;;
*) echo "usage: build.sh objs|link ..." >&2; exit 2;;
esac
