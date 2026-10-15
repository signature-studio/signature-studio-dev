#!/usr/bin/env bash
# #3257 / T-SH-55: 関数ポインタ表 (RVA 0x19c7e0・81 組) の読み手を、表の全要素を観測用スタブへ差し替えて特定する。
# スタブは jmp [GetTickCount] (tail jump) なので、Wine relay の `Call KERNEL32.GetTickCount() ret=...` に
# 表の読み手の呼出し箇所 (戻り番地) が出る。DllMain は無改変で実行する (PATCH_ENTRY=0 相当)。
# 出力は work/qfc-table/ (gitignore 対象)。素材本体は変更しない。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ART="${ARTIFACTS_DIR:-$HOME/artifacts}"
W="$(git rev-parse --show-toplevel)/work/qfc-table"
WINE="${WINE_BIN:-/usr/lib/wine/wine64}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-120}"
STUB_RVA=0x1a9100
mkdir -p "$W/extracted"
cd "$W"
export WINEPREFIX="$W/wpfx"
rm -rf "$WINEPREFIX"

tar --zstd -xf "$ART/fl-win64.tar.zst" -C "$W" extracted/block24350_PE.bin
python3 "$HERE/table_stub.py" extracted/block24350_PE.bin QuickFontCache_x64.dll GetTickCount "$STUB_RVA"
x86_64-w64-mingw32-gcc -shared -O1 -o dsp_ippv2_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
x86_64-w64-mingw32-gcc -shared -O1 -o freetype_x64.dll "$HERE/stub.c" -Wl,--subsystem,windows
x86_64-w64-mingw32-gcc -O0 -o probe.exe "$HERE/probe.c"

Xvfb :78 -screen 0 1024x768x24 >/dev/null 2>&1 &
XPID=$!
sleep 3
DISPLAY=:78 WINEDEBUG=-all timeout 240 "$WINE" wineboot -i > wineboot.txt 2>&1 || true
export WINEDEBUG=+relay
set +e
DISPLAY=:78 timeout "$PROBE_TIMEOUT" "$WINE" probe.exe > probe_out.txt 2> trace.log
RC=$?
set -e
kill "$XPID" 2>/dev/null || true

echo "probe rc=$RC (124 = 時間切れ)"
cat probe_out.txt
QFC_BASE="$(sed -n 's/^LoadLibrary=\([0-9a-f]*\) .*/\1/p' probe_out.txt)"
[ -n "$QFC_BASE" ] && [ "$QFC_BASE" != "0000000000000000" ] || { echo "LoadLibrary 失敗"; exit 1; }
echo "GetTickCount 呼出し (表スタブ経由): $(grep -c 'Call .*GetTickCount' trace.log) 件"
grep 'Call .*GetTickCount' trace.log | grep -oE 'ret=[0-9a-f]+' | sort | uniq -c | sort -rn > stub_ret_sites.txt
while read -r n r; do
  rva=$(printf '0x%x' $((0x${r#ret=} - 0x$QFC_BASE)))
  echo "  $n 回  ret=${r#ret=} (RVA $rva)"
done < stub_ret_sites.txt
python3 "$HERE/callgraph.py" extracted/block24350_PE.bin 0x59c1f0 6 0x40f390 0x40f2f0 | tee callgraph.txt
