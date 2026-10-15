#!/usr/bin/env bash
# fle_data_gen_cmp.sh — fle_data_gen.py の shift 対応 (196f37ef) で FLEngine の敷設出力が不変なことを確認する (#850 / KH-19d §5)。
#   usage: OUT=<repo 外の出力先> bash scripts/fle_data_gen_cmp.sh <block00031_PE.bin> [旧版の commit (既定 196f37ef^)]
#   素材: fl-win64.tar.zst から `tar --zstd -xf ${ARTIFACTS_DIR}/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` で取り出す。
#   検査: 旧版 (shift 引数なし) と新版 (既定 shift 0) の出力が cmp で一致すること。
#         ネガティブコントロール: 新版に shift 0x17E000000 を与えると出力が変わること (cmp が差を検出できること)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../../.." && pwd)"
PE="${1:?FLEngine の PE (block00031_PE.bin) のパスを第 1 引数で指定}"
OLD="${2:-196f37ef^}"
OUT="${OUT:?出力先を OUT で指定 (repo 外)}"
mkdir -p "$OUT"
echo '{}' > "$OUT/meta.json"
git -C "$REPO" show "$OLD:tools/flelift/fle_data_gen.py" > "$OUT/fle_data_gen_old.py"
python3 "$OUT/fle_data_gen_old.py" "$PE" "$OUT/old.c" "$OUT/meta.json" > /dev/null
python3 "$REPO/tools/flelift/fle_data_gen.py" "$PE" "$OUT/new.c" "$OUT/meta.json" > /dev/null
python3 "$REPO/tools/flelift/fle_data_gen.py" "$PE" "$OUT/neg.c" "$OUT/meta.json" 0x17E000000 > /dev/null
if cmp -s "$OUT/old.c" "$OUT/new.c"; then
  echo "cmp old/new: 一致 ($(wc -c < "$OUT/new.c") B)"
else
  echo "cmp old/new: 不一致" >&2
  exit 1
fi
NEG_DIFF=$(cmp -l "$OUT/old.c" "$OUT/neg.c" 2>/dev/null | wc -l || true)
if [ "$NEG_DIFF" -gt 0 ]; then
  echo "neg (shift 0x17E000000): 差分 ${NEG_DIFF} byte (期待どおり検出)"
else
  echo "neg (shift 0x17E000000): 差分 0 (cmp の検出力が無い)" >&2
  exit 1
fi
