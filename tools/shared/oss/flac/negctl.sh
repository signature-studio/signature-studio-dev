#!/usr/bin/env bash
# Negative control (規則 41): libFLAC 検証の合否判定が実際にバイト列を見ていることを確認する。
#   1) 正常 FLAC -> 復号 hash 一致 (PASS 条件の再確認)
#   2) 音声フレームの 1 バイトを反転 -> 復号 PCM の hash が不一致 or エラー (FAIL)
#   3) 先頭 magic "fLaC" を破壊 -> 復号がエラー終了 (FAIL)
# usage: bash oss/flac/negctl.sh [ver]   (事前に bash oss/flac/build.sh)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
B="$ROOT/work/build/flac"
V=${1:-1.5.0}
T="$B/$V-native/test"
[ -x "$T" ] || { echo "[neg] 先に bash oss/flac/build.sh を実行"; exit 2; }
W="$B/negctl"; mkdir -p "$W"; cd "$W"
echo "=== negative control (libFLAC $V) ==="
$T "$W/ok.flac" > "$W/ok.txt" 2>&1; rc_ok=$?
echo "[neg] baseline (そのまま復号) rc=$rc_ok"
grep -E "PCM identical" "$W/ok.txt"

mut() { # in out mode
  python3 - "$1" "$2" "$3" <<'PY'
import sys
pin, pout, mode = sys.argv[1], sys.argv[2], sys.argv[3]
d = bytearray(open(pin,'rb').read())
if mode == 'flip_frame':
    i = d.find(b'\xff\xf8')            # FLAC frame sync を探す
    if i < 0: i = 200
    d[i + 200] ^= 0xff                 # 音声フレーム中の 1 バイト反転
elif mode == 'bad_magic':
    d[0:4] = b'XXXX'                   # "fLaC" 破壊
open(pout,'wb').write(bytes(d))
PY
}
rc_of() { "$@" >/dev/null 2>&1; echo $?; }
base_hash=$(grep "^DECODED" "$W/ok.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
base_id=$(grep "^DECODED" "$W/ok.txt" | sed -E 's/.*frames=([0-9]+).*/\1/')
BAD=0
for mode in flip_frame bad_magic; do
  mut "$W/ok.flac" "$W/bad-$mode.flac" "$mode"
  "$T" -d "$W/bad-$mode.flac" > "$W/bad-$mode.txt" 2>&1 || true
  rc=$(rc_of "$T" -d "$W/bad-$mode.flac")
  new_hash=$(grep "^DECODED" "$W/bad-$mode.txt" | sed -E 's/.*hash=([0-9a-f]+).*/\1/')
  if [ "$rc" != 0 ] || [ "$new_hash" != "$base_hash" ]; then
    echo "[neg] CAUGHT $mode: rc=$rc decoded_hash=$new_hash != baseline $base_hash"
  else
    echo "[neg] MISSED $mode: rc=0 and hash unchanged"; BAD=1
  fi
done
exit $BAD
