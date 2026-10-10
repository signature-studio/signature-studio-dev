#!/usr/bin/env bash
# upstream ソース取得 (バージョンは各 lib のバイナリ実測から決定; REPORT.md §3 参照)
#   freetype 2.7        <- libfreetype_x64.dylib 内パス "/Users/eugene/Documents/freetype-2.7/" (mac)
#   libogg / libvorbis  <- oggio_x64.dll 内 "Xiph.Org libVorbis I 20150105" = libvorbis 1.3.5
#   libFLAC 1.3.1       <- oggio_x64.dll 内 "reference libFLAC 1.3.1 20141125"
#   blend2d + asmjit    <- libblend2d.dylib / Blend2D.dll 内 asmjit ABI "_abi_1_13"
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SRC="$HERE/../work/src"; mkdir -p "$SRC"; cd "$SRC"
dl() { # url file
  [ -s "$2" ] || curl -fsSL --retry 3 -o "$2" "$1"
}
dl https://download.savannah.gnu.org/releases/freetype/freetype-2.7.tar.gz freetype-2.7.tar.gz
dl https://downloads.xiph.org/releases/ogg/libogg-1.3.2.tar.gz libogg-1.3.2.tar.gz
dl https://downloads.xiph.org/releases/vorbis/libvorbis-1.3.5.tar.gz libvorbis-1.3.5.tar.gz
dl https://downloads.xiph.org/releases/flac/flac-1.3.1.tar.xz flac-1.3.1.tar.xz
for t in freetype-2.7.tar.gz libogg-1.3.2.tar.gz libvorbis-1.3.5.tar.gz; do d="${t%.tar.gz}"; [ -d "$d" ] || tar xzf "$t"; done
[ -d flac-1.3.1 ] || tar xJf flac-1.3.1.tar.xz
echo "[fetch] sources ready in $SRC"
