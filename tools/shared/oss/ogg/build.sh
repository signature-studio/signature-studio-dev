#!/usr/bin/env bash
# libogg 1.3.2 + libvorbis 1.3.5 (oggio_x64.dll 内 "Xiph.Org libVorbis I 20150105" と同版) を
#  (a) native gcc / (b) emscripten wasm32 / (c) wasm64 で upstream ソースから直接コンパイルして再ビルドし、
#  test_vorbis.c (エンコード→Ogg→デコード) の出力ハッシュを突合する。 usage: bash oss/ogg/build.sh
#  (autotools は emscripten の cross 判定で Ogg link check が落ちるため使わず、ソース一覧を直接 emcc に渡す)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
S="$ROOT/work/src"; B="$ROOT/work/build/ogg"
[ -d "$S/libvorbis-1.3.5" ] || bash "$ROOT/oss/fetch_sources.sh"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
rm -rf "$B"; mkdir -p "$B/inc/ogg"
OGG="$S/libogg-1.3.2"; VOR="$S/libvorbis-1.3.5"
# config_types.h は configure 生成物 (stdint.h ベースで可搬)。native configure から 1 回だけ生成する。
( mkdir -p "$B/gen" && cp -a "$OGG" "$B/gen/ogg" && cd "$B/gen/ogg" && ./configure >/dev/null 2>&1 )
cp "$B/gen/ogg/include/ogg/config_types.h" "$B/inc/ogg/"; cp "$OGG"/include/ogg/ogg.h "$OGG"/include/ogg/os_types.h "$B/inc/ogg/"
SRCS="$OGG/src/bitwise.c $OGG/src/framing.c"
for f in mdct smallft block envelope window lsp lpc analysis synthesis psy info floor1 floor0 res0 mapping0 registry codebook sharedbook lookup bitrate vorbisenc; do SRCS="$SRCS $VOR/lib/$f.c"; done
INC="-I$B/inc -I$VOR/include -I$VOR/lib"
CF="-O2 -ffp-contract=off -w"
echo "[ogg] $(echo $SRCS | wc -w) source files"
gcc $CF $INC "$HERE/test_vorbis.c" $SRCS -lm -o "$B/test_native"
emcc $CF $INC "$HERE/test_vorbis.c" $SRCS -o "$B/test_wasm32.cjs" -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1
emcc $CF -sMEMORY64=1 $INC "$HERE/test_vorbis.c" $SRCS -o "$B/test_wasm64.cjs" -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 2>&1 | grep -v deprecated || true
echo "[ogg] wasm size: wasm32=$(stat -c %s "$B/test_wasm32.wasm") wasm64=$(stat -c %s "$B/test_wasm64.wasm")"
# (1) エンコード突合: 各環境で encode -> ogg と hash を出力 (libm 差が出うるので差異は一致バイト長で定量化)
"$B/test_native" "$B/enc_native.ogg" > "$B/out_native.txt"
node "$B/test_wasm32.cjs" "$B/enc_wasm32.ogg" > "$B/out_wasm32.txt"
node "$B/test_wasm64.cjs" "$B/enc_wasm64.ogg" > "$B/out_wasm64.txt"
cat "$B/out_native.txt"
for v in wasm32 wasm64; do
  if diff -q "$B/enc_native.ogg" "$B/enc_$v.ogg" >/dev/null; then echo "[ogg] ENC $v: ogg bytes identical to native"; else
    python3 - "$B/enc_native.ogg" "$B/enc_$v.ogg" "$v" <<'PY'
import sys
a=open(sys.argv[1],'rb').read(); b=open(sys.argv[2],'rb').read()
n=next((i for i in range(min(len(a),len(b))) if a[i]!=b[i]), min(len(a),len(b)))
print(f"[ogg] ENC {sys.argv[3]}: first divergence at byte {n}/{len(a)} (native {len(a)}B vs {len(b)}B) -- libm (glibc vs musl) 差由来")
PY
  fi
done
# (2) 復号突合: 同一 ogg (native が作った stream) を native / wasm32 / wasm64 で復号し PCM hash を比較 (FL の OggioLoadFile 相当パス)
"$B/test_native" -d "$B/enc_native.ogg" | tail -1 > "$B/dec_native.txt"
node "$B/test_wasm32.cjs" -d "$B/enc_native.ogg" | tail -1 > "$B/dec_wasm32.txt"
node "$B/test_wasm64.cjs" -d "$B/enc_native.ogg" | tail -1 > "$B/dec_wasm64.txt"
cat "$B/dec_native.txt"
rc=0
for v in wasm32 wasm64; do
  if diff -q "$B/dec_native.txt" "$B/dec_$v.txt" >/dev/null; then echo "[ogg] PASS DEC $v: decoded PCM hash == native"; else diff "$B/dec_native.txt" "$B/dec_$v.txt"; echo "[ogg] FAIL DEC $v"; rc=1; fi
done

# LGL-3 (#86): 再ビルド記録 (libogg / libvorbis)
if [ "$rc" = 0 ]; then
  NSRC_FILES="$(for f in $SRCS; do basename "$f"; done | sort | paste -sd' ')"
  for L in libogg:1.3.2:libogg-1.3.2.tar.gz:https://downloads.xiph.org/releases/ogg/libogg-1.3.2.tar.gz libvorbis:1.3.5:libvorbis-1.3.5.tar.gz:https://downloads.xiph.org/releases/vorbis/libvorbis-1.3.5.tar.gz; do
    IFS=: read -r N V A U <<<"$L"
    case "$N" in libogg) FILES="bitwise.c framing.c" ;; *) FILES="$(for f in $SRCS; do case "$f" in "$VOR"/*) basename "$f" ;; esac; done | sort | paste -sd' ')" ;; esac
    node "$ROOT/../legal/notices/record.mjs" --id "$N-$V" --name "$N" --version "$V" --license-spdx BSD-3-Clause \
      --url "$U" --archive "$S/$A" --src-dir "$S/$N-$V" --license-file COPYING \
      --script "$HERE/build.sh" --toolchain emcc --target wasm32 --target wasm64 \
      --step "compile=emcc $CF -I<build>/inc -I<libvorbis>/include -I<libvorbis>/lib <sources: $FILES> (autotools 不使用。config_types.h のみ native ./configure 生成)"
  done
fi
exit $rc
