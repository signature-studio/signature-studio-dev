#!/usr/bin/env bash
# text_golden.sh — GUI-9 (#186): FreeType テキストエンジンを独立オラクル (native FreeType 直叩き) と画素/metrics 完全一致で検査。
# ネガティブコントロール 4 本 (期待値を壊す / フォント高さ欠陥 / engine 未登録 (8x8) / オラクルのフォント差し替え) は **FAIL(exit 1) しなければ** このスクリプトが exit 1。
# 前提: bash tools/shared/oss/freetype/build.sh 済み (native libfreetype.a) とフォント (tools/gui/work/*.ttf; scripts/fetch_fonts.sh)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/.."; B="$ROOT/build"; mkdir -p "$B"
FTW="$ROOT/../shared/work"; FTSRC="$FTW/src/freetype-2.7"; FTLIB="$FTW/build/freetype/native/src/objs/.libs/libfreetype.a"
FONTDIR="${FONTDIR:-$ROOT/work}"
[ -f "$FTLIB" ] || { echo "native libfreetype.a missing: run tools/shared/oss/freetype/build.sh" >&2; exit 2; }
[ -f "$FONTDIR/OpenSans-Regular.ttf" ] && [ -f "$FONTDIR/Barlow-Regular.ttf" ] || { echo "fonts missing in $FONTDIR: run tools/gui/test/fetch_fonts.sh" >&2; exit 2; }
python3 "$ROOT/gen_api.py" >/dev/null
gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$ROOT/include" -I "$ROOT/src" -I "$B" -I "$FTSRC/include" \
  "$ROOT"/src/gui_platform.c "$ROOT"/src/gui_reach.c "$B"/gui_reach_tab.c "$ROOT"/src/gui_core.c "$ROOT"/src/gui_gdi.c "$ROOT"/src/gui_ft.c "$ROOT"/src/gui_headless.c "$B"/gui_stubs.c \
  "$HERE/text_golden.c" "$FTLIB" -o "$B/text_golden" -lm
gcc -O1 -w -I "$FTSRC/include" "$ROOT/golden/ft_oracle.c" "$FTLIB" -o "$B/ft_oracle" -lm
"$B/ft_oracle" "$FONTDIR" "$B/text_oracle.ppm" "$B/text_oracle.tsv"
"$B/text_golden" "$FONTDIR" "$B/text_actual.ppm" "$B/text_actual.tsv" | tee "$B/text_enum.out"
grep -q "enum all=2 named=1 first=Barlow" "$B/text_enum.out" || { echo "FAIL: EnumFontFamiliesExW result"; exit 1; }
python3 "$ROOT/golden/cmp_text.py" "$B/text_actual.ppm" "$B/text_actual.tsv" "$B/text_oracle.ppm" "$B/text_oracle.tsv"
fail=0
if python3 "$ROOT/golden/cmp_text.py" "$B/text_actual.ppm" "$B/text_actual.tsv" "$B/text_oracle.ppm" "$B/text_oracle.tsv" --tamper >/dev/null 2>&1; then echo "NEGCTL FAIL: tampered oracle was accepted"; fail=1; else echo "negctl 1/4 OK: tampered oracle (1 px + 1 metrics cell) rejected"; fi
TEXT_FAULT=1 "$B/text_golden" "$FONTDIR" "$B/text_fault.ppm" "$B/text_fault.tsv" >/dev/null
if python3 "$ROOT/golden/cmp_text.py" "$B/text_fault.ppm" "$B/text_fault.tsv" "$B/text_oracle.ppm" "$B/text_oracle.tsv" >"$B/text_fault.out" 2>&1; then echo "NEGCTL FAIL: shim with 1px font-height fault was accepted"; fail=1; else echo "negctl 2/4 OK: font-height fault rejected ($(head -1 "$B/text_fault.out" | cut -c1-70))"; fi
TEXT_NOENGINE=1 "$B/text_golden" "$FONTDIR" "$B/text_noeng.ppm" "$B/text_noeng.tsv" >/dev/null
if python3 "$ROOT/golden/cmp_text.py" "$B/text_noeng.ppm" "$B/text_noeng.tsv" "$B/text_oracle.ppm" "$B/text_oracle.tsv" >/dev/null 2>&1; then echo "NEGCTL FAIL: 8x8 fallback was accepted as FreeType output"; fail=1; else echo "negctl 3/4 OK: 8x8 fallback (no engine) rejected"; fi
mkdir -p "$B/fonts_swap"; cp "$FONTDIR/OpenSans-Regular.ttf" "$B/fonts_swap/OpenSans-Regular.ttf"; cp "$FONTDIR/OpenSans-Regular.ttf" "$B/fonts_swap/Barlow-Regular.ttf"
"$B/ft_oracle" "$B/fonts_swap" "$B/text_swap.ppm" "$B/text_swap.tsv"
if python3 "$ROOT/golden/cmp_text.py" "$B/text_actual.ppm" "$B/text_actual.tsv" "$B/text_swap.ppm" "$B/text_swap.tsv" >/dev/null 2>&1; then echo "NEGCTL FAIL: oracle with wrong font file was accepted"; fail=1; else echo "negctl 4/4 OK: oracle built from a different font file rejected"; fi
[ "$fail" = 0 ] && echo "[text-golden] ALL PASS" || { echo "[text-golden] FAILED"; exit 1; }
