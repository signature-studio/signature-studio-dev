#!/usr/bin/env bash
# measure_flengine_split.sh — #229: FLEngine 巨大 2 関数 (0xc589b0 / 0x128f9e0) の
# RetDec 範囲分割 lift で 366 site 落ちが変わるかの before/after 実測。
#   usage: FL_WIN64_DIR=<fl-win64 展開先>/extracted bash measure_flengine_split.sh [OUTDIR]
# 出力: OUTDIR/{base,c2}/audit_after.txt (CHUNKS=1 / CHUNKS=2 の roundtrip 結果)
#       OUTDIR/passes_stub.txt (RetDec --print-after-all の段ごとの stub 呼出し数)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
: "${FL_WIN64_DIR:?FL_WIN64_DIR を設定 (fl-win64 の extracted)}"
OUT="${1:-${TMPDIR:-/tmp}/flengine_split}"
PE="$FL_WIN64_DIR/block00031_PE.bin"
mkdir -p "$OUT"
printf '0xc589b0\n0x128f9e0\n' > "$OUT/F.txt"

# (1) 1 chunk / (2) 2 chunk: 既存 roundtrip.sh をそのまま使う
CHUNKS=1 bash "$HERE/roundtrip.sh" "$PE" "$OUT/F.txt" fle_base "$OUT/base"
CHUNKS=2 bash "$HERE/roundtrip.sh" "$PE" "$OUT/F.txt" fle_c2 "$OUT/c2"

# (3) 段ごとの stub 呼出し数 (after 側 rw.dll を RetDec に通す)
python3 "$HERE/passes_stub_count.py" "$OUT/base/rw.dll" "$OUT/base/after.ranges" "$OUT/passes_stub.txt"

echo "== base (CHUNKS=1) lost:"; grep "=> lost" "$OUT/base/audit_after.txt"
echo "== c2   (CHUNKS=2) lost:"; grep "=> lost" "$OUT/c2/audit_after.txt"
