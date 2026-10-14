#!/usr/bin/env bash
# #2190 / T-SH-34: QuickFontCache の GetProcAddress 引数を Wine の relay で記録する。
# 素材 (fl-win64.tar.zst) の block24350_PE.bin を複製して使い、素材本体は変更しない。
# 出力は work/qfc/ (gitignore 対象)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ART="${ARTIFACTS_DIR:-$HOME/artifacts}"
W="$(git rev-parse --show-toplevel)/work/qfc"
mkdir -p "$W/extracted"
cd "$W"
export WINEDEBUG="${WINEDEBUG_OVERRIDE:-+relay}" WINEPREFIX="$W/wpfx"

tar --zstd -xf "$ART/fl-win64.tar.zst" -C "$W" extracted/block24350_PE.bin
python3 "$HERE/patch_entry.py" extracted/block24350_PE.bin QuickFontCache_x64.dll
x86_64-w64-mingw32-gcc -shared -O1 -o dsp_ippv2_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
x86_64-w64-mingw32-gcc -shared -O1 -o freetype_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
x86_64-w64-mingw32-gcc -O0 -o probe.exe "$HERE/probe.c"

Xvfb :77 -screen 0 1024x768x24 >/dev/null 2>&1 &
XPID=$!
sleep 3
set +e
DISPLAY=:77 timeout 60 wine probe.exe > probe_out.txt 2> trace.log
RC=$?
set -e
kill "$XPID" 2>/dev/null || true

echo "wine rc=$RC"
cat probe_out.txt
echo "relay lines: $(wc -l < trace.log)"
# QuickFontCache 内 (VA 0x7bde0000-0x7bfee000) からの GetProcAddress 呼出しだけを抜く
grep -E 'GetProcAddress\(' trace.log | grep -E 'ret=7bd[e-f][0-9a-f]{5}|ret=7b[e-f][0-9a-f]{6}' > qfc_gpa_calls.txt || true
echo "QuickFontCache 内からの GetProcAddress 呼出し: $(wc -l < qfc_gpa_calls.txt) 件"
