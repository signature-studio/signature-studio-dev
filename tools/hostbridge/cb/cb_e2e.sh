#!/usr/bin/env bash
# cb_e2e.sh — hostbridge/cb 1 コマンド検証 (CAB-177): shimx R2 コールバック変換の実体接続を
# 「shimx 全ソース + 模擬 lift closure (VA 関数表+invoke)」の実リンク構成で往復検証する。
#   bash tools/hostbridge/cb/cb_e2e.sh          # MT + ST ビルド → ハーネス実行 → 判定
# exit 0 = 全 PASS。成果物は work/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SX="$(cd -- "$HERE/../../shimx" && pwd)"
W="$HERE/work"
mkdir -p "$W"
step() { echo "[cb_e2e] $*"; }

set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
command -v emcc >/dev/null || { echo "[cb_e2e] emcc が見つかりません"; exit 2; }

CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing -O1"

build_run() {  # $1 = mt|st
    local mode="$1" flags=()
    if [ "$mode" = mt ]; then flags=(-pthread -sPTHREAD_POOL_SIZE=8); else flags=(); fi
    step "build $mode"
    emcc $CF "${flags[@]}" -I"$SX/src" \
        -sALLOW_MEMORY_GROWTH=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 -sEXIT_RUNTIME=1 -sENVIRONMENT=node \
        -sGLOBAL_BASE=1048576 -sSTACK_SIZE=4MB -sMODULARIZE=1 -sEXPORT_NAME=cbcreate --no-entry \
        -sEXPORTED_RUNTIME_METHODS=HEAPU32 \
        "$SX"/src/*.c "$HERE"/cb_mod.c -o "$W/cb_$mode.cjs" || { echo "[cb_e2e] build $mode FAILED"; exit 1; }
    step "run $mode"
    node "$HERE/cb_harness.mjs" "$W/cb_$mode.cjs" --out "$W" > "$W/cb_$mode.out" 2> "$W/cb_$mode.err" \
        || { tail -8 "$W/cb_$mode.err" >&2; echo "[cb_e2e] run $mode FAILED (work/cb_$mode.err)"; exit 1; }
    grep -c '\[cb\] OK' "$W/cb_$mode.out" | sed 's/^/    checks OK: /'
}

build_run mt
build_run st
step "PASS (cb_result.json: $(python3 -c "import json;r=json.load(open('$W/cb_result.json'));print(r['checks'],'checks /',r['failed'],'failed',r['stats'])"))"
exit 0
