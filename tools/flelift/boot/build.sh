#!/usr/bin/env bash
# build.sh — FLE-2: 単一 variant の再 build (診断・反復用)。
#   bash tools/flelift/boot/build.sh [variant]     # plain|strict|nosx|chk (既定 plain)
# lift 済み (work/boot/lift/fle_lifted.c) と生成物 (fle_imp_bridge.c / fle_textwin.c) を
# そのまま使い、fle_boot.c 等の C 変更だけを反映して link し直す。boot_e2e.sh は全 variant
# を一括で作るので、C 側の反復中はこちらを使う (wasm 142MB の link は 1 本あたり数十秒)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
SX="$(cd "$FLE/../shimx" && pwd)"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"   # 別 route の並走用に上書き可 (#2702)
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
V="${1:-plain}"
case "$V" in plain|strict|nosx|chk) ;; *) echo "usage: build.sh [plain|strict|nosx|chk]"; exit 1;; esac
# #970: 最適化変種 (既定 -O0)。FLE_LABEL は obj・出力名の接頭 (変種ごとに分けて -O0 の obj を上書きしない)。
OPT="${FLE_CC_OPT:--O0}"
LBL="${FLE_LABEL:-$V}"
mkdir -p "$W/obj" "$W/tmp"
export TMPDIR="$W/tmp"
set +u; source "${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" > /dev/null 2>&1; set -u

# ---- 生成物が無い場合のみ gen (entries/link_defs/imp bridge/textwin) ----
[ -f "$W/fle_entries_boot.json" ] || python3 "$HERE/gen_boot.py" --pe "$PE" --out "$W"
[ -f "$W/fle_imp_bridge.c" ]       || python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$W/lift/lift_meta.json" --out "$W"
[ -f "$W/nosx/fle_imp_bridge.c" ]  || python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$W/lift/lift_meta.json" --out "$W/nosx" --nosx
[ -f "$W/fle_textwin.c" ]          || python3 "$HERE/gen_boot.py" --pe "$PE" --out "$W"
if [ ! -f "$W/obj/.sx_done" ]; then
  for f in "$SX"/src/*.c; do b="$(basename "$f" .c)"; emcc -c "$f" -o "$W/obj/sx_$b.o" -O1 -w \
    -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing -I"$SX/src"; done
  touch "$W/obj/.sx_done"
fi

CCF="$OPT -w -Wno-error=int-conversion -Wno-implicit-function-declaration -g1"
SHARDS="${FLE_SHARDS:-1}"
CAP_MB="${FLE_CC_RSS_CAP_MB:-$([ "$SHARDS" -gt 1 ] && echo 5000 || echo 11000)}"
cc() { local src="$1" obj="$2"; shift 2
  if [ ! -f "$obj" ] || [ "$src" -nt "$obj" ]; then
    local rc=0 log="$W/rss_cc_$(basename "$obj" .o).log"
    python3 "$HERE/rss_cap.py" --cap-mb "$CAP_MB" --log "$log" -- emcc -c "$src" -o "$obj" "$@" || rc=$?
    if [ "$rc" = 143 ] && grep -q 'CAP EXCEEDED' "$log"; then
      echo "[build] clang RSS cap 超過: $src peak=$(grep -o 'peak=[0-9]*' "$log" | tail -1 | cut -d= -f2)MB (cap ${CAP_MB}MB, log $log)"; exit 1
    fi
    [ "$rc" = 0 ] || exit "$rc"
  fi; }
CPUDEFS="$(cat "$W/fle_link_defs.txt")"
BRIDGE="$W/fle_imp_bridge.c"; NOSX=0
[ "$V" = nosx ] && { BRIDGE="$W/nosx/fle_imp_bridge.c"; NOSX=1; }
CHKF=""; [ "$V" = chk ] && CHKF="-DFLE_CHK"
NOSX_DEF=$([ "$V" = nosx ] && echo 1 || echo 0)
EXPORTS="_fle_boot_enter,_fle_boot_set_strict,_fle_units_run,_fle_units_total,_fle_units_empty,_fle_boot_stage,_fle_n_getmem,_fle_n_freemem,_fle_n_longjmp,_fle_n_exit,_fle_n_getproc,_fle_n_soft,_fle_n_soft_uniq,_fle_soft_name,_fle_soft_count,_fle_va_calls,_fle_va_bytes,_fle_n_cb,_fle_unit_proc,_fle_run,_fle_rget,_fle_data_install,_fle_init,_fle_reset,_fle_boot_set_nullpage,_fle_boot_set_blkdiag,_fle_blkdiag_stat,_fle_boot_set_ipp,_fle_ipp_total,_fle_ipp_names,_fle_ipp_name,_fle_ipp_count,_fle_ipp_site,_fle_ipp_stop_name,_fle_ipp_stop_site"
[ "$NOSX_DEF" = 1 ] || EXPORTS="$EXPORTS,_shimx_set_trace,_shimx_init"
# FLE_SHARDS>1: fle_lifted_s<k>.c を xargs -P3 で並列 clang (各 cap 付き)。既定 1 は単一 fle_lifted.c。
LIFTED_OBJS="$W/obj/${LBL}_lifted.o"
if [ "$SHARDS" -gt 1 ]; then
  cc_shard() { cc "${FLE_LIFT_DIR:-$W/lift}/fle_lifted_s$1.c" "$W/obj/${LBL}_lifted_s$1.o" $CCF $CHKF -I"$FLE/rt" -I"$HERE"; }
  export -f cc cc_shard
  export W V LBL FLE HERE CAP_MB CCF CHKF FLE_LIFT_DIR
  seq 0 $((SHARDS - 1)) | xargs -P "${FLE_CC_JOBS:-3}" -I{} bash -c 'cc_shard {}'
  LIFTED_OBJS=""
  for k in $(seq 0 $((SHARDS - 1))); do LIFTED_OBJS="$LIFTED_OBJS $W/obj/${LBL}_lifted_s$k.o"; done
else
  cc "${FLE_LIFT_DIR:-$W/lift}/fle_lifted.c"  "$W/obj/${LBL}_lifted.o"  $CCF $CHKF -I"$FLE/rt" -I"$HERE"
fi
cc "${FLE_LIFT_DIR:-$W/lift}/fle_data.c"    "$W/obj/${LBL}_data.o"    $CCF $CHKF -I"$FLE/rt"
cc "$FLE/rt/fle_cpu.c"     "$W/obj/${LBL}_cpu.o"     $CCF $CHKF -I"$FLE/rt" $CPUDEFS
cc "$FLE/rt/fle_glue.c"    "$W/obj/${LBL}_glue.o"    $CCF $CHKF -I"$FLE/rt"
cc "$BRIDGE"               "$W/obj/${LBL}_bridge.o"  $CCF $CHKF -I"$FLE/rt" -I"$HERE"
cc "$W/fle_textwin.c"      "$W/obj/${LBL}_tw.o"      $CCF $CHKF -I"$FLE/rt" -I"$HERE"
cc "$HERE/fle_boot.c"      "$W/obj/${LBL}_boot.o"    $CCF $CHKF -I"$FLE/rt" -I"$HERE" -I"$SX/src" \
   -DFLEBOOT_STRICT=$([ "$V" = strict ] && echo 1 || echo 0) -DFLEBOOT_NOSX=$NOSX_DEF
OBJS="$LIFTED_OBJS $W/obj/${LBL}_data.o $W/obj/${LBL}_cpu.o $W/obj/${LBL}_glue.o $W/obj/${LBL}_bridge.o $W/obj/${LBL}_tw.o $W/obj/${LBL}_boot.o"
[ $NOSX = 1 ] || OBJS="$OBJS $W/obj/sx_*.o"
emcc $OBJS -o "$W/fleboot_$LBL.cjs.tmp" \
  $OPT -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=flebootcreate -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPU32 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) 2> "$W/link_$LBL.log" || { tail -40 "$W/link_$LBL.log"; exit 1; }
mv "$W/fleboot_$LBL.cjs.tmp" "$W/fleboot_$LBL.cjs"
echo "[build] $V: mismatch=$(grep -c 'signature mismatch' "$W/link_$LBL.log" || true) undefined=$(grep -c 'undefined symbol' "$W/link_$LBL.log" || true) dup=$(grep -c 'duplicate symbol' "$W/link_$LBL.log" || true) -> $W/fleboot_$LBL.cjs ($(stat -c%s "$W/fleboot_$LBL.cjs.wasm") B)"
