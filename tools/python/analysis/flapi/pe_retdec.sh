#!/usr/bin/env bash
# FLEngine PE (block00031_PE.bin) の VA 範囲を RetDec v5.0 で逆コンパイルする (PY-39 の解析補助。pe_disasm.py の上位)。
#   FL_WIN64_DIR=<展開先> bash analysis/flapi/pe_retdec.sh <出力 .c> <VA範囲[,範囲...]>
#   例: FL_WIN64_DIR=work/fl bash analysis/flapi/pe_retdec.sh work/fl/rd.c 0xd5b100-0xd5b150,0x11e8670-0x11e8715
# 範囲は絶対 VA (ImageBase 0x400000 込み) をカンマ区切りで指定する。ログは <出力 .c>.log。
# 展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
# retdec-decompiler は PATH 上、または RETDEC_BIN で指定 ([RETDEC] = docs/REFERENCES.md §4)。
set -euo pipefail
: "${FL_WIN64_DIR:?FL_WIN64_DIR を指定 (fl-win64 の展開先)}"
RETDEC="${RETDEC_BIN:-retdec-decompiler}"
OUT="$1"; RANGES="$2"
"$RETDEC" "$FL_WIN64_DIR/extracted/block00031_PE.bin" -o "$OUT" --select-ranges "$RANGES" --select-decode-only --timeout 300 > "$OUT.log" 2>&1
grep -E '^// Address range|^// Detected functions' "$OUT"
