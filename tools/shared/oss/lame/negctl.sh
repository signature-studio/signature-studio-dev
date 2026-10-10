#!/usr/bin/env bash
# Negative control (規則 41) for LAME: 合否判定 (MP3 バイト列の hash 一致) が実際に
# エンコーダの内容を見ていることを確認する。
#   1) 同一 PCM を 2 回エンコード -> 同一 MP3 (determinism / 再現性の確認)
#   2) 別 seed の同一生成器 PCM -> MP3 が変わる (差分検出)
# usage: bash oss/lame/negctl.sh  (事前に bash oss/lame/build.sh)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
B="$ROOT/work/build/lame"; L="$ROOT/work/src/lame-3.99.5"
T="$B/native/test"
[ -x "$T" ] || { echo "[neg] 先に bash oss/lame/build.sh を実行"; exit 2; }
W="$B/negctl"; mkdir -p "$W"; cd "$W"
echo "=== negative control (LAME 3.99.5) ==="
$T "$W/a.mp3" > "$W/a.txt"; $T "$W/b.mp3" > "$W/b.txt"
ha=$(grep "^FILE" "$W/a.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
hb=$(grep "^FILE" "$W/b.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
hp=$(grep "^PCM"  "$W/a.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
if [ "$ha" = "$hb" ]; then
  echo "[neg] OK deterministic: 同一 PCM (hash=$hp) から同一 MP3 (hash=$ha)"
else
  echo "[neg] FAIL non-deterministic: $ha vs $hb"; exit 1
fi
# seed を変えた別 PCM を同じハーネスで食わせ、MP3 が変わることを確認
sed -e 's|88172645463325252ULL|12345678901234567890ULL|' "$HERE/test_lame.c" > "$W/test_variant.c"
gcc -O2 -ffp-contract=off -w -include "$L/config.h" -I"$L/include" -I"$L/libmp3lame" -I"$L" \
    "$W/test_variant.c" $(find "$L/libmp3lame" -name "*.c" | grep -v -E "i386|vector|logo" | sort) \
    "$L/libmp3lame/vector/xmm_quantize_sub.c" -lm -o "$W/test_variant"
"$W/test_variant" "$W/c.mp3" > "$W/c.txt"
hc=$(grep "^FILE" "$W/c.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
hcp=$(grep "^PCM" "$W/c.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
if [ "$hc" != "$ha" ]; then
  echo "[neg] CAUGHT 別 seed PCM: PCM hash=$hcp -> MP3 hash=$hc != baseline $ha"
  exit 0
else
  echo "[neg] MISSED 別 seed PCM で同一 MP3 (hash=$hc)"; exit 1
fi
