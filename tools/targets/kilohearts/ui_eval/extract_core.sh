#!/usr/bin/env bash
# KH-7 (#59): HeartCore.core_64 (Kilohearts release 132102 / Win64) を取り出す。出力パスを stdout の最終行に出す。
#   KH_CORE=<path>      既に展開済みならそれを使う (sha256 検証あり)
#   KH_ZIP=<path>       "Kilohearts Offline Installer.zip" の場所 (既定: ~/ダウンロード/ 、無ければ $ARTIFACTS_DIR/plugins-kilohearts.tar.zst から取り出す)
# exit 1 = 素材なし / sha256 不一致
set -euo pipefail
EXPECT_SHA=d55ce8b4c0ad7ebedf1a4a1f74443a91d255596be887a514e54269ec8751441e
WORK="${KH_UI_WORK:-$(cd -- "$(dirname -- "$0")" && pwd)/work}"; mkdir -p "$WORK"
verify() { local got; got=$(sha256sum "$1" | cut -d' ' -f1); [ "$got" = "$EXPECT_SHA" ] || { echo "sha256 mismatch: $1 $got" >&2; exit 1; }; echo "$1"; }
if [ -n "${KH_CORE:-}" ] && [ -f "$KH_CORE" ]; then verify "$KH_CORE"; exit 0; fi
OUT="$WORK/winpkg/HeartCore.core_64"
if [ -f "$OUT" ]; then verify "$OUT"; exit 0; fi
ZIP="${KH_ZIP:-}"
if [ -z "$ZIP" ]; then
  if [ -f "$HOME/ダウンロード/Kilohearts Offline Installer.zip" ]; then ZIP="$HOME/ダウンロード/Kilohearts Offline Installer.zip"
  elif [ -f "${ARTIFACTS_DIR:-$HOME/artifacts}/plugins-kilohearts.tar.zst" ]; then
    mkdir -p "$WORK/src"; tar --zstd -xf "${ARTIFACTS_DIR:-$HOME/artifacts}/plugins-kilohearts.tar.zst" -C "$WORK/src" "Kilohearts Offline Installer.zip"
    ZIP="$WORK/src/Kilohearts Offline Installer.zip"
  else echo "素材なし: plugins-kilohearts (oc_artifacts) が必要" >&2; exit 1; fi
fi
mkdir -p "$WORK/win" "$WORK/blobs" "$WORK/winpkg"
unzip -q -o "$ZIP" payload.dat -d "$WORK/win"
unzip -q -o "$WORK/win/payload.dat" index.json 'windows.zip/*' -d "$WORK/blobs"
W=$(ls "$WORK"/blobs/windows.zip/* | grep -v '/$' | head -1)
unzip -q -o "$W" HeartCore.core_64 -d "$WORK/winpkg"
rm -rf "$WORK/win" "$WORK/src"          # 3.8GB の中間物は残さない
verify "$OUT"
