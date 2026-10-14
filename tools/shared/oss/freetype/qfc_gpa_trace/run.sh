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
rm -rf "$WINEPREFIX"

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
# 範囲判定は LoadLibrary の基底 (実測 7bde0000) と PE の SizeOfImage から行う (filter_gpa.py)。
# 件数は Call 行のみ。陽性対照として probe.exe (ImageBase 0x140000000) の呼出しを同じ判定器に通す。
QFC_BASE="$(sed -n 's/^LoadLibrary=\([0-9a-f]*\) .*/\1/p' probe_out.txt)"
[ -n "$QFC_BASE" ] && [ "$QFC_BASE" != "0000000000000000" ] || { echo "LoadLibrary 失敗: 範囲判定不可"; exit 1; }
python3 "$HERE/filter_gpa.py" trace.log QuickFontCache_x64.dll "$QFC_BASE" > qfc_gpa_calls.txt || true
python3 "$HERE/filter_gpa.py" trace.log probe.exe 140000000 'CreateVST3Instance|InitDll' > probe_pos_ctrl.txt || true
python3 "$HERE/filter_gpa.py" trace.log probe.exe 140000000 > probe_pos_all.txt || true
echo "QuickFontCache 内からの GetProcAddress 呼出し (Call): $(wc -l < qfc_gpa_calls.txt) 件"
echo "陽性対照 probe (InitDll/CreateVST3Instance): $(wc -l < probe_pos_ctrl.txt) 件 / probe 全体: $(wc -l < probe_pos_all.txt) 件"
