#!/usr/bin/env bash
# build_fle_boot.sh — RT-10 (#128): 実 FLEngine x64c lift (boot 連鎖, 約 126MB wasm) を
#   (1) node 版 (tools/flelift/boot/build.sh plain = 参照値用) と
#   (2) Chrome Worker 用 web/ESM 版 (同一 .o を ENVIRONMENT=web,worker で再 link)
# の 2 通りに build する。lift/gen/shimx obj は tools/flelift/boot/boot_e2e.sh の phase 1–3 と同一手順。
#   bash tools/runtime/rt10/build_fle_boot.sh      → tools/flelift/work/boot/{fleboot_plain.cjs(.wasm), web/fleweb.mjs(.wasm)}
# 所要は各工程を stderr に [t=秒] で出す。素材: FL_WIN64_DIR (fl-win64) と [EMSDK] (toolchain-emsdk, EMSDK_ENV で上書き可。docs/REFERENCES.md)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
FLE="$REPO/tools/flelift"
BOOT="$FLE/boot"
source "$REPO/tools/shared/env.sh"
SX="$REPO/tools/shimx"
W="$FLE/work/boot"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
mkdir -p "$W/obj" "$W/tmp" "$W/web"
export TMPDIR="$W/tmp"
set +u; source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" > /dev/null 2>&1; set -u
T0=$(date +%s.%N); tick() { echo "[t=$(echo "$(date +%s.%N) - $T0" | bc)] $*" >&2; }
LIFT="$W/lift"

tick "gen phase A"
python3 "$BOOT/gen_boot.py" --pe "$PE" --out "$W"
if [ ! -f "$LIFT/fle_lifted.c" ] || [ "$W/fle_entries_boot.json" -nt "$LIFT/fle_lifted.c" ]; then
  tick "lift (x64c, closure ${FLE_LIFT_CLOSURE:-2})"
  python3 "$FLE/x64c.py" --pe "$PE" --entries "$W/fle_entries_boot.json" --out "$LIFT" --closure ${FLE_LIFT_CLOSURE:-2} \
    --img 0x400000 --shift 0 --img-size 0x18c0000 --impbase 0x1D80000 \
    --override 0x4126f0=fle_ov_longjmp --override 0x409410=fle_ov_getmem \
    --override 0x409440=fle_ov_freemem --override 0x4120c0=fle_ov_initunits
  tick "data gen"
  python3 "$FLE/fle_data_gen.py" "$PE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json"
fi
tick "gen phase B (imp bridge)"
python3 "$BOOT/gen_boot.py" --pe "$PE" --meta "$LIFT/lift_meta.json" --out "$W"
python3 "$BOOT/gen_boot.py" --pe "$PE" --meta "$LIFT/lift_meta.json" --out "$W/nosx" --nosx

tick "shimx objs"
for f in "$SX"/src/*.c; do
  b="$(basename "$f" .c)"
  emcc -c "$f" -o "$W/obj/sx_$b.o" -O1 -w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing -I"$SX/src"
done
touch "$W/obj/.sx_done"

tick "build.sh plain (objs + node link)"
bash "$BOOT/build.sh" plain
tick "node link done"

V=plain
EXPORTS=_fle_boot_enter,_fle_boot_set_strict,_fle_units_run,_fle_units_total,_fle_units_empty,_fle_boot_stage,_fle_n_getmem,_fle_n_freemem,_fle_n_longjmp,_fle_n_exit,_fle_n_getproc,_fle_n_soft,_fle_n_soft_uniq,_fle_soft_name,_fle_soft_count,_fle_va_calls,_fle_va_bytes,_fle_n_cb,_fle_unit_proc,_fle_run,_fle_rget,_fle_data_install,_fle_init,_fle_reset,_fle_boot_set_nullpage,_fle_boot_set_blkdiag,_fle_blkdiag_stat,_shimx_set_trace,_shimx_init
OBJS="$W/obj/${V}_lifted.o $W/obj/${V}_data.o $W/obj/${V}_cpu.o $W/obj/${V}_glue.o $W/obj/${V}_bridge.o $W/obj/${V}_tw.o $W/obj/${V}_boot.o $W/obj/sx_*.o"
tick "web link (ENVIRONMENT=web,worker, ESM)"
emcc $OBJS -o "$W/web/fleweb.mjs" \
  -O0 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=web,worker -sMODULARIZE=1 -sEXPORT_ES6=1 -sEXPORT_NAME=flebootcreate -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=UTF8ToString,HEAPU8,HEAPU32 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) 2> "$W/link_web.log" || { tail -30 "$W/link_web.log"; exit 1; }
tick "web link done"
ls -l "$W/fleboot_plain.cjs" "$W/fleboot_plain.cjs.wasm" "$W/web/" >&2
sha256sum "$W/fleboot_plain.cjs.wasm" "$W/web/fleweb.wasm" >&2
