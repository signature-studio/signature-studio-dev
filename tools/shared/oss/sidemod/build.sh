#!/usr/bin/env bash
# LGL-4: FFmpeg n4.4.2 / LAME 3.99.5 を upstream から再ビルドし、FL 由来 wasm とは別の
# SIDE_MODULE (ffmpeg.wasm / lame.wasm) にする。host (MAIN_MODULE) が dlopen でロードする。
#   usage: bash oss/sidemod/build.sh        (TMPDIR 直下でビルド、成果は work/build/sidemod)
#   前提: emcc 6.0.12 (SS_EMSDK_ENV に emsdk_env.sh のパス、既定 /opt/emsdk/emsdk_env.sh)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
S="$ROOT/work/src"; B="$ROOT/work/build/sidemod"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"  # emsdk_env.sh は EMSDK_ENV を unset するので別名にする
[ -f "$SS_EMSDK_ENV" ] || { echo "[sidemod] emsdk_env.sh not found: $SS_EMSDK_ENV (SS_EMSDK_ENV で指定)"; exit 2; }
source "$SS_EMSDK_ENV" >/dev/null 2>&1
FFV=4.4.2; LV=3.99.5
J=$(nproc)
mkdir -p "$B" "$S"
dl() { [ -s "$2" ] || curl -fsSL --retry 3 -o "$2" "$1"; }
( cd "$S"
  dl https://ffmpeg.org/releases/ffmpeg-$FFV.tar.bz2 ffmpeg-$FFV.tar.bz2
  dl https://downloads.sourceforge.net/project/lame/lame/3.99/lame-$LV.tar.gz lame-$LV.tar.gz
  [ -d ffmpeg-$FFV ] || tar xjf ffmpeg-$FFV.tar.bz2
  [ -d lame-$LV ] || tar xzf lame-$LV.tar.gz )

# FFmpeg の configure 引数 (oss/ffmpeg/build.sh と同一の最小構成 + --enable-pic)。
# ここに GPL / version3 / nonfree を入れると check_license_flags.py が落とす。
FF_ARGS=(--prefix=/nonexistent --target-os=none --arch=generic --cpu=generic --enable-cross-compile
  --disable-x86asm --disable-inline-asm --disable-doc --disable-programs
  --disable-network --disable-postproc --disable-swscale --disable-avfilter --disable-everything
  --disable-bzlib --disable-zlib --disable-lzma --disable-iconv --disable-debug
  --enable-decoder=flac,mp3,vorbis,pcm_s16le,wmav2,aac
  --enable-parser=flac,mpegaudio,vorbis,aac
  --enable-demuxer=wav,flac,ogg,mp3,matroska,aiff
  --enable-protocol=file --enable-bsf=null --enable-pic ${FF_EXTRA_ARGS:-})
LAME_ARGS=(--disable-shared --enable-static --disable-nasm --disable-decoder --disable-frontend
  --disable-gtktest --disable-analyzer-hooks ${LAME_EXTRA_ARGS:-})

# --- 1. 検出 CI を configure *前* に実行 (GPL フラグが入っていればビルドせず失敗) ---
python3 "$HERE/check_license_flags.py" config "${FF_ARGS[*]}"
python3 "$HERE/check_license_flags.py" lame "${LAME_ARGS[*]}" -- /dev/null
echo "${FF_ARGS[*]}" > "$B/ffmpeg.configure"; echo "${LAME_ARGS[*]}" > "$B/lame.configure"

# --- 2. FFmpeg 静的 lib (-fPIC) を native / wasm32 で ---
build_ff() { # name cc-args...
  local N="$1"; shift; local D="$ROOT/work/tmp/sidemod-ffmpeg-$N"
  rm -rf "$D"; mkdir -p "$(dirname "$D")"; cp -a "$S/ffmpeg-$FFV" "$D"
  ( cd "$D"
    if [ "$N" = wasm32 ]; then
      emconfigure ./configure "${FF_ARGS[@]}" --cc=emcc --cxx=em++ --ar=emar --ranlib=emranlib --nm=llvm-nm --strip=llvm-strip >configure.log 2>&1
      emmake make -j"$J" >make.log 2>&1
    else
      ./configure "${FF_ARGS[@]}" >configure.log 2>&1; make -j"$J" >make.log 2>&1
    fi )
  echo "[sidemod] ffmpeg $N built: avcodec.a $(stat -c %s "$D/libavcodec/libavcodec.a")B"
}
echo "[sidemod] ffmpeg configure+make (wasm32, native 並列)"
build_ff wasm32 & build_ff native & wait
FFW="$ROOT/work/tmp/sidemod-ffmpeg-wasm32"; FFN="$ROOT/work/tmp/sidemod-ffmpeg-native"
cp "$FFW/config.h" "$B/ffmpeg-config.h"
python3 "$HERE/check_license_flags.py" configh "$B/ffmpeg-config.h"

# --- 3. LAME (-fPIC, mpglib なし) ---
L="$ROOT/work/tmp/sidemod-lame"; rm -rf "$L"; cp -a "$S/lame-$LV" "$L"
( cd "$L" && ./configure "${LAME_ARGS[@]}" --build=x86_64-pc-linux-gnu >configure.log 2>&1 )
sed -e 's|^#define HAVE_XMMINTRIN_H 1|/* wasm: no x86 intrinsics */|' -e 's|^#define MIN_ARCH_SSE 1|/* wasm: no SSE */|' \
    "$L/config.h" > "$B/lame-wasm-config.h"
LSRC=$(find "$L/libmp3lame" -name '*.c' | grep -v -E 'i386|vector|logo|mpglib' | sort)
LINC="-I$L/include -I$L/libmp3lame -I$L"
LDEF='-DPACKAGE_VERSION="3.99.5"'

# --- 4. SIDE_MODULE (wasm) と native 基準 (.so) ---
FFLIBS="$FFW/libavformat/libavformat.a $FFW/libavcodec/libavcodec.a $FFW/libavutil/libavutil.a"
emcc -O2 -w -fPIC -I"$FFW" -sSIDE_MODULE=2 -o "$B/ffmpeg.wasm" "$HERE/ffmpeg_side.c" $FFLIBS
emcc -O2 -w -fPIC -ffp-contract=off -include "$B/lame-wasm-config.h" $LINC $LDEF -sSIDE_MODULE=2 \
  -o "$B/lame.wasm" "$HERE/lame_side.c" $LSRC
emcc -O2 -w -sMAIN_MODULE=1 -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=_main -o "$B/host.cjs" "$HERE/host.c"
echo "[sidemod] ffmpeg.wasm $(stat -c %s "$B/ffmpeg.wasm")B / lame.wasm $(stat -c %s "$B/lame.wasm")B / host.wasm $(stat -c %s "$B/host.wasm")B"

gcc -O2 -w -fPIC -shared -I"$FFN" -o "$B/ffmpeg-native.so" "$HERE/ffmpeg_side.c" \
  -Wl,--whole-archive $(for l in libavformat libavcodec libavutil; do echo "$FFN/$l/$l.a"; done) -Wl,--no-whole-archive -lm -lpthread
gcc -O2 -w -fPIC -shared -ffp-contract=off -include "$B/lame-wasm-config.h" $LINC $LDEF \
  -o "$B/lame-native.so" "$HERE/lame_side.c" $LSRC -lm
gcc -O2 -w -o "$B/host-native" "$HERE/host.c" -ldl
echo "[sidemod] build done"
