#!/usr/bin/env bash
# lift 産物 IR の declare 署名と shimx の定義署名が wasm レベルで一致するかを検査する。
#   RetDec は API によって HANDLE/enum/REFCLSID を i64 で declare することがあり (acmMetrics, CoCreateInstance ...)、
#   不一致のまま wasm-ld すると「signature mismatch」→ 実行時 trap になる。IR + shimx 全ソースをリンクして警告を数える。
#   使い方: bash scripts/verify_sig.sh <ir.ll> [tag]      → 不一致 0 で exit 0、あれば一覧を出して exit 1
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
IR="$1"; TAG="${2:-ir}"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
mkdir -p "$HERE/work/sig"
LOG="$HERE/work/sig/$TAG.log"
emcc "$IR" "$HERE"/src/*.c -o "$HERE/work/sig/$TAG.js" -w -Wno-error=int-conversion -O0 -sALLOW_MEMORY_GROWTH=1 \
    -sENVIRONMENT=node -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sGLOBAL_BASE=268435456 \
    -Wl,--initial-memory=$((0x12000000)) -Wl,--max-memory=$((0x72000000)) -Wl,--allow-multiple-definition > "$LOG" 2>&1 || { tail -5 "$LOG"; echo "[verify_sig] $TAG: リンク失敗"; exit 1; }
N=$(grep -ci "function signature mismatch" "$LOG" || true)
echo "[verify_sig] $TAG: signature mismatch = $N"
if [ "$N" -ne 0 ]; then grep -A2 -i "function signature mismatch" "$LOG" | head -40; exit 1; fi
