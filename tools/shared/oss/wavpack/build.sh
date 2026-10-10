#!/usr/bin/env bash
# WavPack 4.80.0 (wavpack_x64.dylib 実測) / 4.60.1 (wavpack_x64.dll 実測) を upstream から
# native gcc / emscripten wasm32 / wasm64 で再ビルドし、同一 test_wavpack.c の WV エンコード・
# 復号結果を突合する。 usage: bash oss/wavpack/build.sh [4.80.0|4.60.1|both]
#
# 注意:
#  - 4.80.0 / 4.60.1 は github tag archive (release asset は存在しない) から取得
#  - WavpackOpenFileOutput は WavpackBlockOutput (メモリコールバック) なので
#    FILE* を介さず native/wasm で同一バイト列が出る (読み側だけ WavpackOpenFileInput)
#  - WavpackOpenFileInput は CLI の open_filename.c 経由で fopen するため wasm では
#    NODERAWFS を有効にしてパスを渡す
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
S="$ROOT/work/src"; B="$ROOT/work/build/wavpack"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
CF="-O2 -ffp-contract=off -w"
rm -rf "$B"; mkdir -p "$B"
[ -d "$S/WavPack-4.80.0" ] || bash "$ROOT/oss/fetch_sources.sh"

for V in 4.80.0 4.60.1; do
  D="$S/WavPack-$V"
  [ -d "$D" ] || continue
  INC="-I$D/include"
  SRCS=$(find "$D/src" -name "*.c" | sort)
  NSRC=$(echo $SRCS | wc -w)
  for A in native wasm32 wasm64; do
    O="$B/$V-$A"; mkdir -p "$O"
    echo "[wavpack $V] $A: $NSRC sources"
    case "$A" in
      native)
        gcc $CF $INC -DPACKAGE_VERSION="\"$V\"" -o "$O/test" "$HERE/test_wavpack.c" $SRCS -lm
        ( cd "$O" && ./test "$O/out.wv" > "$O/out.txt" )
        echo "[wavpack $V] native ok, $(stat -c %s "$O/test")B" ;;
      wasm32)
        emcc $CF $INC -DPACKAGE_VERSION="\"$V\"" -sENVIRONMENT=node -sNODERAWFS=1 \
          -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 -o "$O/test.cjs" "$HERE/test_wavpack.c" $SRCS -lm
        node "$O/test.cjs" "$O/out.wv" > "$O/out.txt"
        echo "[wavpack $V] wasm32 ok, wasm $(stat -c %s "$O/test.wasm")B" ;;
      wasm64)
        emcc $CF -sMEMORY64=1 $INC -DPACKAGE_VERSION="\"$V\"" -sENVIRONMENT=node -sNODERAWFS=1 \
          -sALLOW_MEMORY_GROWTH=1 -sEXIT_RUNTIME=1 -o "$O/test.cjs" "$HERE/test_wavpack.c" $SRCS -lm 2>&1 | grep -v deprecated || true
        node "$O/test.cjs" "$O/out.wv" > "$O/out.txt"
        echo "[wavpack $V] wasm64 ok, wasm $(stat -c %s "$O/test.wasm")B" ;;
    esac
  done
done

echo
echo "=== 突合 (各 version で native == wasm32 == wasm64) ==="
RC=0
sel() { grep -E "^PCM |^WV |^WV version|^DECODED |^WM identical" "$1"; }
for V in 4.80.0 4.60.1; do
  [ -d "$B/$V-native" ] || continue
  for A in wasm32 wasm64; do
    if diff -q <(sel "$B/$V-native/out.txt") <(sel "$B/$V-$A/out.txt") >/dev/null; then
      echo "[wavpack $V] PASS $A: identical to native"
    else
      echo "[wavpack $V] FAIL $A:"; diff <(sel "$B/$V-native/out.txt") <(sel "$B/$V-$A/out.txt"); RC=1
    fi
  done
  # エンコードした .wv のバイト一致 (native vs wasm)
  python3 - "$B" "$V" <<'PY'
import sys, hashlib
B, V = sys.argv[1], sys.argv[2]
def h(p):
    try: return hashlib.sha256(open(p,'rb').read()).hexdigest()[:16]
    except FileNotFoundError: return "MISSING"
n = h(f"{B}/{V}-native/out.wv")
for a in ("wasm32","wasm64"):
    w = h(f"{B}/{V}-{a}/out.wv")
    print(f"[wavpack {V}] .wv sha256[:16] {a}={'==' if w==n else '!='} native ({n} vs {w})")
PY
  echo "[wavpack $V] native output:"; sel "$B/$V-native/out.txt" | sed 's/^/    /'
done
exit $RC
