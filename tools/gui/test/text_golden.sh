#!/usr/bin/env bash
# text_golden.sh — GUI-9 (#186): FreeType テキストエンジンを独立オラクル (native FreeType 直叩き) と画素/metrics 完全一致で検査。
# ネガティブコントロール 4 本 (期待値を壊す / フォント高さ欠陥 / engine 未登録 (8x8) / オラクルのフォント差し替え) は cmp_text.py が **exit 1 (不一致) で拒否しなければ** (exit 0 も exit 2 も不合格) このスクリプトが exit 1。
# 前提: bash tools/shared/oss/freetype/build.sh 済み (native libfreetype.a) とフォント (tools/gui/work/*.ttf; test/fetch_fonts.sh)。
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
# ネガコンは cmp_text.py の「不一致 = exit 1」だけを検出扱いにする (exit 2 = 入力不正 / 例外での偶然の非 0 を検出と数えない)
NEG_RC=0
rejected() { NEG_RC=0; python3 "$ROOT/golden/cmp_text.py" "$@" >"$B/text_neg.out" 2>&1 || NEG_RC=$?; [ "$NEG_RC" = 1 ]; }
if rejected "$B/text_actual.ppm" "$B/text_actual.tsv" "$B/text_oracle.ppm" "$B/text_oracle.tsv" --tamper; then echo "negctl 1/4 OK: tampered oracle (1 px + 1 metrics cell) rejected (rc=1)"; else echo "NEGCTL FAIL: tampered oracle not rejected with rc=1 (rc=$NEG_RC)"; fail=1; fi
TEXT_FAULT=1 "$B/text_golden" "$FONTDIR" "$B/text_fault.ppm" "$B/text_fault.tsv" >/dev/null
if rejected "$B/text_fault.ppm" "$B/text_fault.tsv" "$B/text_oracle.ppm" "$B/text_oracle.tsv"; then echo "negctl 2/4 OK: font-height fault rejected (rc=1; $(head -1 "$B/text_neg.out" | cut -c1-70))"; else echo "NEGCTL FAIL: shim with 1px font-height fault not rejected with rc=1 (rc=$NEG_RC)"; fail=1; fi
TEXT_NOENGINE=1 "$B/text_golden" "$FONTDIR" "$B/text_noeng.ppm" "$B/text_noeng.tsv" >/dev/null
if rejected "$B/text_noeng.ppm" "$B/text_noeng.tsv" "$B/text_oracle.ppm" "$B/text_oracle.tsv"; then echo "negctl 3/4 OK: 8x8 fallback (no engine) rejected (rc=1)"; else echo "NEGCTL FAIL: 8x8 fallback not rejected with rc=1 (rc=$NEG_RC)"; fail=1; fi
mkdir -p "$B/fonts_swap"; cp "$FONTDIR/OpenSans-Regular.ttf" "$B/fonts_swap/OpenSans-Regular.ttf"; cp "$FONTDIR/OpenSans-Regular.ttf" "$B/fonts_swap/Barlow-Regular.ttf"
"$B/ft_oracle" "$B/fonts_swap" "$B/text_swap.ppm" "$B/text_swap.tsv"
if rejected "$B/text_actual.ppm" "$B/text_actual.tsv" "$B/text_swap.ppm" "$B/text_swap.tsv"; then echo "negctl 4/4 OK: oracle built from a different font file rejected (rc=1)"; else echo "NEGCTL FAIL: oracle with wrong font file not rejected with rc=1 (rc=$NEG_RC)"; fail=1; fi
[ "$fail" = 0 ] && echo "[text-golden] ALL PASS" || { echo "[text-golden] FAILED"; exit 1; }
