#!/usr/bin/env bash
# Negative control (規則 41) for WavPack: 合否判定 (PCM の可逆 round-trip 一致) が
# 実際に符号化内容を見ていることを確認する。
#   1) 正常 round-trip -> PCM 完全一致 (baseline)
#   2) エンコード時に意図的に 1 つの sample を +1 ずらした入力 -> 復号 PCM が 1 サンプル差 (検出)
#   3) .wv の 1 バイト破損 -> 復号エラー or 差分 (検出)
# usage: bash oss/wavpack/negctl.sh [ver] (事前に bash oss/wavpack/build.sh)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
B="$ROOT/work/build/wavpack"
V=${1:-4.80.0}
T="$B/$V-native/test"
[ -x "$T" ] || { echo "[neg] 先に bash oss/wavpack/build.sh を実行"; exit 2; }
W="$B/negctl"; mkdir -p "$W"; cd "$W"
echo "=== negative control (WavPack $V) ==="
"$T" "$W/ok.wv" > "$W/ok.txt"
ok_hash=$(grep "^WM identical" "$W/ok.txt" | sed -E 's/^WM //')
echo "[neg] baseline: $ok_hash"
case "$ok_hash" in
  "identical 48000/48000 (reference frames=24000)") : ;;
  *) echo "[neg] baseline broken: $ok_hash"; exit 1 ;;
esac

# (2) 1 sample ずらした入力 -> 復号差分を検出
sed -e 's|pcm\[i\] = (int32_t)vl;|pcm[i] = (int32_t)(vl + 1);  /* negative control: shift 1 sample */|' \
    "$HERE/test_wavpack.c" > "$W/test_shift.c"
gcc -O2 -ffp-contract=off -w -I"$ROOT/work/src/WavPack-$V/include" "$W/test_shift.c" \
    $(find "$ROOT/work/src/WavPack-$V/src" -name "*.c" | sort) -lm -o "$W/test_shift"
"$W/test_shift" "$W/shift.wv" > "$W/shift.txt"
sh=$(grep "^WM identical" "$W/shift.txt" | sed -E 's/^WM //')
dh=$(grep "^DECODED" "$W/shift.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
dbh=$(grep "^DECODED" "$W/ok.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
echo "[neg] shift run: decoded_hash=$dh (baseline $dbh)"
if [ "$sh" != "$ok_hash" ] || [ "$dh" != "$dbh" ]; then
  echo "[neg] CAUGHT 入力 1 sample シフト: WM='$sh' decoded_hash=$dh (baseline '$ok_hash' / $dbh)"
else
  echo "[neg] MISSED 1 sample シフト"; exit 1
fi

# (3) .wv の 1 バイト破損
cp "$W/ok.wv" "$W/bad.wv"
python3 - "$W/bad.wv" <<'PY'
import sys
p = sys.argv[1]; d = bytearray(open(p,'rb').read())
d[5000] ^= 0xff                      # 音声ブロック中の 1 バイト反転
open(p,'wb').write(bytes(d))
PY
"$T" -d "$W/bad.wv" > "$W/bad.txt" || true
bh=$(grep "^WM identical" "$W/bad.txt")
eh=$(grep -c "^WV version" "$W/bad.txt")
if [ "$bh" != "$ok_hash" ] || [ "$eh" = 0 ]; then
  echo "[neg] CAUGHT .wv 1B 破損: ${bh:-open-failed}"
else
  echo "[neg] MISSED .wv 1B 破損 ($bh)"; exit 1
fi
exit 0
