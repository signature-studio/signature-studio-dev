#!/usr/bin/env bash
# P8: 合成 plugin カーネルを 構成別にビルド → work/
#   A: 静的 N 個リンク (非 PIC)     B: 単体 standalone wasm (plugin 別 module/memory)   C: MAIN+SIDE (PIC)
# 使い方: build.sh [N_STATIC=16]   軽量カーネル: P8_NST=1 P8_SUFFIX=_light build.sh (出力名に接尾辞)
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/env.sh"
NS=${1:-16}; SFX=${P8_SUFFIX:-}; NSTF="-DNST=${P8_NST:-32}"; S="$P8_DIR/src"; W="$P8_WORK"; mkdir -p "$W/obj" "$W/gen"
# 生成: 256 個の stage 関数 + 間接呼び table (guest 間接 call 相当)
{ for n in $(seq 0 255); do echo "static void N_(st$n)(void){ STAGE_BODY($n); }"; done
  echo "__attribute__((used)) void (*N_(tab)[256])(void) = {"; for n in $(seq 0 255); do echo "  N_(st$n),"; done; echo "};"; } > "$W/gen/stages.h"
INC="-I$S -I$W/gen"
# A) 静的: plugin n は GBASE = 16MiB + n*64KiB (rebase 済み lift 相当)・ABS と BASED の 2 系統
for mode in ABS BASED; do
  for n in $(seq 0 $((NS-1))); do
    emcc $P8_CFLAGS $INC $NSTF -DADDR_$mode -DPFX=p${n}_ -DPID=$n -DGBASE=$((0x1000000 + n*0x10000)) -c "$S/p8_kernel.c" -o "$W/obj/k${SFX}_${mode}_$n.o" &
    while [ "$(jobs -rp | wc -l)" -ge 4 ]; do wait -n; done
  done
done; wait
emcc $P8_CFLAGS $INC -c "$S/p8_cpu.c" -o "$W/obj/cpu.o"
for mode in ABS BASED; do
  for n in 1 4 $NS; do
    : > "$W/gen/static_decl.h"; : > "$W/gen/static_tab.h"
    for i in $(seq 0 $((n-1))); do echo "DECL($i)" >> "$W/gen/static_decl.h"; echo "E($i)" >> "$W/gen/static_tab.h"; done
    objs=""; for i in $(seq 0 $((n-1))); do objs="$objs $W/obj/k${SFX}_${mode}_$i.o"; done
    emcc $P8_CFLAGS $INC -DP8_STATIC -DP8_N=$n "$S/p8_host.c" $objs "$W/obj/cpu.o" -o "$W/static_${mode,,}${SFX}_$n.wasm" \
      -sSTANDALONE_WASM -Wl,--no-entry -sINITIAL_MEMORY=$((64<<20)) -sSTACK_SIZE=64KB -sALLOW_MEMORY_GROWTH=0 \
      -sEXPORTED_FUNCTIONS=_init_all,_chain_block,_chain_n,_host_in_ptr,_plugin_in,_plugin_out,_call_one
    echo "[static_${mode,,}${SFX}_$n] $(stat -c %s "$W/static_${mode,,}${SFX}_$n.wasm") B"
  done
done
# B) 単体 standalone: ABS@0x30000000 (現行 lift の VA・initial=864MiB 級) / ABS 低位 (rebase 済み) / BASED
b_one() { local name=$1 mode=$2 gbase=$3 initmem=$4
  emcc $P8_CFLAGS $INC $NSTF -DADDR_$mode -DGBASE=$gbase "$S/p8_kernel.c" "$S/p8_cpu.c" -o "$W/$name$SFX.wasm" \
    -sSTANDALONE_WASM -Wl,--no-entry -sINITIAL_MEMORY=$initmem -sSTACK_SIZE=64KB -sALLOW_MEMORY_GROWTH=0 \
    -sEXPORTED_FUNCTIONS=_plg_process,_plg_in,_plg_out,_plg_init
  echo "[$name$SFX] $(stat -c %s "$W/$name$SFX.wasm") B"; }
b_one sep_abs_hi ABS $((0x30000000)) $((0x30010000 + 0x100000))
b_one sep_abs_lo ABS $((0x1000000)) $((64<<20))
b_one sep_based BASED 0 $((16<<20))
# C) MAIN_MODULE=2 (host) + SIDE_MODULE=2 (-fPIC; default / hidden visibility)
emcc $P8_CFLAGS -I"$S" -fPIC "$S/p8_host.c" -o "$W/dyn_main.cjs" -sMAIN_MODULE=2 -sINITIAL_MEMORY=$((64<<20)) -sALLOW_MEMORY_GROWTH=0 \
  -sENVIRONMENT=node,web,worker -sMODULARIZE=1 -sEXPORT_NAME=createMain -sINVOKE_RUN=0 -Wl,--no-entry -sFORCE_FILESYSTEM=1 \
  -sEXPORTED_FUNCTIONS=_load_plugin,_chain_block,_chain_n,_host_in_ptr,_plugin_in,_plugin_out,_call_one,_malloc \
  -sEXPORTED_RUNTIME_METHODS=FS,HEAPU8,HEAPF32,stringToUTF8,lengthBytesUTF8
echo "[dyn_main] $(stat -c %s "$W/dyn_main.wasm") B"
for v in def hid; do
  vis=""; [ "$v" = hid ] && vis="-fvisibility=hidden"
  emcc $P8_CFLAGS $INC $NSTF -fPIC $vis -DADDR_BASED "$S/p8_kernel.c" "$S/p8_cpu.c" -o "$W/side_$v$SFX.wasm" -sSIDE_MODULE=2 \
    -sEXPORTED_FUNCTIONS=_plg_process,_plg_in,_plg_out,_plg_init
  echo "[side_$v$SFX] $(stat -c %s "$W/side_$v$SFX.wasm") B"
done
