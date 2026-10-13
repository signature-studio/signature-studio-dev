#!/usr/bin/env bash
# tools/ipp/shim/fft 1 コマンド e2e (CAB-139): pffft 差替え FFT の全検証。
#   1. 署名突合 (本実装 28 関数宣言 vs gen/ipp_proto.h)
#   2. ネイティブ・オラクル: 実 IPP DLL vs 本実装, 28 関数 × order 0..16 × flag × buffer あり/なし + エラー格子
#   3. wasm (scalar/simd128) ビルド + 実 IPP golden 48 ケース (shim_e2e と同一ハーネス)
#   4. wasm 規模拡張テスト (order 0..16 全 flag, 全 Run 系, thunk 経由)
#   5. simd128 の成立確認 (v128 命令の実在)
#   6. 性能: 差替え前後を同一条件で実測 (scalar/simd128)
# usage: bash tools/ipp/shim/fft/fft_e2e.sh
set -euo pipefail
cd "$(dirname "$0")"; FFT=$PWD; SHIM="$(dirname "$FFT")"; IPP="$(dirname "$SHIM")"; W="$IPP/work/shim"; mkdir -p "$W" /tmp/opencode
source "$IPP/../shared/env.sh"
DLL="$FL_WIN64_DIR/extracted/block24356_PE.bin"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
step() { echo; echo "## $*"; }
CF="-std=gnu11 -O2 -ffp-contract=off -fno-fast-math -Wall -Wno-unused-function -Wno-maybe-uninitialized -Wno-misleading-indentation"
SRCS="ipp_fft_pffft.c pffft/pffft.c pffft/pffft_double.c pffft/pffft_common.c"

step "1. 署名突合 (ipp_fft_pffft.h vs gen/ipp_proto.h)"
gcc -std=gnu11 -fsyntax-only -w test/fft_proto_check.c && echo "  proto check: OK (28 関数の宣言が生成プロトタイプと一致)"

step "2. native オラクル (実 IPP DLL vs 本実装, pffft assert 有効)"
gcc $CF -o "$W/fft_oracle" test/fft_oracle.c $SRCS "$IPP"/ref/pe_load.c -lm 2>&1 | grep -v "pragma message\|note:" | head -3 || true
"$W/fft_oracle" "$DLL" 2>&1 | tail -1 | tee "$W/fft_oracle.json" | sed 's/^/  /'
python3 - "$W/fft_oracle.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert r['fails'] == 0 and r['status_mismatch'] == 0, r
print(f"  oracle: {r['fft_oracle_cases']} cases, status 不一致 0, NRMS 単一 32f {r['worst_single_32f']:.2e} / 64f {r['worst_single_64f']:.2e}, 意図的差分 {r['known_deviation_64f_bufnull']} (64f bufNULL)")
PY

step "3. wasm ビルド (shim 全体, scalar + simd128) と 実 IPP golden 48 ケース"
bash ../build_wasm.sh 2>&1 | tail -1 | sed 's/^/  scalar: /'
EXTRA="-msimd128" OUT="$W/ipp_shim_simd.wasm" bash ../build_wasm.sh 2>&1 | tail -1 | sed 's/^/  simd128: /'
node ../test/ipp_shim_wasm.mjs "$W/ipp_shim.wasm" "$IPP/work/golden" ../data/ipp_sigs.json "$W/wasm_thunk.json" 2>&1 | tail -2 | sed 's/^/  scalar: /'
node ../test/ipp_shim_wasm.mjs "$W/ipp_shim_simd.wasm" "$IPP/work/golden" ../data/ipp_sigs.json "$W/wasm_thunk_simd.json" 2>&1 | tail -2 | sed 's/^/  simd128: /'

step "4. wasm 規模拡張テスト (order 0..16 × flag × 全 Run 系, thunk 経由)"
node test/fft_wasm_ext.mjs "$W/ipp_shim.wasm" ../data/ipp_sigs.json | sed 's/^/  scalar: /'
node test/fft_wasm_ext.mjs "$W/ipp_shim_simd.wasm" ../data/ipp_sigs.json | sed 's/^/  simd128: /'

step "5. simd128 の成立確認 (pffft TU の v128 命令)"
bash bench/build_bench.sh > /dev/null 2>&1
VS=$(wasm-objdump -d work/bench/fft_new_simd.wasm | grep -c "v128\." || true)
VSF=$(wasm-objdump -d work/bench/fft_new.wasm | grep -c "v128\." || true)
echo "  pffft float+double simd128: v128 命令 $VS (scalar build: $VSF)"
[ "$VS" -gt 100 ] && [ "$VSF" -eq 0 ] && echo "  simd 有効 / scalar 無効: OK"

step "6. 性能: 差替え前後を同一条件で実測 (同一 node・入力・iteration・emcc フラグ)"
EXTRA=-msimd128 bash bench/build_bench.sh > /dev/null 2>&1
node bench/bench_fft.mjs work/bench/fft_old.wasm work/bench/fft_new.wasm work/bench/scalar.json | sed 's/^/  scalar  /'
node bench/bench_fft.mjs work/bench/fft_old_simd.wasm work/bench/fft_new_simd.wasm work/bench/simd.json | sed 's/^/  simd128 /'

echo
echo "== fft e2e: 全 step 完了 (exit 0) =="
