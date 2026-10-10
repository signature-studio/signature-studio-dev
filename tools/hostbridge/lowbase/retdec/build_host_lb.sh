#!/usr/bin/env bash
# build_host_lb.sh — mini VST2 host (tools/hostbridge/poc/host_vst2.c) を lowbase/work へビルド (poc/build_host.sh と同コマンド; 出力先のみ別).
set -euo pipefail
LB="$(cd -- "$(dirname -- "$0")/.." && pwd)"; HB="$LB/.."
mkdir -p "$LB/work"
/opt/emsdk/upstream/bin/clang --target=wasm32 -O2 -nostdlib -ffreestanding -fno-builtin -I "$HB/poc" \
  -Wl,--no-entry -Wl,--export-dynamic -Wl,--export-table -Wl,--allow-undefined -Wl,-z,stack-size=262144 -Wl,--initial-memory=2097152 \
  "$HB/poc/host_vst2.c" -o "$LB/work/host_vst2.wasm"
