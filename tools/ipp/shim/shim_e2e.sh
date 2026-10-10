#!/usr/bin/env bash
# tools/ipp/shim 1 コマンド e2e: 署名採取 -> thunk/表生成 -> native(実 DLL オラクル)/wasm(golden) の thunk 経路回帰 -> 判定
# usage: bash tools/ipp/shim/shim_e2e.sh   (前提: tools/ipp/ipp_e2e.sh を一度実行済み = work/ に golden / 420 名 / win_refs がある。無ければ自動実行)
set -euo pipefail
cd "$(dirname "$0")"; HERE=$PWD; IPP=$(dirname "$HERE"); W=$IPP/work/shim; mkdir -p "$W" /tmp/opencode
DLL=/home/ubuntu/work/analysis/win64/extracted/block24356_PE.bin; ALL=0xFFFFFFFFFFFFFFFF
[ -f "$IPP/work/golden/manifest.json" ] && [ -f "$IPP/work/win_refs.json" ] && [ -f "$IPP/work/flengine_ipp_names.json" ] || { echo "## prerequisite: tools/ipp/ipp_e2e.sh"; bash "$IPP/ipp_e2e.sh" > "$W/ipp_e2e.log" 2>&1; }
step() { echo; echo "## $*"; }
step "1. 呼出箇所実績の採取 (win64 全 145 モジュール, 署名の独立検算用)"
python3 sigscan.py
step "2. 署名導出 + 検算 + thunk/表/プロトタイプ生成"
python3 gen_shim.py | head -1 | cut -c1-400
sha256sum gen/ipp_shim_tab.c gen/ipp_proto.h data/ipp_sigs.json > "$W/gen.sha"
python3 gen_shim.py > /dev/null; sha256sum -c "$W/gen.sha" > /dev/null && echo "  generator idempotent: OK"
step "3. native ビルド (署名検査 = ipp_min.h vs 生成プロトタイプのコンパイル) と自己検査"
bash build_native.sh | tail -1
EXP=$(python3 -c "import json; s=json.load(open('data/sigs_summary.json')); print(s['thunks_typed(impl)'], s['names']-s['thunks_typed(impl)'])")
"$W/bin/shim_selftest" "$W/names.txt" $EXP | tee "$W/selftest.log" | tail -2
step "4. 実 Intel IPP(DLL をネイティブ実行) vs thunk 経路 (実 MS x64 呼出 -> asm トランポリン -> dispatch -> thunk)"
"$W/bin/shim_ref" err $DLL > "$W/err_thunk.json"; tail -1 "$W/err_thunk.json"
"$W/bin/shim_ref" cmp $DLL $ALL > "$W/cmp_thunk.json" 2> "$W/cmp_thunk.err"; tail -1 "$W/cmp_thunk.err"
SPEC=1 "$W/bin/shim_ref" cmp $DLL $ALL > "$W/cmp_thunk_spec.json" 2> "$W/cmp_thunk_spec.err"; tail -1 "$W/cmp_thunk_spec.err"
step "5. wasm (scalar / simd128): golden(実 IPP 出力)を ABI レジスタブロック経由で突合"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
./build_wasm.sh | sed 's/^/  scalar: /'; EXTRA=-msimd128 OUT="$W/ipp_shim_simd.wasm" ./build_wasm.sh | sed 's/^/  simd128: /'
node test/ipp_shim_wasm.mjs "$W/ipp_shim.wasm" "$IPP/work/golden" data/ipp_sigs.json "$W/wasm_thunk.json" | tail -3 | sed 's/^/  scalar: /'
node test/ipp_shim_wasm.mjs "$W/ipp_shim_simd.wasm" "$IPP/work/golden" data/ipp_sigs.json "$W/wasm_thunk_simd.json" | tail -3 | sed 's/^/  simd128: /'
step "5b. shimx 結合 (tools/shimx 読取専用で wasm ビルド): LoadLibraryW -> GetProcAddress(420 名) -> dispatch"
mkdir -p "$W/shimx_obj"; SX=$IPP/../shimx/src
for f in "$SX"/*.c; do emcc -c -O1 -w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing "$f" -o "$W/shimx_obj/$(basename "$f" .c).o" & done; wait
emcc -O1 -w -I"$SX" -Isrc -I"$IPP/src" test/shimx_glue_test.c src/ipp_shim_shimx.c src/ipp_shim.c gen/ipp_shim_tab.c "$IPP/src/ipp_min.c" "$HERE"/fft/*.c "$HERE"/fft/pffft/*.c $(ls "$HERE"/impl/*.c 2>/dev/null || true) "$W"/shimx_obj/*.o -o "$W/shimx_glue_test.cjs" \
  -sALLOW_MEMORY_GROWTH=1 -sENVIRONMENT=node -sEXIT_RUNTIME=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 -sGLOBAL_BASE=1048576 --embed-file "$W/names.txt@/names.txt"
node "$W/shimx_glue_test.cjs" | tee "$W/shimx_glue.log" | sed 's/^/  /'
step "6. 判定"
python3 shim_check.py
