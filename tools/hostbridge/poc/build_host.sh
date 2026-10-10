#!/usr/bin/env bash
# build_host.sh — mini VST2 host (freestanding wasm32) をビルド. emsdk 同梱 clang + wasm-ld を直接使用.
set -euo pipefail
HB="$(cd -- "$(dirname -- "$0")/.." && pwd)"
CLANG=/opt/emsdk/upstream/bin/clang
mkdir -p "$HB/work"
"$CLANG" --target=wasm32 -O2 -nostdlib -ffreestanding -fno-builtin -I "$HB/poc" \
  -Wl,--no-entry -Wl,--export-dynamic -Wl,--export-table -Wl,--allow-undefined \
  -Wl,-z,stack-size=262144 -Wl,--initial-memory=2097152 \
  "$HB/poc/host_vst2.c" -o "$HB/work/host_vst2.wasm"
ls -la "$HB/work/host_vst2.wasm"
