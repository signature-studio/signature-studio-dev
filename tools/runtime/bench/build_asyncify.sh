#!/usr/bin/env bash
# 実 lifted wasm (stage 済み M10/M11) に wasm-opt --asyncify を適用し、サイズ増と速度比を測る素材を work/asyncify/ に作る。
# 前提: node tools/runtime/stage_wasm.mjs 済み。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; W="$HERE/../work"; S="$W/wasm"; O="$W/asyncify"; mkdir -p "$O"
WOPT=/opt/emsdk/upstream/bin/wasm-opt
M10=$(ls "$S"/m10-ott.*.wasm); M11=$(ls "$S"/m11-boot.*.wasm)
"$WOPT" -O2 "$M10" -o "$O/m10_O2.wasm"
"$WOPT" -O2 --asyncify --pass-arg=asyncify-imports@env.WriteFile "$M10" -o "$O/m10_async.wasm"
"$WOPT" -O2 --asyncify --pass-arg=asyncify-imports@env.WriteFile --pass-arg=asyncify-ignore-indirect "$M10" -o "$O/m10_async_noind.wasm"
"$WOPT" -O2 "$M11" -o "$O/m11_O2.wasm"
"$WOPT" -O2 --asyncify --pass-arg=asyncify-imports@env.__syscall_openat "$M11" -o "$O/m11_async.wasm"
printf '%-22s %10s\n' file bytes; for f in "$O"/*.wasm; do printf '%-22s %10d\n' "$(basename "$f")" "$(stat -c %s "$f")"; done
