#!/usr/bin/env bash
# SR-5 (#73): 参照 WAV を wine64 上の実 Serum 2 DLL から生成する (native 機械語の DSP 出力)。
# usage: bash ref_render.sh <outdir> [pitch]
#   <outdir> 出力先 (絶対パス推奨)。render_f32.wav / summary.json / log.txt を書く。
#   pitch    MIDI ノート (既定 60)。ネガコン用に別ノートを指定する。
# 固定条件: DLL = 実 Serum2_win64.vst3 (無改変・unpatched), state = plugin 既定 (Init), 48 kHz / 128 frames / 64 blocks,
#           MIDI = NoteOn (block 0) / NoteOff (block 24)。WAV 本体は work/ (gitignore) に置き、commit しない。
# content dir (DLL の CWD。Serum 2 が Tables/Presets を探す先): 既定は専用の空 dir (SERUM_DIR/work/ref_content)。
#           env S2REF_CONTENT=<dir> で installer 全展開 dir (Tables あり) など別条件を指定できる。
#           出力は content dir の中身で変わる (REPORT_SR5 §1)。条件は stdout の content= / tables= に出す。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:?usage: ref_render.sh <outdir> [pitch]}"
PITCH="${2:-60}"
SERUM_DIR="$(cd "$HERE/.." && pwd)"
W="$HERE/work"
mkdir -p "$W" "$OUT"
export WINEPREFIX="$(cd "$W" && pwd)/wineprefix" WINEDEBUG=-all
command -v wine64 >/dev/null 2>&1 || export PATH="/usr/lib/wine:$PATH"
[ -f "$W/build/vst3host.exe" ] || bash "$HERE/build.sh"
[ -f "$SERUM_DIR/work/Serum2_win64.vst3" ] || { echo "FAIL: $SERUM_DIR/work/Serum2_win64.vst3 が無い (素材 plugins-serum2 を展開すること)" >&2; exit 1; }
CONTENT="${S2REF_CONTENT:-$SERUM_DIR/work/ref_content}"
[ -n "${S2REF_CONTENT:-}" ] || mkdir -p "$CONTENT"
[ -d "$CONTENT" ] || { echo "FAIL: S2REF_CONTENT=$CONTENT が dir でない" >&2; exit 1; }
CONTENT="$(cd "$CONTENT" && pwd)"
TABLES=no; [ -d "$CONTENT/Tables" ] && TABLES=yes
echo "content=$CONTENT tables=$TABLES"
ZS2='Z:'"${SERUM_DIR//\//\\}"
OUTW="Z:${OUT//\//\\}"
RC=0
S2HOST_PITCH="$PITCH" timeout 300 wine64 "$W/build/vst3host.exe" "$ZS2\\work\\Serum2_win64.vst3" - "$OUTW" 64 "Z:${CONTENT//\//\\}" > "$OUT/console.txt" 2>&1 || RC=$?
echo "wine exit=$RC out=$OUT pitch=$PITCH"
[ -f "$OUT/render_f32.wav" ] || { echo "FAIL: render_f32.wav が出ていない" >&2; exit 1; }
exit "$RC"
