#!/usr/bin/env bash
# SR-5 (#73): 参照 WAV を wine64 上の実 Serum 2 DLL から生成する (native 機械語の DSP 出力)。
# usage: bash ref_render.sh <outdir> [pitch] [preset.SerumPreset]
#   <outdir> 出力先 (絶対パス推奨)。render_f32.wav / summary.json / log.txt を書く。
#   pitch    MIDI ノート (既定 60)。ネガコン用に別ノートを指定する。
#   preset   (任意) factory preset の .SerumPreset。SR-46 (#2384) で追加。省略時は既定 Init state。
# 固定条件: DLL = 実 Serum2_win64.vst3 (無改変・unpatched), state = plugin 既定 (Init) または preset, 48 kHz / 128 frames / 64 blocks,
#           MIDI = NoteOn (block 0) / NoteOff (block 24)。WAV 本体は work/ (gitignore) に置き、commit しない。
# content dir (DLL の CWD。Serum 2 が Tables/Presets を探す先): 既定は installer 全展開 (SERUM_DIR/work/content_full。
#           作成は host/ref_content.sh)。SR-47 (#2414) で既定を空 dir から切り替えた (REPORT_SR5 §4)。
#           env S2REF_CONTENT=<dir> で別条件 (例: 専用の空 dir) を指定できる。出力は content dir の中身で変わる。
#           条件は stdout の content= / tables= に出す。
# preset の state: .SerumPreset の DOM を既定 Init の processor DOM に重ねた XferJson を processor_state.json に渡す (preset_state.py overlay)。
#           preset ファイルをそのまま渡すと setState が kResultFalse で復元されない (S2REF_PRESET_MODE=exact で再現する負例)。
#           controller_state.json は既定 Init の controller state (work/init_ctrl/ の seed) を使う。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:?usage: ref_render.sh <outdir> [pitch] [preset]}"
PITCH="${2:-60}"
PRESET="${3:-}"
SERUM_DIR="$(cd "$HERE/.." && pwd)"
W="$HERE/work"
mkdir -p "$W" "$OUT"
export WINEPREFIX="$(cd "$W" && pwd)/wineprefix" WINEDEBUG=-all
command -v wine64 >/dev/null 2>&1 || export PATH="/usr/lib/wine:$PATH"
[ -f "$W/build/vst3host.exe" ] || bash "$HERE/build.sh"
[ -f "$SERUM_DIR/work/Serum2_win64.vst3" ] || { echo "FAIL: $SERUM_DIR/work/Serum2_win64.vst3 が無い (素材 plugins-serum2 を展開すること)" >&2; exit 1; }
CONTENT="${S2REF_CONTENT:-$SERUM_DIR/work/content_full}"
[ -d "$CONTENT" ] || { echo "FAIL: content dir $CONTENT が無い (既定は installer 全展開。bash host/ref_content.sh で作る)" >&2; exit 1; }
CONTENT="$(cd "$CONTENT" && pwd)"
TABLES=no; [ -d "$CONTENT/Tables" ] && TABLES=yes
echo "content=$CONTENT tables=$TABLES"
ZS2='Z:'"${SERUM_DIR//\//\\}"
OUTW="Z:${OUT//\//\\}"
STATE_ARG="-"
if [ -n "$PRESET" ]; then
  [ -f "$PRESET" ] || { echo "FAIL: preset が無い: $PRESET" >&2; exit 1; }
  if [ ! -f "$W/init_ctrl/saved_controller_state.bin" ]; then
    bash "$HERE/ref_render.sh" "$W/init_ctrl" 60 > "$W/init_ctrl.log" 2>&1
  fi
  STATE="$(cd "$OUT" && pwd)/state"
  mkdir -p "$STATE"
  python3 "$HERE/preset_state.py" "$PRESET" "$W/init_ctrl/saved_processor_state.bin" "$STATE/processor_state.json" "${S2REF_PRESET_MODE:-overlay}"
  cp "$W/init_ctrl/saved_controller_state.bin" "$STATE/controller_state.json"
  STATE_ARG="Z:${STATE//\//\\}"
  echo "preset=$(basename "$PRESET")"
fi
RC=0
S2HOST_PITCH="$PITCH" timeout 300 wine64 "$W/build/vst3host.exe" "$ZS2\\work\\Serum2_win64.vst3" "$STATE_ARG" "$OUTW" 64 "Z:${CONTENT//\//\\}" > "$OUT/console.txt" 2>&1 || RC=$?
echo "wine exit=$RC out=$OUT pitch=$PITCH"
[ -f "$OUT/render_f32.wav" ] || { echo "FAIL: render_f32.wav が出ていない" >&2; exit 1; }
exit "$RC"
