#!/usr/bin/env bash
# libFLAC 1.5.0 (upstream ソース) -> flacdec.wasm (wasm32, memory->memory 復号 + MD5 検証)。
#   bash tools/assets/serum2/flac/build.sh     出力: tools/assets/serum2/work/flacdec.wasm + flacdec.build.json
# 前提: emcc (EMSDK 環境済み or $EMSDK_ENV を source)。ソースは tools/shared/oss/flac/build.sh と同じ upstream tarball
# (sha256 は tools/legal/notices/records/flac-1.5.0.json と一致を検査する)。config.h は native configure 生成物から
# x86 専用ヘッダの define だけ落とす (tools/shared/oss/flac/build.sh と同手法)。x86 intrin / neon は wasm に無いので除外。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="$HERE/../work"; mkdir -p "$W/src"
[ -n "${EMSDK_ENV:-}" ] && source "$EMSDK_ENV" >/dev/null 2>&1
command -v emcc >/dev/null || { echo "[flac] emcc が無い (EMSDK_ENV=<emsdk_env.sh> を指定)"; exit 2; }
V=1.5.0
SHA=f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920
T="$W/src/flac-$V.tar.xz"
[ -s "$T" ] || curl -fsSL --retry 3 -o "$T" "https://downloads.xiph.org/releases/flac/flac-$V.tar.xz"
echo "$SHA  $T" | sha256sum -c - >/dev/null || { echo "[flac] upstream sha256 不一致"; exit 3; }
D="$W/src/flac-$V"
[ -d "$D" ] || tar -C "$W/src" -xJf "$T"
if [ ! -f "$D/config.h" ]; then
  ( cd "$D" && ./configure --disable-ogg --disable-asm-optimizations --disable-doxygen-docs --disable-examples \
      --disable-xmms-plugin --disable-cpplibs --disable-shared --enable-static >/dev/null 2>&1 )
fi
CF="$W/cfg"; mkdir -p "$CF"
sed -e 's|^#define HAVE_CPUID_H 1|/* wasm: no cpuid.h */|' -e 's|^#define HAVE_SYS_AUXV_H 1|/* wasm: no sys/auxv.h */|' \
    -e 's|^#define FLAC__HAS_X86INTRIN.*|/* wasm: no x86 intrinsics */|' "$D/config.h" > "$CF/config.h"
SRC=$(find "$D/src/libFLAC" -name '*.c' | grep -v -E 'ia32|_intrin_|deduplication|lpc_intrin_neon|ogg_' | sort)
NSRC=$(echo "$SRC" | wc -w)
emcc -O2 -ffp-contract=off -w -DHAVE_CONFIG_H -DFLAC__NO_DLL -I"$CF" -I"$D/include" -I"$D" -I"$D/src/libFLAC/include" \
  $SRC "$HERE/flacdec.c" -o "$W/flacdec.wasm" \
  -sSTANDALONE_WASM=1 --no-entry -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=33554432 -sMAXIMUM_MEMORY=2147483648 \
  -sEXPORTED_FUNCTIONS=_malloc,_free,_fd_decode,_fd_pcm,_fd_pcm_samples,_fd_rate,_fd_channels,_fd_bps,_fd_total_lo,_fd_total_hi,_fd_has_md5,_fd_md5
printf '{"libflac":"%s","upstream_sha256":"%s","emcc":"%s","libflac_sources":%s,"wasm_bytes":%s,"wasm_sha256":"%s"}\n' \
  "$V" "$SHA" "$(emcc --version | head -1 | sed 's/"//g')" "$NSRC" "$(stat -c %s "$W/flacdec.wasm")" "$(sha256sum "$W/flacdec.wasm" | cut -d' ' -f1)" \
  > "$W/flacdec.build.json"
cat "$W/flacdec.build.json"
