#!/bin/bash
# PLG-F3-30 (#2493): 0x867100 を構築するアリーナ初期化関数を、unicorn の書込み元 rip で特定する。
# 使い方: bash tools/plugins/f2/write_origin_2493.sh <block19148_PE.bin> [出力先 (既定 $RUNNER_TEMP/2493)]
# 依存: pefile・unicorn 2.1.4・capstone (REPORT_1305.md §11 の venv)。出力は work 側に置き、リポジトリには書かない。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PE="${1:?usage: write_origin_2493.sh <block19148_PE.bin> [out_dir]}"
OUT="${2:-${RUNNER_TEMP:-/tmp}/2493}"
mkdir -p "$OUT"
UT="$HERE/unicorn_trace.py"
WO="$HERE/write_origin.py"

for i in 1 2 3; do
  python3 "$UT" "$PE" 0x409090 -H -q 0x867100 -w 0x867100:0x867200 -m 2000000 > "$OUT/w_409090_$i.txt"
done
md5sum "$OUT"/w_409090_*.txt
echo "== 0x409090 -w 0x867100:0x867200 (run 1)"
grep '^status' "$OUT/w_409090_1.txt"
python3 "$WO" "$PE" "$OUT/w_409090_1.txt"

echo "== negative: 0x409090 -w 0x867d00:0x867e00 (アリーナ末尾より上)"
python3 "$UT" "$PE" 0x409090 -H -q 0x867100 -w 0x867d00:0x867e00 -m 2000000 > "$OUT/neg_409090.txt"
python3 "$WO" "$PE" "$OUT/neg_409090.txt"

echo "== negative: full path 0x83efb0 -H -w 0x867100:0x867200 (アリーナを構築しない経路)"
python3 "$UT" "$PE" 0x83efb0 -H -w 0x867100:0x867200 -m 2000000 > "$OUT/full_83efb0.txt"
grep '^status\|^fault' "$OUT/full_83efb0.txt" || true
python3 "$WO" "$PE" "$OUT/full_83efb0.txt"
