#!/usr/bin/env bash
# SR-47 (#2414): 参照の content dir = installer 全展開 (Tables・Presets 等あり) を作る。素材 plugins-serum2 から展開する。
# usage: bash ref_content.sh [installer.exe]
#   installer 既定: work/dl/Install_Xfer_Serum2_2.1.5.exe。無ければ $ARTIFACTS_DIR の plugins-serum2.tar.zst から取り出す。
# 出力 (work/ は gitignore): content_full/ (7z x の全展開。Tables あり) と Serum2_win64.vst3 (DLL・無改変 sha256 501e7bb3…5283)。
# 既に展開済みなら作り直さない。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SERUM_DIR="$(cd "$HERE/.." && pwd)"
W="$SERUM_DIR/work"
ART="${ARTIFACTS_DIR:-}"
EXE="${1:-$W/dl/Install_Xfer_Serum2_2.1.5.exe}"
mkdir -p "$W/dl"
if [ ! -f "$EXE" ]; then
  [ -f "$ART/plugins-serum2.tar.zst" ] || { echo "FAIL: installer も $ART/plugins-serum2.tar.zst も無い (素材 plugins-serum2 が必要)" >&2; exit 1; }
  tar --zstd -xf "$ART/plugins-serum2.tar.zst" -C "$W/dl" Install_Xfer_Serum2_2.1.5.exe
  EXE="$W/dl/Install_Xfer_Serum2_2.1.5.exe"
fi
if [ ! -d "$W/content_full/Tables" ]; then
  mkdir -p "$W/content_full"
  7z x -y -o"$W/content_full" "$EXE" > "$W/content_full.log"
fi
DLL="$W/content_full/\$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3"
[ -f "$DLL" ] || { echo "FAIL: 展開後に DLL が無い: $DLL" >&2; exit 1; }
cp "$DLL" "$W/Serum2_win64.vst3"
SHA="$(sha256sum "$W/Serum2_win64.vst3" | cut -d' ' -f1)"
case "$SHA" in 501e7bb3*5283) ;; *) echo "FAIL: DLL sha256 が想定外 ($SHA)" >&2; exit 1 ;; esac
echo "content_full=$W/content_full tables=$([ -d "$W/content_full/Tables" ] && echo yes || echo no) dll_sha256=${SHA:0:8}…${SHA: -4}"
