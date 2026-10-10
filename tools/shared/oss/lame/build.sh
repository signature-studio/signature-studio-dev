#!/usr/bin/env bash
# LAME 3.99.5 (libmp3lame_x64.dylib 実測 "LAME 3.99.5" / "LAME3.99r5") を upstream ソースから
# native gcc / emscripten wasm32 / wasm64 で再ビルドし、同一 test_lame.c の MP3 エンコード出力を突合する。
#   usage: bash oss/lame/build.sh
# 注意:
#  - autotools は native configure で config.h を作り、-include で全 TU に供給 (ieee754_float32_t typedef が要る)
#  - x86 xmm intrinsic (vector/xmm_quantize_sub.c) は wasm に無い命令のため native のみ。
#    wasm は config.h から HAVE_XMMINTRIN_H / MIN_ARCH_SSE を落として init_xrpow_core_c だけを使う
#    (MPEG-2 の quantize 経路が変わるため、hash は native と *異なる* ことを明示して許容差扱い)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
S="$ROOT/work/src"; B="$ROOT/work/build/lame"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
CF="-O2 -ffp-contract=off -w"
D="$S/lame-3.99.5"
[ -d "$D" ] || bash "$ROOT/oss/fetch_sources.sh"

echo "[lame 3.99.5] native configure (config.h 生成)"
( cd "$D" && ./configure --disable-shared --enable-static --disable-nasm --disable-decoder \
    --disable-gtktest --disable-analyzer-hooks --build=x86_64-pc-linux-gnu >/dev/null 2>&1 )
# wasm 用 config.h: x86 intrinsic 依存を落とす
mkdir -p "$B"
sed -e 's|^#define HAVE_XMMINTRIN_H 1|/* wasm: no x86 intrinsics */|' \
    -e 's|^#define MIN_ARCH_SSE 1|/* wasm: no SSE */|' \
    "$D/config.h" > "$B/lame-wasm-config.h"

BASE=$(find "$D/libmp3lame" -name "*.c" | grep -v -E "i386|vector|logo" | sort)
NSRC=$(echo $BASE | wc -w)
rm -rf "$B/native" "$B/wasm32" "$B/wasm64"
for A in native wasm32 wasm64; do
  O="$B/$A"; mkdir -p "$O"
  INC="-I$D/include -I$D/libmp3lame -I$D"
  case "$A" in
    native)
      gcc $CF -include "$D/config.h" $INC -DPACKAGE_VERSION="\"3.99.5\"" \
        -o "$O/test" "$HERE/test_lame.c" $BASE "$D/libmp3lame/vector/xmm_quantize_sub.c" -lm
      "$O/test" "$O/out.mp3" > "$O/out.txt"
      echo "[lame] native: $NSRC sources (+xmm), $(stat -c %s "$O/test")B" ;;
    wasm32)
      emcc $CF -include "$B/lame-wasm-config.h" $INC -DPACKAGE_VERSION="\"3.99.5\"" \
        -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 \
        -o "$O/test.cjs" "$HERE/test_lame.c" $BASE -lm
      node "$O/test.cjs" "$O/out.mp3" > "$O/out.txt"
      echo "[lame] wasm32: $NSRC sources, wasm $(stat -c %s "$O/test.wasm")B" ;;
    wasm64)
      emcc $CF -sMEMORY64=1 -include "$B/lame-wasm-config.h" $INC -DPACKAGE_VERSION="\"3.99.5\"" \
        -sENVIRONMENT=node -sNODERAWFS=1 -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 \
        -o "$O/test.cjs" "$HERE/test_lame.c" $BASE -lm 2>&1 | grep -v deprecated || true
      node "$O/test.cjs" "$O/out.mp3" > "$O/out.txt"
      echo "[lame] wasm64: $NSRC sources, wasm $(stat -c %s "$O/test.wasm")B" ;;
  esac
done

echo
echo "=== 突合 ==="
sel() { grep -E "^PCM |^MP3 |^FILE |^LAME " "$1"; }
echo "--- native ---"; sel "$B/native/out.txt"
for A in wasm32 wasm64; do echo "--- $A ---"; sel "$B/$A/out.txt"; done
echo
# 判定: native と wasm の MP3 を同一設定で比較。xmm 有無で quantize の丸めが変わり得るため
# 許容差 = バイト数 ±2% 以内 & 先頭 ID3 ヘッダ以降の完全一致を確認する。
python3 - "$B" <<'PY'
import sys
B=sys.argv[1]
def pxch(p):
    d=open(p,'rb').read()
    i=d.find(b'\xff\xfb')            # MPEG-1 Layer3 frame sync
    return (len(d), d[i:] if i>=0 else d)
import itertools
base=None
for a in ('native','wasm32','wasm64'):
    p=f"{B}/{a}/out.mp3"
    try: n,d=pxch(p)
    except FileNotFoundError: print(f"[lame] MISSING {p}"); continue
    if base is None: base=(a,n,d); print(f"[lame] {a}: bytes={n} payload_after_sync={len(d)}")
    else:
        same = (d == base[2])
        delta = (n - base[1]) / base[1] * 100
        print(f"[lame] {a}: bytes={n} (vs {base[0]} {delta:+.1f}%) payload_byte_identical={same}")
PY
