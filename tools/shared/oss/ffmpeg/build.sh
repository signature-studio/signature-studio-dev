#!/usr/bin/env bash
# FFmpeg n4.4.2 (win 実測, --enable-version3 無し = LGPL-2.1+; mac 実測は n4.4.3) を upstream から
# native gcc / emscripten wasm32 / wasm64 で再ビルドし、同一 test_ffmpeg.c の復号 PCM hash を突合する。
#   usage: bash oss/ffmpeg/build.sh [4.4.2]   (version 引数で 4.4.3 も可)
#   * ビルドは TMPDIR 直下 (実ディスク・gitignore 対象外なので add 事故がない) で行い、
#     成果 (.a / .cjs / .wasm / out.txt) だけ work/build/ffmpeg に置く
#
# 【重要な設計判断 (LGPL version3 論点 = CAB-148 の決定事項)】:
#   lift 済み FL コードと同一 wasm に FFmpeg を静的リンクしない。
#   FL 側の libILVideo glue (26 export) は非互換の代替 (flac/vorbis/mp3/wmav2/pcm の最小デコーダ)
#   を別途持ち、FFmpeg は *独立した wasm モジュール / Worker* として構築する (本 build.sh の構成)。
#   version3 を有効化しない configure (CONFIG_VERSION3=0) なので LGPL-2.1+ のままで、
#   静的リンクしても version3 の条項は持ち込まない。
#
# 構成:
#   --disable-everything + flac/mp3/vorbis/pcm_s16le/wmav2/aac decoder、
#   wav/flac/ogg/mp3/matroska/aiff demuxer, file protocol のみ (FL の音声読み込み経路に必要最小限)。
#   zlib/bz2/lzma/asm は無効 (nasm 非搭載 & emscripten の sysroot に無い or 不要)。
#   -sMEMORY64=1 (wasm64) は configure の try-compile を壊すため ffbuild/config.mak の
#   CFLAGS に直接注入する (configure 後・make 前)。
set -euo pipefail
PATH="$HOME/.local/share/pnpm/bin:$PATH"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
S="$ROOT/work/src"; B="$ROOT/work/build/ffmpeg"
V=${1:-4.4.2}
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
[ -d "$S/ffmpeg-$V" ] || bash "$ROOT/oss/fetch_sources.sh"
mkdir -p "$B"

FF_CFG() { # dir configure-program...
  local D="$1"; shift
  ( cd "$D" && "$@" --prefix=/nonexistent \
    --target-os=none --arch=generic --cpu=generic --enable-cross-compile \
    --disable-x86asm --disable-inline-asm --disable-doc \
    --disable-ffmpeg --disable-ffplay --disable-ffprobe \
    --disable-network --disable-postproc --disable-swscale --disable-avfilter --disable-everything \
    --disable-bzlib --disable-zlib --disable-lzma --disable-iconv \
    --enable-decoder=flac,mp3,vorbis,pcm_s16le,wmav2,aac \
    --enable-parser=flac,mpegaudio,vorbis,aac \
    --enable-demuxer=wav,flac,ogg,mp3,matroska,aiff \
    --enable-protocol=file --enable-bsf=null )
}
LIBS="libavformat/libavformat.a libavcodec/libavcodec.a libavutil/libavutil.a"

# ---------- native ----------
echo "[ffmpeg $V] native configure+make"
D="$B/native-src"; rm -rf "$D"; cp -a "$S/ffmpeg-$V" "$D"
( cd "$D" && FF_CFG . ./configure >/dev/null 2>&1 && make -j16 >/dev/null 2>&1 )
gcc -O2 -w -I"$D" "$HERE/test_ffmpeg.c" $(for l in $LIBS; do echo "$D/$l"; done) -lm -lpthread -lz -o "$B/native-test"
echo "[ffmpeg $V] native ok: avcodec.a $(stat -c %s "$D/libavcodec/libavcodec.a")B"

# ---------- wasm32 / wasm64 ----------
for A in wasm32 wasm64; do
  echo "[ffmpeg $V] $A configure+make (emcc)"
  D="$ROOT/work/tmp/ffmpeg-$V-$A"
  rm -rf "$D"; mkdir -p "$(dirname "$D")"; cp -a "$S/ffmpeg-$V" "$D"
  (
    cd "$D"
    FF_CFG . emconfigure ./configure --cc=emcc --cxx=em++ --ar=emar --ranlib=emranlib --nm=llvm-nm --strip=llvm-strip >/dev/null 2>&1
    # -sMEMORY64=1 は configure の try-compile を壊すため config.mak の CFLAGS に直接注入する
    if [ "$A" = wasm64 ]; then sed -i 's|^CFLAGS=   -std=c11|CFLAGS=   -sMEMORY64=1 -std=c11|' ffbuild/config.mak; fi
    find . -name '*.o' -delete; find . -name '*.a' -delete
    emmake make -j8 >/dev/null 2>&1
  )
  MEM64=""; [ "$A" = wasm64 ] && MEM64="-sMEMORY64=1"
  emcc -O2 -w $MEM64 -I"$D" -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 \
      "$HERE/test_ffmpeg.c" $(for l in $LIBS; do echo "$D/$l"; done) -lm -lpthread -o "$B/$A.cjs"
  echo "[ffmpeg $V] $A ok: wasm $(stat -c %s "$B/$A.wasm")B"
done

# ---------- 入力生成 + 3 arch で復号 ----------
python3 - "$B" <<'PY'
import sys, wave, struct
B = sys.argv[1]
# libm 非依存 PCM (libFLAC/libogg/LAME 検証と同一生成器: 移植しても native/wasm で同値)
x1=0.037; x2=-0.021; yl=0.0; yr=0.013; s=88172645463325252
frames=11025; buf=bytearray()
for i in range(frames):
    s ^= (s<<13)&0xFFFFFFFFFFFFFFFF; s ^= s>>7; s ^= (s<<17)&0xFFFFFFFFFFFFFFFF
    xn=((s>>40)/16777216.0)*2.0-1.0
    yl=0.9821*yl-0.0179*x1+0.0007*x2+xn*0.31
    yr=0.9821*yr-0.0179*x2+0.0007*x1+xn*0.29
    x2=x1; x1=xn
    vl=max(-1.0,min(1.0,yl*0.5)); vr=max(-1.0,min(1.0,yr*0.5))
    buf+=struct.pack('<hh', int(vl*32000), int(vr*32000))
with wave.open(f"{B}/gen.wav",'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(bytes(buf))
print(f"[ffmpeg] gen.wav {len(buf)}B PCM written")
PY
FILES="$B/gen.wav"
for f in "$ROOT/work/build/flac/negctl/ok.flac" "$ROOT/work/build/ogg/enc_native.ogg" "$ROOT/work/build/lame/native/out.mp3"; do
  [ -s "$f" ] && FILES="$FILES $f"
done
echo "[ffmpeg] inputs: $(echo $FILES | wc -w) files"

"$B/native-test" $FILES 2>/dev/null > "$B/native.txt"
node "$B/wasm32.cjs" $FILES 2>/dev/null > "$B/wasm32.txt"
node "$B/wasm64.cjs" $FILES 2>/dev/null > "$B/wasm64.txt"

echo
echo "=== 突合 (native == wasm32 == wasm64): DECODE 行の pcm_hash 一致 ==="
RC=0
for A in wasm32 wasm64; do
  if diff -q "$B/native.txt" "$B/$A.txt" >/dev/null; then
    echo "[ffmpeg $V] PASS $A: decode hash identical to native"
  else
    echo "[ffmpeg $V] FAIL $A:"; diff "$B/native.txt" "$B/$A.txt"; RC=1
  fi
done
echo "[ffmpeg $V] native output:"; sed 's/^/    /' "$B/native.txt"
echo
echo "[ffmpeg $V] ライセンス: $(grep -m1 'Version' "$B/native-src/config.h" >/dev/null && grep -m1 CONFIG_VERSION3 "$B/native-src/config.h")"
exit $RC
