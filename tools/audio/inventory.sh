#!/usr/bin/env bash
# FL(win/mac) のオーディオ/MIDI import・API 呼出面を実測して results/inventory_raw.txt に出力する (INVENTORY.md の根拠)。
# 使い方: bash tools/audio/inventory.sh   (analysis/ の抽出物を参照; 読取専用)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
OUT="$HERE/results/inventory_raw.txt"
mkdir -p "$HERE/results"
. "$HERE/../shared/env.sh"
WIN="$FL_WIN64_DIR/extracted"
MAC=/home/ubuntu/work/webstudio/tools/m2/work/FLEngine_x86_64.dylib   # M2 が lipo 抽出した x86_64 スライス (読取のみ)
{
  echo "### [1] FLEngine_x64.dll: audio/MIDI import 参照元 (fl_audio_xref.py, thunk 経由 e8 解決)"
  python3 "$HERE/fl_audio_xref.py" --json "$HERE/results/xref.json" > /dev/null
  python3 - <<PY
import json
d=json.load(open("$HERE/results/xref.json"))
for k,v in d["iat_callers"].items():
    if k.startswith(("dsound","winmm.dll!midi")): print(f"  {k:36s} callers={[x['fn'] for x in v]}")
print("  winmm.dll!timeGetTime distinct caller functions =", len(d["iat_callers"]["winmm.dll!timeGetTime"]))
for a,rows in d["anchors"].items():
    print(f"  anchor {a!r}: {[(r['fn'],r['size']) for r in rows]}")
PY
  echo; echo "### [2] FLEngine ASIO/DirectSound vtable 呼出面 (fl_asio_surface.py)"
  python3 "$HERE/fl_asio_surface.py"
  echo; echo "### [3] GUID 走査 (scan_guids.py)"
  python3 "$HERE/scan_guids.py" $WIN/block00031_PE.bin $WIN/block00001_PE.bin
  echo; echo "### [4] ILWASAPI2ASIO_x64.dll: ILWasapiToAsioDriver vtable / 報告値 (ilw_vtable.py, ilw_consts.py)"
  python3 "$HERE/ilw_vtable.py" $WIN/block00001_PE.bin | head -28
  python3 "$HERE/ilw_consts.py"
  echo; echo "### [5] macOS FLEngine x86_64 slice: CoreAudio/AudioToolbox/CoreMIDI undefined symbols (llvm-nm)"
  llvm-nm -m -u "$MAC" | grep -E "CoreAudio|AudioToolbox|AudioUnit|CoreMIDI" | sed 's/.*external //' | sort
} > "$OUT"
echo "[audio] inventory -> $OUT ($(wc -l < "$OUT") lines)"
