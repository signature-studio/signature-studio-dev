#!/usr/bin/env bash
# M3 E2E 検証エントリ (1 コマンドで全 reproduce 可能):
#
#   bash tools/m3/m3.sh
#
# 1. ir_patch.py により EasyFLAC slice (tools/m2/work/easyflac.drc.ll 由来の
#    準備済正規形 ef_norm0.ll) から純計算 4 関数の call-graph 閉包を選別:
#      _FLAC__crc8, _FLAC__crc16, _FLAC__bitmath_silog2,
#      _FLAC__bitmath_extra_mulbits_unsigned
# 2. 定型フラグ (flags.sh) で emcc → wasm (MODULARIZE glue .cjs)
# 3. node work/t1_h.mjs   : M3 セッション実測の crc8 検証再現 (6 ケース照合)
# 4. node work/m3_e2e.mjs : 4 関数 bit-exact 照合 (仕様参照実装, 独立根拠付き)
#    + wasm 性能測定
# 5. native vs wasm 性能比: work/m3_perf_native.c (同一 lifted IR の x86_64
#    native 再コンパイル, -O2, mmap MAP_FIXED で VA 通りにテーブル/バッファ敷設)
#    を同型 LCG ループで測定し比を算出
#
# check 失敗時は非 0 で終了する (fail-fast)。
set -euo pipefail
cd "$(dirname "$0")"
source ./flags.sh

# バージョン pin 照合 (M1 検証条件 1 の継承)
EMCC_V="$(emcc --version 2>/dev/null | awk 'NR==1{print $1,$2}')" || true
echo "[m3] emcc: $EMCC_V (pin: $EMCC_VERSION_PIN)"

# ---- 1. IR 選別 (call-graph 閉包 4 関数, 外部参照 0) ------------------------
SRC_LL=work/ef_norm0.ll            # tools/m2/work/easyflac.drc.ll の正規形 (M3 セッション実測)
command -v python3 >/dev/null
python3 ir_patch.py "$SRC_LL" work/m3_sel4.ll \
  --select _FLAC__crc8,_FLAC__crc16,_FLAC__bitmath_silog2,_FLAC__bitmath_extra_mulbits_unsigned \
  --report work/m3_sel4_report.json

# ---- 2. wasm 再コンパイル (定型フラグ) --------------------------------------
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
EMCC_FLAGS=(-w -Wno-error=implicit-function-declaration
  -msimd128
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=536870912
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 --no-entry
  -Wl,--no-gc-sections)

EXPS=(-Wl,--export=_FLAC__crc8 -Wl,--export=_FLAC__crc16
  -Wl,--export=_FLAC__bitmath_silog2
  -Wl,--export=_FLAC__bitmath_extra_mulbits_unsigned)

emcc "${EMCC_FLAGS[@]}" "${EXPS[@]}" work/m3_sel4.ll -o work/m3_sel4.js
mv work/m3_sel4.js work/m3_sel4.cjs

# M3 セッション実測分 (crc8 単独 IR, t1_h.mjs が t1.cjs/t1.wasm/t1.ll を読む)
emcc "${EMCC_FLAGS[@]}" -O1 -Wl,--export=_FLAC__crc8 work/t1.ll -o work/t1.js
mv work/t1.js work/t1.cjs

# ---- 3-4. bit-exact 照合 -----------------------------------------------------
(cd work && node t1_h.mjs)
(cd work && node m3_e2e.mjs)

# ---- 5. native vs wasm 性能比 (同一 lifted IR のネイティブ再コンパイル) -------
# IR から datalayout 行を除いて x86_64 host clang -O2 で object 化し,
# mmap(MAP_FIXED) でテーブル/バッファ領域を VA 通りに敷いて呼ぶ (m3_perf_native.c)。
grep -v '^target datalayout' work/m3_sel4.ll > work/m3_sel4_native.ll
/opt/emsdk/upstream/bin/clang -O2 -x ir work/m3_sel4_native.ll -o work/m3_sel4_native.o -c 2>/dev/null
cc -O2 -o work/m3_perf_native work/m3_perf_native.c work/m3_sel4_native.o
(cd work && ./m3_perf_native "$(pwd)/easyflac_x86_64.dylib" > m3_perf_native.out 2>&1 || true)
echo "[m3] native (lifted IR, -O2, VA=直map):"
(cd work && cat m3_perf_native.out)
echo "[m3] wasm/node 側は work/m3_e2e_results.json の perf (m3_e2e.mjs) を対照"
