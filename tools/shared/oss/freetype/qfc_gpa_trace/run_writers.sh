#!/usr/bin/env bash
# #3369 / T-SH-72: 登録簿 [0x5d0c90] の書込み元 (W1 = 0x40f48b・W2 = 0x40fcf5) を Wine 上で実行して記録する。
# 素材の QuickFontCache を複製し、2 つの書込み命令を int3 に置換する (patch_writers.py)。素材本体は変更しない。
# 出力は work/qfc/writers/ (gitignore 対象)。前提: apt の wine64 (/usr/lib/wine/wine64)・gcc-mingw-w64-x86-64・xvfb。
# 再現: bash tools/shared/oss/freetype/qfc_gpa_trace/run_writers.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ART="${ARTIFACTS_DIR:?ARTIFACTS_DIR に素材の置き場を設定する}"
W="$(git rev-parse --show-toplevel)/work/qfc/writers"
mkdir -p "$W/extracted"
cd "$W"
WINE="${WINE:-/usr/lib/wine/wine64}"
export WINEDEBUG=-all WINEPREFIX="$W/wpfx"
rm -rf "$WINEPREFIX"

tar --zstd -xf "$ART/fl-win64.tar.zst" -C "$W" extracted/block24350_PE.bin
python3 "$HERE/patch_writers.py" extracted/block24350_PE.bin QuickFontCache_x64.dll
x86_64-w64-mingw32-gcc -shared -O1 -o dsp_ippv2_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
x86_64-w64-mingw32-gcc -shared -O1 -o freetype_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
# PROBE_CFLAGS=-DSKIP_MSGBOX=1 で、0x40fb56 の MessageBoxA (モーダル) を IDOK で即時に戻す変種を作る
x86_64-w64-mingw32-gcc -O0 ${PROBE_CFLAGS:-} -o writers_probe.exe "$HERE/writers_probe.c"

Xvfb :77 -screen 0 1024x768x24 >/dev/null 2>&1 &
XPID=$!
sleep 3
DISPLAY=:77 timeout 180 "$WINE" wineboot -i >wineboot.log 2>&1 || true
set +e
DISPLAY=:77 timeout "${WRITERS_TIMEOUT:-150}" "$WINE" writers_probe.exe > probe_out.txt 2> trace.log
RC=$?
set -e
kill "$XPID" 2>/dev/null || true
WINEPREFIX="$WINEPREFIX" "${WINE%/*}/wineserver" -k 2>/dev/null || true

echo "wine rc=$RC (124 = timeout で打ち切り。DllMain はウィンドウ処理で戻らない)"
echo "probe stdout:"
cat probe_out.txt
echo "W1 (0x40f48b) hit: $(grep -c '^W1 ' trace.log || true) 件 / W2 (0x40fcf5) hit: $(grep -c '^W2 ' trace.log || true) 件"
grep -E '^(W[12]|P) ' trace.log || true
