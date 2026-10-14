#!/usr/bin/env bash
# #1967 (LD-71): 既存 RetDec v5.0 バイナリへの uprobe 再現スクリプト。
# 付録 REPORT_911_APPENDIX_1967.md §6f の siteA/B/C 件数・範囲を再現する。
#
# 入力 (環境変数):
#   RETDEC_BIN   : retdec-decompiler (v5.0) の絶対パス。[RETDEC] (docs/REFERENCES.md §4)
#   PE_BIN       : block00031_PE.bin ($FL_WIN64_DIR/extracted/ 配下)。fl-win64 素材
#   FUNC_BASE    : convertConstantToType の呼び出し元関数の VA (16 進)。
#                  付録には記録していない。nm / 逆アセンブルで同定して渡す (未確定)。
#   OUT          : 出力先。既定 $RUNNER_TEMP/uprobe_1967 (gitignore 外の大物は置かない)
#
# 使い方:
#   RETDEC_BIN=... PE_BIN=... FUNC_BASE=0x... bash tools/m11/ldfix/uprobe_1967.sh
#
# 状態: 本スクリプトは #1967 の run では未実行 (toolchain-retdec 素材が取得されず RETDEC_BIN が無い)。
# 未検証: perf probe の -a 指定 (アドレス指定の構文) は実機で未確認 (当該 run は tracefs 権限無し)。
# 初回実行時に構文と件数を確かめ、結果を REPORT_911_APPENDIX_1967.md に反映すること。
set -euo pipefail

: "${RETDEC_BIN:?RETDEC_BIN (retdec-decompiler v5.0) を指定}"
: "${PE_BIN:?PE_BIN (block00031_PE.bin) を指定}"
: "${FUNC_BASE:?FUNC_BASE (呼び出し元関数の VA) を指定}"
OUT="${OUT:-${RUNNER_TEMP:-/tmp}/uprobe_1967}"
mkdir -p "$OUT"

# 付録 §6f の呼び出し点オフセット (FUNC_BASE からの相対)
SITE_A=$(printf '0x%x' $((FUNC_BASE + 768)))
SITE_B=$(printf '0x%x' $((FUNC_BASE + 1426)))
SITE_C=$(printf '0x%x' $((FUNC_BASE + 1475)))

# 1. uprobe の登録 (DWARF 無しのためアドレス指定)
perf probe -d 'probe_retdec:*' 2>/dev/null || true
perf probe -x "$RETDEC_BIN" -a "siteA=$SITE_A" -a "siteB=$SITE_B" -a "siteC=$SITE_C"

# 2. 範囲ごとに記録して件数を数える (付録の表の列)
# 範囲は付録の行に対応: 41a670-41a6f4 / 41a6a0-41a6a3 / 41a6d3-41a6d6 / 41a6b3-41a6b7 / 666b10-666b13 / 666b20-666b23
# 注: 範囲の VA は RetDec バイナリ上の値。FUNC_BASE とは別の空間のため、付録の表の値をそのまま使う。
count_hits() {
  local label="$1"
  perf record -e "probe_retdec:*" -o "$OUT/$label.data" -- "$RETDEC_BIN" -s -o "$OUT/$label.c" \
    --select-ranges "$2" --select-decode-only "$PE_BIN" > "$OUT/$label.log" 2>&1 || true
  perf script -i "$OUT/$label.data" 2>/dev/null | awk '/siteA/{a++} /siteB/{b++} /siteC/{c++} END{printf "%s siteA=%d siteB=%d siteC=%d\n", "'"$label"'", a+0, b+0, c+0}'
}

count_hits full_41a670   0x41a670-0x41a6f4
count_hits 41a6a0        0x41a6a0-0x41a6a3
count_hits 41a6d3        0x41a6d3-0x41a6d6
count_hits ctl_41a6b3    0x41a6b3-0x41a6b7
count_hits 666b10        0x666b10-0x666b13
count_hits 666b20        0x666b20-0x666b23

# 3. 後始末 (自分が登録した probe のみ削除)
perf probe -d 'probe_retdec:*' 2>/dev/null || true
