#!/usr/bin/env bash
# #1188: RetDec が先頭 cmp/jg を落とす段の切り分け (8c5eb0 と同型の最小再現)
# 使い方: bash tools/m11/trap_triage/retdec_jcc_cut_1188.sh
# 前提: RETDEC (retdec-decompiler) と gcc (as/ld 同梱)。出力は tools/m11/work/trap1188/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
RETDEC_BIN="${RETDEC:-$(command -v retdec-decompiler || true)}"
[ -n "$RETDEC_BIN" ] || RETDEC_BIN="${RETDEC_ROOT:-/opt/retdec}/bin/retdec-decompiler"
[ -x "$RETDEC_BIN" ] || { echo "FAIL: retdec-decompiler 無し" >&2; exit 1; }
OUT="$HERE/../work/trap1188"
mkdir -p "$OUT"
cd "$OUT"
for v in vA vB vC; do
  as --64 -o "$v.o" "$HERE/1188_min/$v.s"
  gcc -nostdlib -static -no-pie -Wl,-e,_start -o "$v.elf" "$v.o"
  timeout 300 "$RETDEC_BIN" "$v.elf" -o "$v.c" --print-before-all > "$v.log" 2>&1
  # 最終 IR の条件分岐数 (0 なら分岐が落ちた)
  echo "$v: final_br=$(grep -c 'br ' "$v.ll")"
done
