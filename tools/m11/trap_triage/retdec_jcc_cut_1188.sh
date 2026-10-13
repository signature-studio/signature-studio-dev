#!/usr/bin/env bash
# #1188: RetDec が先頭 cmp/jg を落とす段の切り分け (8c5eb0 と同型の最小再現)
# 使い方: RETDEC=<retdec-decompiler> bash tools/m11/trap_triage/retdec_jcc_cut_1188.sh
# 前提: retdec-decompiler と as/gcc。出力は tools/m11/work/trap1188/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
RETDEC_BIN="${RETDEC:-$(command -v retdec-decompiler || true)}"
[ -n "$RETDEC_BIN" ] || RETDEC_BIN="${RETDEC_ROOT:-/opt/retdec}/bin/retdec-decompiler"
[ -x "$RETDEC_BIN" ] || { echo "FAIL: retdec-decompiler 無し" >&2; exit 1; }
OUT="$HERE/../work/trap1188"
mkdir -p "$OUT"
cd "$OUT"
for v in vA vB vC g2; do
  as --64 -o "$v.o" "$HERE/1188_min/$v.s"
  gcc -nostdlib -static -no-pie -Wl,-e,_start -o "$v.elf" "$v.o"
  timeout 300 "$RETDEC_BIN" "$v.elf" -o "$v.c" --print-before-all > "$v.log" 2>&1
  # エントリブロックの終端が条件分岐 (br i1) なら先頭ガード残存、無条件 br なら脱落
  entry="$(grep -o 'dec_label_pc_[0-9a-f]*:' "$v.ll" | head -1)"
  term="$(awk -v E="$entry" 'index($0,E)==1{f=1} f&&/^ *br /{print; exit}' "$v.ll")"
  case "$term" in
    *"br i1"*) echo "$v: entry guard kept" ;;
    *) echo "$v: entry guard DROPPED (${term:-no br})" ;;
  esac
done
