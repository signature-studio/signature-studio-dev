#!/usr/bin/env bash
# M2-5: 300KB級副モジュール (EasyFLAC_x64.dylib の x86_64 slice, 299KB) の
#       RetDec lift IR → emcc wasm 化 → node 実行 + bit-exact 照合の最小 PoC。
#
#   bash tools/m2/poc_crc8_wasm.sh
#
# 対象関数: _FLAC__crc8 (EasyFLAC export, 150B)  — 純計算・外部依存ゼロ・
#           crc8 テーブルがモジュール内定数 (アドレス参照 199232 = 0x30a40)。
#
# 依存: /opt/retdec (v5.0), /opt/emsdk (emcc 6.0.x), llvm-objdump (PATH), capstone は不使用。
# 成果物: tools/m2/work/ 配下 (gitignored)。
# 成功: "POC-CRC8: bit-exact OK" 出力と exit 0。

set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WORK="$HERE/work"
source "$HERE/../shared/env.sh"
EASYFLAC_FAT="$FL_MAC_DIR/pkg_extract/payload_out/Library/Audio/Plug-Ins/Components/FL Studio.component/Contents/Resources/FL Studio VSTi.vst/Contents/Resources/Shared/EasyFLAC_x64.dylib"
RETC="${RETDEC_DECOMPILER:-/opt/retdec/bin/retdec-decompiler}"

log() { echo "[poc_crc8] $*"; }
die() { echo "[poc_crc8] FAIL: $*" >&2; exit 1; }

command -v node >/dev/null  || die "node が見つかりません"
[ -x "$RETC" ]              || die "retdec-decompiler が見つかりません ($RETC)"
command -v emcc >/dev/null  || { source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; }
command -v emcc >/dev/null  || die "emcc が見つかりません"

mkdir -p "$WORK"
cd "$WORK"

# 1) slice 抽出 (universal2 → x86_64 299KB = 「300KB級」)
log "1/5 EasyFLAC slice 抽出"
python3 "$HERE/extract_slice.py" --input "$EASYFLAC_FAT" \
  --output-dir "$WORK" --arch x86_64 --output-name easyflac_x86_64.dylib

# 2) RetDec selective lift (関数内 IR のみを decode)
log "2/5 RetDec selective lift (_FLAC__crc8)"
"$RETC" easyflac_x86_64.dylib -o poc_crc8.drc.c \
  --select-functions "_FLAC__crc8" \
  --select-decode-only --timeout 600 > poc_crc8.retdec.log 2>&1 \
  || die "RetDec selective lift に失敗 (work/poc_crc8.retdec.log)"
[ -f poc_crc8.drc.ll ] || die "IR が生成されていません"

# 3) IR 正規化 (LLVM 12 → 現行 wasm バックエンド互換)
log "3/5 IR 正規化 (tools/m2/ir_normalize.py)"
python3 "$HERE/ir_normalize.py" poc_crc8.drc.ll poc_crc8_norm.ll

# 4) emcc → wasm (m1 flags.sh 準拠の定型値 + M2 追加)
log "4/5 emcc ビルド"
#  - GLOBAL_BASE=512MB   : emcc runtime 系データを 0x20000000 以降に置き、
#                          lifted IR のアドレス空間 (0x1d0000 未満) と非衝突にする
#  - --export=_FLAC__crc8: --no-entry 構成では EXPORTED_FUNCTIONS が tree-sweep
#                          されるため linker 直指定
emcc poc_crc8_norm.ll \
  -o poc_crc8_test.js \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -O0 \
  -sENVIRONMENT=node -sALLOW_MEMORY_GROWTH=1 \
  -sSTACK_SIZE=1mb -sGLOBAL_BASE=536870912 \
  -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -Wl,--no-gc-sections -Wl,--export=_FLAC__crc8 \
  --no-entry \
  || die "emcc に失敗"
mv poc_crc8_test.js poc_crc8_test.cjs
mv poc_crc8_test.wasm crc8_test.wasm

# 5) node ハーネスで bit-exact 実行
log "5/5 node ハーネス実行"
cp "$HERE/poc_crc8_harness.mjs" "$WORK/" 2>/dev/null || true
node "$WORK/poc_crc8_harness.mjs"

log "POC-CRC8: bit-exact OK (RetDec lift IR → emcc → wasm → node)"
