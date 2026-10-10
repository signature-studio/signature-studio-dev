#!/usr/bin/env bash
# libFLAC を upstream ソースから native gcc / emscripten wasm32 / wasm64 で再ビルドし、
# 同一 test_flac.c (PCM 生成 -> FLAC エンコード -> 復号) の出力を突合する。
# version 1.5.0 (EasyFLAC mac 実測) / 1.3.1 (oggio win 実測) の 2 本を検証する。
#   usage: bash oss/flac/build.sh
# 注意:
#  - autotools の emscripten cross 判定は使わず、ソース一覧を直接 emcc に渡す (libogg PoC 同手法)。
#    config.h は native configure が 1 度生成したものを -DHAVE_CONFIG_H で共有する
#    (これを省くと compat.h が fseeko->fseek に define して emscripten stdio と衝突する)。
#  - FLAC__stream_encoder_init_FILE / init_FILE (FILE* 直結) を使うと seek/tell は
#    libFLAC 内部の file_*_callback_ で解決され native/wasm で同一バイト列になる。
#  - x86 専用 intrin (sse/ssse3/sse41/avx2/fma 等) と neon・deduplication は wasm に
#    存在しない命令を含むため除外 (将来 -msimd128 化は別タスク)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
S="$ROOT/work/src"; B="$ROOT/work/build/flac"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
CF="-O2 -ffp-contract=off -w"

configure_make() { # ver
  local V="$1" D="$S/flac-$1"
  echo "[flac $V] native configure+make (config.h 生成)"
  ( cd "$D" && ./configure --disable-ogg --disable-asm-optimizations --disable-doxygen-docs \
      --disable-examples --disable-xmms-plugin --disable-cpplibs --disable-shared --enable-static \
      --build=x86_64-pc-linux-gnu >/dev/null 2>&1 && make -j16 >/dev/null 2>&1 )
  # wasm 用 config.h: x86 専用ヘッダ (cpuid.h / sys/auxv.h) の define を落として
  # cpu.c の x86 分岐自体を無効化する (native 生成 config.h をそのまま使うと
  # emcc の sysroot に存在しないヘッダを include して失敗する)
  sed -e 's|^#define HAVE_CPUID_H 1|/* wasm: no cpuid.h */|' \
      -e 's|^#define HAVE_SYS_AUXV_H 1|/* wasm: no sys/auxv.h */|' \
      -e 's|^#define FLAC__HAS_X86INTRIN.*|/* wasm: no x86 intrinsics */|' \
      "$D/config.h" > "$B/flac-$V-wasm-config.h"
}
[ -d "$S/flac-1.5.0" ] || bash "$ROOT/oss/fetch_sources.sh"
mkdir -p "$B"
configure_make 1.5.0
configure_make 1.3.1
rm -rf "$B/flac-build-tmp"; mkdir -p "$B/flac-build-tmp"
# wasm config.h を -I の先頭に置く (include "config.h" は引用順でカレント dir より -I が優先)
CFGDIR="$B/flac-build-tmp"
cp "$B/flac-1.5.0-wasm-config.h" "$CFGDIR/config.h"
cp "$B/flac-1.3.1-wasm-config.h" "$CFGDIR/config_131.h"

srcs() { # ver -> ソース一覧 (wasm 非対応 intrin 除外)
  find "$S/flac-$1/src/libFLAC" -name "*.c" | grep -v -E "ia32|_intrin_|deduplication|lpc_intrin_neon|ogg_" | sort
}

for V in 1.5.0 1.3.1; do
  D="$S/flac-$V"
  # wasm は CFGDIR を -I 先頭に置き、x86 専用ヘッダ define を落とした config.h を使う。
  # native は素の $D/config.h (HAVE_CPUID_H 等あり) を使う。
  INC_N="-I$D/include -I$D -I$D/src/libFLAC/include -DHAVE_CONFIG_H"
  INC_W="-I$CFGDIR -I$D/include -I$D -I$D/src/libFLAC/include -DHAVE_CONFIG_H"
  SRC=$(srcs "$V"); NSRC=$(echo $SRC | wc -w)
  for A in native wasm32 wasm64; do
    O="$B/$V-$A"; mkdir -p "$O"
    if [ "$A" = native ]; then INC="$INC_N"; else INC="$INC_W"; fi
    # 1.3.1 の config.h は別ファイル (CFGDIR/config_131.h) なので version 別に退避
    if [ "$A" != native ]; then
      cp "$B/flac-$V-wasm-config.h" "$CFGDIR/config.h"
    fi
    case "$A" in
      native)
        gcc $CF $INC -DPACKAGE_VERSION="\"$V\"" -o "$O/test" "$HERE/test_flac.c" $SRC -lm
        "$O/test" > "$O/out.txt"
        echo "[flac $V] native: $NSRC sources, $(stat -c %s "$O/test")B" ;;
      wasm32)
        emcc $CF $INC -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 \
          -DPACKAGE_VERSION="\"$V\"" -o "$O/test.cjs" "$HERE/test_flac.c" $SRC -lm
        node "$O/test.cjs" > "$O/out.txt"
        echo "[flac $V] wasm32: $NSRC sources, wasm $(stat -c %s "$O/test.wasm")B" ;;
      wasm64)
        emcc $CF -sMEMORY64=1 $INC -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 \
          -DPACKAGE_VERSION="\"$V\"" -o "$O/test.cjs" "$HERE/test_flac.c" $SRC -lm 2>&1 | grep -v deprecated || true
        node "$O/test.cjs" > "$O/out.txt"
        echo "[flac $V] wasm64: $NSRC sources, wasm $(stat -c %s "$O/test.wasm")B" ;;
    esac
  done
done

echo
echo "=== 突合 (native == wasm32 == wasm64): FILE bytes/hash・DECODED hash・PCM identical ==="
RC=0
sel() { grep -E "^FILE |^DECODED |^PCM identical" "$1"; }
for V in 1.5.0 1.3.1; do
  for A in wasm32 wasm64; do
    if diff -q <(sel "$B/$V-native/out.txt") <(sel "$B/$V-$A/out.txt") >/dev/null; then
      echo "[flac $V] PASS $A: identical to native"
    else
      echo "[flac $V] FAIL $A:"; diff <(sel "$B/$V-native/out.txt") <(sel "$B/$V-$A/out.txt"); RC=1
    fi
  done
  echo "[flac $V] native output:"; sed 's/^/    /' "$B/$V-native/out.txt"
done
exit $RC
