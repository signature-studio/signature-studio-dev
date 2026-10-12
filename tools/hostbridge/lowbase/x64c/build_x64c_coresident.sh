#!/usr/bin/env bash
# build_x64c_coresident.sh — 同一 DLL (OTT) を 2 つの異なる V-shift base (A=0x10000, B=0x400000) で lift し、prefix (a_/b_) で関数名衝突を避けて
#   **1 つの wasm / 1 つの linear memory** に同居させる (per-plugin base + module prefix の実証; 「1 DLL = 1 Memory」を破る場合の方式 = m11 型の複数 PE 同居).
#   出力: work/coresident/co.cjs  (exports: _run_a/_run_b/_a_data_install/_b_data_install/_ott_alog_addr/_malloc), layout.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; LB="$HERE/.."; OTT="$LB/../../ott"
source "$LB/../../shared/env.sh"
DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"
BA=0x10000; BB=0x400000; OUT="$LB/work/coresident"; mkdir -p "$OUT/a" "$OUT/b"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
python3 "$OTT/lift/mkentries.py" "$OTT/ref/cov_all.json" "$OUT/entries.json" >/dev/null
for k in a b; do
  B=$BA; [ $k = b ] && B=$BB
  python3 "$HERE/lb_x64c.py" --base $B --prefix $k -- --pe "$DLL" --entries "$OUT/entries.json" --out "$OUT/$k" --closure 2 \
    --override 1801c8c00=ovr_handle_error_d --override 1801c8cb8=ovr_handle_error_f --override 1801a9a6c=ovr_sqrt_d --override 1801a9b38=ovr_sqrt_f | tail -2 | cut -c1-120
  python3 "$HERE/lb_data_gen.py" "$DLL" "$OUT/$k/ott_data.c" "$OUT/$k/lift_meta.json" $B | tail -1 | cut -c1-100
  sed -i "s/\bott_data_install\b/${k}_data_install/" "$OUT/$k/ott_data.c"
done
# 配置: A image 0x10000..0x318000, B image 0x400000..0x708000, ARENA_A/B (各 1MiB), GLOBAL_BASE 以降 static/stack/heap
ARENA_A=$((0x710000)); ARENA_B=$((0x810000)); GB=$((0x910000)); INIT=$((24<<20)); MAX=$((64<<20))
printf 'LB_BASE_A=%d\nLB_BASE_B=%d\nLB_ARENA_A=%d\nLB_ARENA_B=%d\nLB_GLOBAL_BASE=%d\nLB_INIT=%d\nLB_MAX=%d\n' $((BA)) $((BB)) $ARENA_A $ARENA_B $GB $INIT $MAX > "$OUT/layout.sh"
cat > "$OUT/glue2.c" <<'CEOF'
#include "ott_cpu.h"
void a_dispatch(uint64_t); void b_dispatch(uint64_t);
static uint8_t guest_stack[1 << 20] __attribute__((aligned(16)));
#define STACK_TOP ((uint64_t)(uintptr_t)guest_stack + sizeof(guest_stack) - 0x100)
static uint64_t run_common(void (*disp)(uint64_t), uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) {
    R[RSP] = STACK_TOP; R[RCX] = a0; R[RDX] = a1; R[R8] = a2; R[R9] = a3;
    X[0].q[0] = x0; X[0].q[1] = 0; X[1].q[0] = x1; X[1].q[1] = 0; X[2].q[0] = x2; X[2].q[1] = 0; X[3].q[0] = x3; X[3].q[1] = 0;
    R[RSP] -= 8; ST64(R[RSP], 0xdead0000ull);
    disp(va); return R[RAX];
}
uint64_t run_a(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) { return run_common(a_dispatch, va, a0, a1, a2, a3, x0, x1, x2, x3); }
uint64_t run_b(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) { return run_common(b_dispatch, va, a0, a1, a2, a3, x0, x1, x2, x3); }
CEOF
emcc -O1 -ffp-contract=off -fno-fast-math -I"$OTT/rt" -DLB_IMG_BASE=$BA \
  "$OUT/a/ott_lifted.c" "$OUT/b/ott_lifted.c" "$OUT/a/ott_data.c" "$OUT/b/ott_data.c" "$HERE/rt/ott_cpu.c" "$OUT/glue2.c" "$OTT/rt/ott_ovr.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=$GB -sENVIRONMENT=node,web,worker -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=_run_a,_run_b,_a_data_install,_b_data_install,_ott_alog_addr,_malloc -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -sINITIAL_MEMORY=$INIT -sMAXIMUM_MEMORY=$MAX -o "$OUT/co.cjs" 2>&1 | tail -10
echo "[build_x64c_coresident] OK: $OUT/co.cjs"
