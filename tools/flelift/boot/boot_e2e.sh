#!/usr/bin/env bash
# boot_e2e.sh — FLE-2: x64c lift による FLEngine boot 連鎖 (1 コマンド検証)。
#
#   bash tools/flelift/boot/boot_e2e.sh              # 全 variant (lift 共通 1 回 + link 4 種 + 実行)
#   bash tools/flelift/boot/boot_e2e.sh --fast       # lift 済みなら lift skip、plain のみ実行
#
# variant:
#   plain  shimx bridge + soft GUI (本命の測定)   strict  soft を fail-fast 化 (link 構成の証跡)
#   nosx   shimx をリンクしない (fle_cpu imp のみ = shimx 寄与の対照)   chk  FLE_CHK 住所ガード (診断)
#   trace  plain と同一バイナリを SHIMX_TRACE=1 で実行 (shimx 呼出トレース)
#
# 各 link で signature mismatch / undefined symbol / duplicate symbol を数え、
# 結果を work/boot/link_<variant>.log と results/ に残す。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
SX="$(cd "$FLE/../shimx" && pwd)"
W="$FLE/work/boot"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
FAST=0; [ "${1:-}" = "--fast" ] && FAST=1
mkdir -p "$W/obj" "$W/tmp" "$HERE/results"
export TMPDIR="$W/tmp"
set +u; source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1; set -u
NODE="$(command -v node || echo ~/.local/share/pnpm/bin/node)"

LIFT="$W/lift"
# ---- 1. 生成 phase A: entries + .text 窓 (meta 不要) ----
python3 "$HERE/gen_boot.py" --pe "$PE" --out "$W"

# ---- 2. lift (boot 用 entries: +entry_point 0x1376820, +longjmp 断片 0x1376840, +override) ----
if [ ! -f "$LIFT/fle_lifted.c" ] || [ "$FAST" = 0 ] || [ "$W/fle_entries_boot.json" -nt "$LIFT/fle_lifted.c" ]; then
  echo "[boot_e2e] lift (x64c) ..."
  # closure 既定 2 (FLE-2 実測: closure 0 = 16 unit / closure 2 = 40 unit。20,479 → 29,415 関数)。
  # FLE_LIFT_CLOSURE=0 で旧既定に戻せる。
  python3 "$FLE/x64c.py" --pe "$PE" --entries "$W/fle_entries_boot.json" --out "$LIFT" --closure ${FLE_LIFT_CLOSURE:-2} \
    --img 0x400000 --shift 0 --img-size 0x18c0000 --impbase 0x1D80000 \
    --override 0x4126f0=fle_ov_longjmp --override 0x409410=fle_ov_getmem \
    --override 0x409440=fle_ov_freemem --override 0x4120c0=fle_ov_initunits
  python3 "$FLE/fle_data_gen.py" "$PE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json"
fi

# ---- 3. 生成 phase B: imp bridge (lift_meta の iat_map から) ----
python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$LIFT/lift_meta.json" --out "$W"
python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$LIFT/lift_meta.json" --out "$W/nosx" --nosx

# ---- 3. shimx objects (ST, tools/shimx 無改変) ----
if [ ! -f "$W/obj/.sx_done" ] || [ "$SX/src/shimx.h" -nt "$W/obj/.sx_done" ]; then
  for f in "$SX"/src/*.c; do
    b="$(basename "$f" .c)"
    emcc -c "$f" -o "$W/obj/sx_$b.o" -O1 -w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing -I"$SX/src"
  done
  touch "$W/obj/.sx_done"
fi

CCF="-O0 -w -Wno-error=int-conversion -Wno-implicit-function-declaration -g1"
CAP_MB="${FLE_CC_RSS_CAP_MB:-11000}"
cc() { # cc <src> <obj> [flags...]  (emcc -c は RSS 上限付き。超過は非 0 で止める)
  local src="$1" obj="$2"; shift 2
  if [ ! -f "$obj" ] || [ "$src" -nt "$obj" ]; then
    local rc=0 log="$W/rss_cc_$(basename "$obj" .o).log"
    python3 "$HERE/rss_cap.py" --cap-mb "$CAP_MB" --log "$log" -- emcc -c "$src" -o "$obj" "$@" || rc=$?
    if [ "$rc" = 143 ] && grep -q 'CAP EXCEEDED' "$log"; then
      echo "[build] clang RSS cap 超過: $src peak=$(grep -o 'peak=[0-9]*' "$log" | tail -1 | cut -d= -f2)MB (cap ${CAP_MB}MB, log $log)"; exit 1
    fi
    [ "$rc" = 0 ] || exit "$rc"
  fi
}
CPUDEFS="$(cat "$W/fle_link_defs.txt")"
BUILD() { # BUILD <variant> <bridge.c> [extra emcc flags...] [-- nosx]
  local v="$1" bridge="$2"; shift 2
  local nosx=0; local flags=()
  local args=()
  for a in "$@"; do if [ "$a" = "--nosx" ]; then nosx=1; else args+=("$a"); fi; done
  local CHKF=""
  if [ "$v" = "chk" ]; then CHKF="-DFLE_CHK"; fi
  cc "$LIFT/fle_lifted.c"  "$W/obj/${v}_lifted.o"  $CCF $CHKF -I"$FLE/rt" -I"$HERE"
  cc "$LIFT/fle_data.c"    "$W/obj/${v}_data.o"    $CCF $CHKF -I"$FLE/rt"
  cc "$FLE/rt/fle_cpu.c"   "$W/obj/${v}_cpu.o"     $CCF $CHKF -I"$FLE/rt" $CPUDEFS
  cc "$FLE/rt/fle_glue.c"  "$W/obj/${v}_glue.o"    $CCF $CHKF -I"$FLE/rt"
  cc "$bridge"             "$W/obj/${v}_bridge.o"  $CCF $CHKF -I"$FLE/rt" -I"$HERE"
  cc "$W/fle_textwin.c"    "$W/obj/${v}_tw.o"      $CCF $CHKF -I"$FLE/rt" -I"$HERE"
  cc "$HERE/fle_boot.c"    "$W/obj/${v}_boot.o"    $CCF $CHKF -I"$FLE/rt" -I"$HERE" -I"$SX/src" \
     -DFLEBOOT_STRICT=$([ "$v" = strict ] && echo 1 || echo 0) -DFLEBOOT_NOSX=$([ "$v" = nosx ] && echo 1 || echo 0)
  local OBJS="$W/obj/${v}_lifted.o $W/obj/${v}_data.o $W/obj/${v}_cpu.o $W/obj/${v}_glue.o $W/obj/${v}_bridge.o $W/obj/${v}_tw.o $W/obj/${v}_boot.o"
  [ $nosx = 1 ] || OBJS="$OBJS $W/obj/sx_*.o"
  local EXPORTS=_fle_boot_enter,_fle_boot_set_strict,_fle_units_run,_fle_units_total,_fle_units_empty,_fle_boot_stage,_fle_n_getmem,_fle_n_freemem,_fle_n_longjmp,_fle_n_exit,_fle_n_getproc,_fle_n_soft,_fle_n_soft_uniq,_fle_soft_name,_fle_soft_count,_fle_va_calls,_fle_va_bytes,_fle_n_cb,_fle_unit_proc,_fle_run,_fle_rget,_fle_data_install,_fle_init,_fle_reset,_fle_boot_set_nullpage,_fle_boot_set_blkdiag,_fle_blkdiag_stat,_fle_boot_set_ipp,_fle_ipp_total,_fle_ipp_names,_fle_ipp_name,_fle_ipp_count
  [ $nosx = 1 ] || EXPORTS="$EXPORTS,_shimx_set_trace,_shimx_init"
  emcc $OBJS -o "$W/fleboot_$v.cjs.tmp" \
    -O0 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
    -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=flebootcreate -sEXIT_RUNTIME=1 \
    -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPU32 \
    -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
    "${args[@]:-}" 2> "$W/link_$v.log" || { tail -30 "$W/link_$v.log"; echo "[boot_e2e] link fail ($v)"; exit 1; }
  mv "$W/fleboot_$v.cjs.tmp" "$W/fleboot_$v.cjs"
  local mm un dup
  mm=$(grep -c 'signature mismatch' "$W/link_$v.log" || true)
  un=$(grep -c 'undefined symbol'  "$W/link_$v.log" || true)
  dup=$(grep -c 'duplicate symbol' "$W/link_$v.log" || true)
  echo "[boot_e2e] link $v: mismatch=$mm undefined=$un duplicate=$dup -> fleboot_$v.cjs ($(stat -c%s "$W/fleboot_$v.wasm" 2>/dev/null || stat -c%s "$W/fleboot_$v.cjs.wasm" 2>/dev/null || echo '?') B)"
}

echo "[boot_e2e] build variants ..."
BUILD plain  "$W/fle_imp_bridge.c"
BUILD strict "$W/fle_imp_bridge.c"
BUILD nosx   "$W/nosx/fle_imp_bridge.c" --nosx
BUILD chk    "$W/fle_imp_bridge.c"

# ---- 4. run ----
run() { # run <variant> <out.json> [args...]
  local v="$1" out="$2"; shift 2
  FLE_BOOT_VARIANT="$v" "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_$v.cjs" "$out" "$@" 2> "$W/run_$v.stderr" || {
    echo "[boot_e2e] runner exit != 0 ($v) — stderr は $W/run_$v.stderr"; tail -5 "$W/run_$v.stderr"; }
  grep -o 'FLEBOOT_RESULT .*' "$W/run_$v.stderr" || true
}

echo "[boot_e2e] run plain (boot only) ..."
# 注: survey を同プロセスで回すと unit 283 (i=283, 状態依存 hang) で停止する実測があるため
# boot 単独で実行する。survey は survey_drive.sh (セグメント実行 + 再開) を使うこと。
FLE_BOOT_VARIANT=plain "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_plain.cjs" "$HERE/results/boot_summary.json" --boot-only 2>&1 | tee "$W/run_plain.log" | grep 'FLEBOOT_RESULT' || true
[ -f "$W/run_plain.stderr" ] || cp "$W/run_plain.log" "$W/run_plain.stderr" 2>/dev/null || true

if [ "$FAST" = 0 ]; then
  echo "[boot_e2e] run strict / nosx / chk (boot only) ..."
  FLE_BOOT_VARIANT=strict "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_strict.cjs" "$HERE/results/boot_summary_strict.json" --boot-only > "$W/run_strict.log" 2>&1 || true
  grep 'FLEBOOT_RESULT' "$W/run_strict.log" || true
  FLE_BOOT_VARIANT=nosx   "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_nosx.cjs"   "$HERE/results/boot_summary_nosx.json"   --boot-only > "$W/run_nosx.log" 2>&1 || true
  grep 'FLEBOOT_RESULT' "$W/run_nosx.log" || true
  FLE_BOOT_VARIANT=chk    "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_chk.cjs"    "$HERE/results/boot_summary_chk.json"    --boot-only > "$W/run_chk.log" 2>&1 || true
  grep 'FLEBOOT_RESULT' "$W/run_chk.log" || true
  echo "[boot_e2e] run trace (plain binary + SHIMX_TRACE=1, boot only) ..."
  FLE_BOOT_TRACE=1 FLE_BOOT_VARIANT=trace "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_plain.cjs" "$HERE/results/boot_summary_trace.json" --boot-only > "$W/run_trace.log" 2>&1 || true
  grep 'FLEBOOT_RESULT' "$W/run_trace.log" || true
fi

echo "[boot_e2e] done. results: $HERE/results/"
