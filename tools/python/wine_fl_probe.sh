#!/usr/bin/env bash
# #5838: wine64 9.0 で FL64.exe を起動し、FLEngine_x64.dll への到達を記録する。
# 素材: ART 環境変数で指定 (oc_artifacts: fl-win64 の .tar.zst)。生成物は RUNNER_TEMP 配下。
set -u
ART="${ART:-${HOME}/artifacts/fl-win64.tar.zst}"
W="${RUNNER_TEMP:-/tmp}/fl5838"
P="${RUNNER_TEMP:-/tmp}/wineprefix"
WINE="${WINE:-$(command -v wine64 || echo /usr/lib/wine/wine64)}"
FL_DIR="$P/drive_c/Program Files/Image-Line/FL Studio 2026"
export WINEPREFIX="$P" WINEDEBUG="${WINEDEBUG:--all}"

[ -f "$ART" ] || { echo "NO_ARTIFACT $ART" >&2; exit 2; }
command -v "$WINE" >/dev/null || { echo "NO_WINE64 (apt-get install wine64 wine32:i386)" >&2; exit 2; }

mkdir -p "$W" && cd "$W" || exit 2
[ -d extracted ] || tar --zstd -xf "$ART" || exit 2

if [ ! -f "$FL_DIR/FLEngine_x64.dll" ]; then
  [ -d "$P/drive_c" ] || timeout 120 "$WINE" wineboot --init >/dev/null 2>&1
  # インストーラは PowerShell 段階で timeout するが、展開は完了する (#5838 で確認)。
  timeout 150 xvfb-run -a "$WINE" flstudio_win64_26.1.7.5653.exe /S >/dev/null 2>&1
fi
[ -f "$FL_DIR/FLEngine_x64.dll" ] || { echo "NO_FLENGINE_EXTRACTED" >&2; exit 3; }

# 同一性: block00031_PE.bin と一致すること
a=$(sha256sum "$FL_DIR/FLEngine_x64.dll" | cut -c1-16)
b=$(sha256sum "extracted/block00031_PE.bin" | cut -c1-16)
echo "flengine_sha256_16 installed=$a block00031=$b"

# FL64.exe を一定時間起動し、FLEngine_x64.dll への CreateFileW / LoadLibrary を記録する
cd "$FL_DIR" || exit 2
WINEDEBUG=+relay timeout "${FL_SECS:-90}" xvfb-run -a "$WINE" FL64.exe > "$W/fl_relay.log" 2>&1
echo "fl64_rc=$?"
echo "createfile_flengine=$(grep -c 'KERNEL32.CreateFileW(.*FLEngine_x64.dll' "$W/fl_relay.log")"
echo "sip_guid_flengine=$(grep -c 'CryptSIPRetrieveSubjectGuid(.*FLEngine_x64.dll' "$W/fl_relay.log")"
echo "loadlibrary_flengine=$(grep -c 'LoadLibraryW(.*FLEngine' "$W/fl_relay.log")"
echo "winverifytrust_ret=$(grep -o 'Ret  wintrust.WinVerifyTrust() retval=[0-9a-f]*' "$W/fl_relay.log" | sed 's/.*retval=//' | tr '\n' ' ')"
echo "msgbox_unverified=$(grep -c 'MessageBoxA(.*could not be verified' "$W/fl_relay.log")"
echo "unsupported_spc_decoder=$(grep -c 'CryptDecodeObjectEx Unsupported decoder for 1.3.6.1.4.1.311.2.1.4' "$W/fl_relay.log" || true)"
echo "log=$W/fl_relay.log"
