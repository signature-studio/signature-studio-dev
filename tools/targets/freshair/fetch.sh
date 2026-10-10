#!/usr/bin/env bash
# 素材展開: ~/ダウンロード の Fresh Air.Win.zip / Fresh Air.pkg → work/win, work/mac/x (再実行可)
set -euo pipefail
FA="$(cd -- "$(dirname -- "$0")" && pwd)"; DL="${FA_DL:-$HOME/ダウンロード}"
mkdir -p "$FA/work/win" "$FA/work/mac/x"
[ -d "$FA/work/win/Fresh Air" ] || unzip -q -o "$DL/Fresh Air.Win.zip" -d "$FA/work/win"
cd "$FA/work/mac"
[ -f Distribution ] || xar -xf "$DL/Fresh Air.pkg"
for p in 1_-_AU 2_-_VST3 3_-_APP,_Uninstaller 4_-_Content; do
  if [ -z "$(ls -A "x/$p" 2>/dev/null)" ]; then mkdir -p "x/$p"; (cd "x/$p" && gzip -dc "../../$p.pkg/Payload" | cpio -idm --quiet); fi
done
echo "[fetch] win: $(find "$FA/work/win" -type f | wc -l) files, mac: $(find "$FA/work/mac/x" -type f | wc -l) files"
