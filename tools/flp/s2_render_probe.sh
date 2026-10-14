#!/usr/bin/env bash
# #113 S2 probe: 実物の FL64.exe を wine64 で `/R` 起動し、Render tests の 1 本を WAV 書き出しする。
# 前提: `bash tools/flp/s1_wine_probe.sh` でインストール木 ($RUNNER_TEMP/fl-install) と wineprefix を作成済み。
# 手順: block から FL64.exe / FLEngine_x64.dll を復元 → G03 パッチ (s1_g03_patch.py, oracle ローカルコピーのみ)
#       → 出力 sample rate を 48000 に設定 → `/R` で書き出し → data チャンクの SHA-256 を REPEAT 回求める。
# 使い方: bash tools/flp/s2_render_probe.sh <Render tests の .flp 名> [REPEAT=3]
# 出力は $RUNNER_TEMP 配下のみ (commit 対象外)。結果の要約は tools/flp/REPORT_APPENDIX.md §15。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ART="${RUNNER_TEMP:-/tmp}"
EXT="$ART/fl-win64/extracted"
INST="$ART/fl-install"
SRC="$ART/fl-install/Data/System/Render tests"
WORKDIR="$ART/s2"
NAME="${1:?usage: s2_render_probe.sh <name.flp> [repeat]}"
REPEAT="${2:-3}"
export WINEPREFIX="$ART/wineprefix" WINEARCH=win64 WINEDEBUG="-all"
export PATH="/usr/lib/wine:$PATH"

[[ -d "$INST" ]] || { echo "missing $INST (先に s1_wine_probe.sh)" >&2; exit 2; }
mkdir -p "$WORKDIR"
cp "$SRC/$NAME" "$WORKDIR/"

cp "$EXT/$(ls "$EXT" | grep -E '^block00038_')" "$INST/FL64.exe"
cp "$EXT/$(ls "$EXT" | grep -E '^block00031_')" "$INST/FLEngine_x64.dll"
(cd "$INST" && python3 "$ROOT/tools/flp/s1_g03_patch.py" FL64.exe && python3 "$ROOT/tools/flp/s1_g03_patch.py" FLEngine_x64.dll)

wine64 reg add 'HKCU\Software\Image-Line\FL Studio 26\Devices\Audio output' /v 'Sample rate' /t REG_SZ /d 48000 /f >/dev/null 2>&1 || true
wineserver -k >/dev/null 2>&1 || true
sleep 2

base="${NAME%.flp}"
WINPATH="$(printf '%s' "$WORKDIR" | sed 's#/#\\#g')"
for n in $(seq 1 "$REPEAT"); do
  rm -f "$WORKDIR/$base.wav"
  s=$(date +%s)
  rc=0
  (cd "$INST" && timeout 120 xvfb-run -a wine64 FL64.exe /R "Z:${WINPATH}\\$NAME" > "$WORKDIR/s2_run_$n.log" 2>&1) || rc=$?
  e=$(date +%s)
  cp "$WORKDIR/$base.wav" "$WORKDIR/${base}_run_$n.wav" 2>/dev/null || true
  python3 - "$WORKDIR/${base}_run_$n.wav" "$n" "$rc" "$((e - s))" <<'EOF'
import hashlib, struct, sys
path, n, rc, sec = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    b = open(path, "rb").read()
except OSError:
    print(f"run={n} rc={rc} sec={sec} wav=missing"); raise SystemExit
i = 12; fmt = data = None
while i + 8 <= len(b):
    cid = b[i:i+4]; sz = struct.unpack("<I", b[i+4:i+8])[0]
    if cid == b"fmt ":
        fmt = struct.unpack("<HHIIHH", b[i+8:i+24])
    if cid == b"data":
        data = b[i+8:i+8+sz]
    i += 8 + sz + (sz & 1)
print(f"run={n} rc={rc} sec={sec} fmt={fmt[0]}/{fmt[1]}ch/{fmt[2]}Hz/{fmt[5]}bit data_bytes={len(data)} sha256={hashlib.sha256(data).hexdigest()}")
EOF
done
