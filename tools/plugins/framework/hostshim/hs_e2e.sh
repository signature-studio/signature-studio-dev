#!/usr/bin/env bash
# hs_e2e.sh — CAB-195 (P0b) host shim E2E を 1 コマンドで実行。
#   bash hs_e2e.sh            # 増分ビルド + 実行
#   bash hs_e2e.sh --fresh    # IR patch / table / emcc を作り直し
#   bash hs_e2e.sh --observe  # 判定なし観測モード (GOLDEN 固定前の ID 序列観測)
#   HS_WFW=<dir> bash hs_e2e.sh --fresh  # 入力 dir を差し替え (FW_EXT_FUNCS の ext 版 canon3 で検証)。
#                                        # 絶対パスで指定する (相対パスは cd 後に解決されて前提不足になる)。
#                                        # 増分判定は WFW の fw_flat4_canon3.ll と fw_rt.c の mtime だけを見るため、差し替えるときは必ず --fresh
#
# 前提: CAB-194 の framework lift 済み (tools/plugins/framework/fw_stage2.sh 完走)。
#   本 script は framework 成果物を **読み取りのみ** で利用する:
#     work/fw/fw_flat4_canon3.ll / fw_simd.c / fw_image.bin / fw_imports.json /
#     fw_rt.c / fw_rt.h / fw_boot.c / fw_route.cjs
#   書込は自 dir (tools/plugins/framework/hostshim/) と自 work (tools/plugins/work/hs/) のみ。
#
# 構成 (framework build と連鎖 build を分離する理由は REPORT §4):
#   Phase A: fw_route.cjs (CAB-194 artifact をそのまま) で framework smoke — 回帰確認。
#   Phase B: hs_route.cjs (下記の派生ビルド) で CreatePlugInstance→ctor 連鎖 + host shim 記録照合。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../../shared/env.sh"
T="$REPO_ROOT"
FW="$T/tools/plugins/framework"
WFW="${HS_WFW:-$T/tools/plugins/work/fw}"
W="$T/tools/plugins/work/hs"
H="$HERE"
FRESH=0
EXTRA=()
for a in "$@"; do case "$a" in
  --fresh) FRESH=1 ;;
  --observe) EXTRA+=(--observe) ;;
  *) echo "unknown arg $a" >&2; exit 2 ;;
esac; done

mkdir -p "$W"
cd "$W"

for f in fw_flat4_canon3.ll fw_simd.c fw_image.bin fw_imports.json fw_rt.c fw_rt.h fw_boot.c fw_route.cjs; do
  [ -f "$WFW/$f" ] || { echo "[hs] 前提不足: $WFW/$f (fw_stage2.sh を先に実行)" >&2; exit 1; }
done

# ---- 1. IR: CreatePlugInstance 引数経路 → 戻り値 store → mosaic override ----
#   hs_irfix   : 6bdde0 の 0-arg define に (Host, Tag) 引数を復元 ( RetDec 定数折畳み修復)
#   fw_retw    : TTestPlug.Create (0x6be800) の ret に BLK+0x80 store (6bdde0 の abi_ret_load 対応)
#   fw_hostfix : 連鎖が通る mosaic 領域 (0x40e5e0/0x40bd20) を安全化
if [ $FRESH = 1 ] || [ ! -f hs_flat.ll ] || [ "$WFW/fw_flat4_canon3.ll" -nt hs_flat.ll ]; then
  python3 "$H/hs_irfix.py" "$WFW/fw_flat4_canon3.ll" hs_flat.ll
fi
if [ $FRESH = 1 ] || [ ! -f hs_flat2.ll ] || [ hs_flat.ll -nt hs_flat2.ll ]; then
  python3 "$FW/fw_retw.py" hs_flat.ll hs_flat2.ll --blk 0x8A1000 --only-range 0x6be800:0x6be801 --report hs_retw.json
fi
if [ $FRESH = 1 ] || [ ! -f hs_flat3.ll ] || [ hs_flat2.ll -nt hs_flat3.ll ]; then
  python3 "$FW/fw_hostfix.py" hs_flat2.ll hs_flat3.ll --blk 0x8A1000 --report hs_hostfix.json
fi

# ---- 2. dispatch 表 (hs_flat3.ll から生成 — fw_table.py は hs_slot0..45 を 0xE100000.. に登録) ----
if [ $FRESH = 1 ] || [ ! -f hs_table.c ] || [ hs_flat3.ll -nt hs_table.c ]; then
  python3 "$FW/fw_table.py" --ir hs_flat3.ll --imports "$WFW/fw_imports.json" --out hs_table.c --blk 0x8A1000
fi

# ---- 3. emcc (framework と同一 flag + hs sources + hostshim) ----
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
if [ $FRESH = 1 ] || [ ! -f hs_route.cjs ] || [ hs_table.c -nt hs_route.cjs ] || \
   [ "$H/hs_plug.c" -nt hs_route.cjs ] || [ "$H/hostshim.c" -nt hs_route.cjs ] || \
   [ "$H/hs_utl.c" -nt hs_route.cjs ] || \
   [ "$WFW/fw_rt.c" -nt hs_route.cjs ]; then
  emcc hs_flat3.ll "$WFW/fw_simd.c" hs_table.c "$H/hs_plug.c" "$H/hostshim.c" "$H/hs_utl.c" "$WFW/fw_rt.c" "$WFW/fw_boot.c" \
    -I"$H" -I"$WFW" -I"$FW" -I"$T/tools/liftlib/liftlib/simd" \
    -w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB \
    -sGLOBAL_BASE=$((0x10000000)) -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
    -sEXIT_RUNTIME=0 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
    -sEXPORTED_FUNCTIONS=_function_6c13a0,_fw_dispatch_count,_fw_last_site,_fw_last_target,_fw_ff_count,_fw_ff_msg,_fw_va_calls,_fw_va_used,_fw_alloc_count,_fw_alloc_bytes,_fw_call_cur,_hs_e2e_run,_hs_status_get,_hs_plug_get,_hs_rec_buf,_hs_rec_count,_hs_rec_stride,_hs_seen_slots,_hs_seen_slots_hi,_hs_unimpl_count,_hs_pluglog_buf,_hs_pluglog_count,_hs_slots_called_get,_hs_plugvtab_buf,_hs_tag_get,_fw_hs_host,_fw_hs_host_va,_fw_hs_install,_fw_hs_fold_cell,_fw_hs_trace,_fw_hs_reset,_fw_hs_count,_fw_hs_records,_fw_hs_installed \
    -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64,wasmExports \
    -Wl,--initial-memory=$((0x14000000)) -Wl,--max-memory=$((0x80000000)) \
    -o hs_route.cjs 2> emcc.log || { grep -v 'warning\|>>>\|^$' emcc.log | head -20; exit 1; }
fi
ls -la hs_route.cjs

# ---- 4. e2e (Phase A: fw_route で framework smoke / Phase B: hs_route で host shim 連鎖) ----
node "$H/hs_e2e.mjs" "$WFW/fw_image.bin" "$WFW/fw_route.cjs" "$W/hs_route.cjs" ${EXTRA+"${EXTRA[@]}"}
