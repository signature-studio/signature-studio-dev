#!/usr/bin/env bash
# pump_spike.c → work/spike/{plain,asyncify,native}.wasm  (clang + wasm-opt のみ。emscripten glue 不要)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; OUT="$HERE/../work/spike"; mkdir -p "$OUT"
CLANG=/opt/emsdk/upstream/bin/clang; WOPT=/opt/emsdk/upstream/bin/wasm-opt
[ -x "$WOPT" ] || WOPT=wasm-opt
COMMON=(--target=wasm32 -O2 -nostdlib -fno-builtin -Wl,--no-entry -Wl,--export-dynamic -Wl,--allow-undefined -Wl,-z,stack-size=65536)
$CLANG "${COMMON[@]}" -Wl,--initial-memory=2097152 -o "$OUT/plain.wasm" "$HERE/pump_spike.c"
$CLANG "${COMMON[@]}" -DNATIVE -matomics -mbulk-memory -Wl,--shared-memory -Wl,--import-memory -Wl,--initial-memory=2097152 -Wl,--max-memory=2097152 -o "$OUT/native.wasm" "$HERE/pump_spike.c"
# Asyncify: get_message を async import として指定。全体を最適化付きで instrument
$WOPT -O2 --asyncify --pass-arg=asyncify-imports@env.get_message "$OUT/plain.wasm" -o "$OUT/asyncify.wasm"
# 実 lifted wasm (M11 5.7MB) への Asyncify 適用コスト (全関数が間接呼び出し経由で到達しうる最悪ケースの代理: env.exit を async とみなす)
ls -la "$OUT"/*.wasm
