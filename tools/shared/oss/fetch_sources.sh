#!/usr/bin/env bash
# upstream ソース取得 (バージョンは各 lib のバイナリ実測から決定; REPORT.md §3 参照)
#   freetype 2.7        <- libfreetype_x64.dylib 内パス "/Users/eugene/Documents/freetype-2.7/" (mac)
#   libogg / libvorbis  <- oggio_x64.dll 内 "Xiph.Org libVorbis I 20150105" = libvorbis 1.3.5
#   libFLAC 1.3.1       <- oggio_x64.dll 内 "reference libFLAC 1.3.1 20141125"
#   libFLAC 1.5.0       <- EasyFLAC_x64.dylib 内 "reference libFLAC 1.5.0 20250211"
#   LAME 3.99.5         <- libmp3lame_x64.dylib 内 LAME 3.99.5
#   WavPack 4.80/4.60.1 <- wavpack_x64.dylib / wavpack_x64.dll の version 文字列
#   FFmpeg n4.4.2/4.4.3 <- win 6 DLL / mac の n4.4.x
#   cppfw/{svgdom,svgren,papki,utki,mikroxml,cssom} <- ILSvg version 特定用
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
dl https://downloads.xiph.org/releases/flac/flac-1.5.0.tar.xz flac-1.5.0.tar.xz
# LAME 3.99.5: savannah の /releases/lame/ は 404。sourceforge の project ミラーが正 (dl で -L 追従)
dl https://downloads.sourceforge.net/project/lame/lame/3.99/lame-3.99.5.tar.gz lame-3.99.5.tar.gz
# WavPack: github の release asset は無いため tag の archive tarball を使う
dl https://github.com/dbry/WavPack/archive/refs/tags/4.80.0.tar.gz wavpack-4.80.0.tar.gz
dl https://github.com/dbry/WavPack/archive/refs/tags/4.60.1.tar.gz wavpack-4.60.1.tar.gz
# FFmpeg n4.4.2 (win 実測, --enable-version3 無しの LGPL2.1+) / n4.4.3 (mac 実測)
dl https://ffmpeg.org/releases/ffmpeg-4.4.2.tar.bz2 ffmpeg-4.4.2.tar.bz2
dl https://ffmpeg.org/releases/ffmpeg-4.4.3.tar.xz ffmpeg-4.4.3.tar.xz
# ILSvg (cppfw): version 特定に使う upstream ソース
for r in svgdom svgren papki utki mikroxml cssom; do
  [ -d "cppfw-$r" ] || git clone -q --filter=blob:none "https://github.com/cppfw/$r.git" "cppfw-$r"
done
for t in freetype-2.7.tar.gz libogg-1.3.2.tar.gz libvorbis-1.3.5.tar.gz lame-3.99.5.tar.gz wavpack-4.80.0.tar.gz wavpack-4.60.1.tar.gz; do d="${t%.tar.gz}"; [ -d "$d" ] || tar xzf "$t"; done
[ -d flac-1.3.1 ] || tar xJf flac-1.3.1.tar.xz
[ -d flac-1.5.0 ] || tar xJf flac-1.5.0.tar.xz
[ -d ffmpeg-4.4.2 ] || tar xjf ffmpeg-4.4.2.tar.bz2
[ -d ffmpeg-4.4.3 ] || tar xJf ffmpeg-4.4.3.tar.xz
echo "[fetch] sources ready in $SRC"
