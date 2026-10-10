#!/usr/bin/env bash
# sigprobe.sh — adapter が m11 IR の GUI declare 署名を wasm-ld レベルで満たすことの検証 (CAB-156)。
#   IR の GUI declare (既定 fixture / 引数で m11 boot_final.ll 等) を全て参照する probe.o を作り、
#   (1) 改名 shim + gui_adapt_w32.c  -> "function signature mismatch" 0 件・未解決シンボル 0 件であること
#   (2) 陰性対照: adapter 無し (int64 wrapper のみ) -> 不一致が検出されること
# usage: sigprobe.sh [ir.ll]    exit 0 = (1)==0 かつ (2)>0
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$HERE/.."; BUILD="$GUI/build"; W="$BUILD/sigprobe"; mkdir -p "$W"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
python3 "$GUI/gen_api.py" >/dev/null
IRARG=(); [ $# -ge 1 ] && IRARG=(--ir "$1")
python3 "$HERE/gen_adapt.py" "${IRARG[@]}" --no-md --probe "$W/probe.ll" | tail -1
CF=(-O1 -w -pthread -I "$GUI/include" -I "$GUI/src" -I "$BUILD")
emcc -c "${CF[@]}" "$W/probe.ll" -o "$W/probe.o"
for f in "$GUI"/src/gui_core.c "$GUI"/src/gui_gdi.c "$BUILD"/gui_stubs.c; do emcc -c "${CF[@]}" -include "$BUILD/gui_rename.h" "$f" -o "$W/$(basename "$f" .c).o"; done
emcc -c "${CF[@]}" "$BUILD/gui_adapt_w32.c" -o "$W/adapt.o"
emcc -c "${CF[@]}" "$BUILD/gui_wrap_i64.c" -o "$W/wrap.o"
BASE=("$W/probe.o" "$W/gui_core.o" "$W/gui_gdi.o" "$W/gui_stubs.o" "$GUI/src/gui_platform.c" "$GUI/src/gui_reach.c" "$BUILD/gui_reach_tab.c")
LF=(-pthread -O1 -I "$GUI/include" -I "$GUI/src" -sGLOBAL_BASE=1048576 --no-entry -Wl,--no-gc-sections -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXPORTED_FUNCTIONS=_gui_shared_ptr)
emcc "${LF[@]}" "${BASE[@]}" "$W/adapt.o" -o "$W/with_adapt.js" >"$W/with_adapt.log" 2>&1 || { tail -20 "$W/with_adapt.log"; exit 1; }
emcc "${LF[@]}" "${BASE[@]}" "$W/wrap.o" -o "$W/no_adapt.js" >"$W/no_adapt.log" 2>&1 || true
A=$(grep -c "signature mismatch" "$W/with_adapt.log" || true); B=$(grep -c "signature mismatch" "$W/no_adapt.log" || true)
U=$(wasm-objdump -j Import -x "$W/with_adapt.wasm" | grep -cE "<env\.(gui_|[A-Z])" || true)   # 未解決のまま wasm import になった shim/GUI シンボル
echo "[sigprobe] declares=$(grep -c '^declare' "$W/probe.ll")  with adapter: signature mismatch=$A unresolved-imports=$U | without adapter (negative control): mismatch=$B"
[ "$A" = 0 ] && [ "$U" = 0 ] && [ "$B" -gt 0 ]
