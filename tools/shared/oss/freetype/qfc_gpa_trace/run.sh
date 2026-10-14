#!/usr/bin/env bash
# #2190 / T-SH-34, #2220: QuickFontCache の GetProcAddress 引数を Wine の relay で記録する。
# 既定は素材の DllMain をそのまま使う (#2220)。FT 解決 (0x563000) は DllMain の PROCESS_ATTACH 経路で走る。
# DllMain はその後ウィンドウ処理で戻らないため timeout で打ち切り、relay の記録から範囲判定する。
# QFC_PATCH_ENTRY=1 で旧方式 (entry を mov eax,1; ret に置換。#2190 の 0 件はこの方式) に戻す。
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
if [ "${QFC_PATCH_ENTRY:-0}" = 1 ]; then
  python3 "$HERE/patch_entry.py" extracted/block24350_PE.bin QuickFontCache_x64.dll
else
  cp extracted/block24350_PE.bin QuickFontCache_x64.dll
fi
x86_64-w64-mingw32-gcc -shared -O1 -o dsp_ippv2_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
x86_64-w64-mingw32-gcc -shared -O1 -o freetype_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
x86_64-w64-mingw32-gcc -O0 -o probe.exe "$HERE/probe.c"

Xvfb :77 -screen 0 1024x768x24 >/dev/null 2>&1 &
XPID=$!
sleep 3
# prefix の作成は relay の記録に含めない (記録量と時間を抑える)
WINEDEBUG=-all DISPLAY=:77 timeout 180 wineboot -i >wineboot.log 2>&1 || true
set +e
DISPLAY=:77 timeout "${QFC_TIMEOUT:-150}" wine probe.exe > probe_out.txt 2> trace.log
RC=$?
set -e
kill "$XPID" 2>/dev/null || true

echo "wine rc=$RC"
cat probe_out.txt
echo "relay lines: $(wc -l < trace.log)"
# 範囲判定は LoadLibrary の基底 (DllMain の PROCESS_ATTACH 行の module=) と PE の SizeOfImage から行う (filter_gpa.py)。
# DllMain は戻らないことがあるため probe_out の LoadLibrary 行には依存しない。
QFC_BASE="$(grep -m1 'PE DLL (.*L"QuickFontCache_x64.dll",reason=PROCESS_ATTACH' trace.log | sed -n 's/.*module=\([0-9A-Fa-f]*\) .*/\1/p')"
[ -n "$QFC_BASE" ] && [ "$QFC_BASE" != "0000000000000000" ] || { echo "PROCESS_ATTACH 行が無い: 範囲判定不可"; exit 1; }
python3 "$HERE/filter_gpa.py" trace.log QuickFontCache_x64.dll "$QFC_BASE" > qfc_gpa_calls.txt || true
# 陽性対照: probe.exe (ImageBase 0x140000000) の呼出しを同じ判定器に通す
python3 "$HERE/filter_gpa.py" trace.log probe.exe 140000000 'GetLastError|CreateVST3Instance|InitDll' > probe_pos_ctrl.txt || true
python3 "$HERE/filter_gpa.py" trace.log probe.exe 140000000 > probe_pos_all.txt || true
echo "QuickFontCache 内からの GetProcAddress 呼出し (Call): $(wc -l < qfc_gpa_calls.txt) 件"
echo "  うち FT_* 名: $(grep -c '"FT_' qfc_gpa_calls.txt || true) 件"
echo "  うち欠落 17 本の名前: $(grep -cFf "$HERE/missing17.txt" qfc_gpa_calls.txt || true) 件"
echo "陽性対照 probe (GetLastError/InitDll/CreateVST3Instance): $(wc -l < probe_pos_ctrl.txt) 件 / probe 全体: $(wc -l < probe_pos_all.txt) 件"
