#!/usr/bin/env bash
# Kilohearts Offline Installer (dmg + zip) → 製品バイナリ抽出。 1 コマンド: bash scripts/extract_installer.sh
# 出力: work/winpkg (Windows 製品一式), work/macpkg (macOS 製品一式), work/blobs/index.json (製品定義)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$HERE"
SRC="${KH_SRC:-$HOME/ダウンロード}"
ZIP="$SRC/Kilohearts Offline Installer.zip"
DMG="$SRC/Kilohearts Offline Installer.dmg"
mkdir -p work/win work/dmg work/blobs work/winpkg work/macpkg work/mac_slices

# --- Windows: zip = [Kilohearts Installer.exe (自製インストーラ), payload.dat (zip 形式の content-addressed ストア)]
[ -f work/win/payload.dat ] || unzip -q -o "$ZIP" -d work/win
# --- macOS: dmg(bzip2 UDIF) → HFS+ → "Kilohearts Installer.app" + ".payload" (= win の payload.dat と同構造)
if [ ! -f "work/dmg/Kilohearts Installer/.payload" ]; then
  7z x -y -owork/dmg "$DMG" > work/dmg_7z.log 2>&1 || true   # 末尾 "Unexpected end of archive" 警告は無害 (.payload の zip central dir は完全)
fi
python3 - <<'EOF'
import zipfile
for tag, p in (("win", "work/win/payload.dat"), ("mac", "work/dmg/Kilohearts Installer/.payload")):
    z = zipfile.ZipFile(p)
    bad = z.testzip() if False else None   # 3.8GB 全 CRC 検証は run_all の --full で
    print(tag, "entries", len(z.infolist()), "uncompressed", sum(i.file_size for i in z.infolist()))
EOF
# --- payload 内の製品 blob: windows.zip/<hash>, mac.zip/<hash>, index.json
unzip -q -o work/win/payload.dat index.json 'windows.zip/*' -d work/blobs
unzip -q -o "work/dmg/Kilohearts Installer/.payload" 'mac.zip/*' -d work/blobs
W=$(ls work/blobs/windows.zip/* | grep -v '/$' | head -1); M=$(ls work/blobs/mac.zip/* | grep -v '/$' | head -1)
unzip -q -o "$W" -d work/winpkg
unzip -q -o "$M" -d work/macpkg
# --- mac universal → x86_64 / arm64 slice
llvm-lipo work/macpkg/HeartCore.core/Contents/MacOS/HeartCore -thin x86_64 -output work/mac_slices/HeartCore_x86_64
llvm-lipo work/macpkg/HeartCore.core/Contents/MacOS/HeartCore -thin arm64 -output work/mac_slices/HeartCore_arm64
echo "OK: winpkg=$(find work/winpkg -type f | wc -l) files, macpkg=$(find work/macpkg -type f | wc -l) files"
