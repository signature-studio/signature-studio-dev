#!/usr/bin/env bash
# fl-win64 の展開済み PE (extracted/*_PE.bin) から FreeType 呼出元の候補を洗う (#1144)。
# usage: bash oss/freetype/callers_scan.sh <extracted_dir>
#   extracted_dir は `tar --zstd -xf fl-win64.tar.zst 'extracted/*_PE.bin'` の展開先 (repo 外の素材・work/ 配下に置く)
set -euo pipefail
D="${1:?usage: callers_scan.sh <extracted_dir>}"
cd "$D"
echo "== FT_ 名を文字列で持つ PE (FT_ 名数 / DLL import に freetype を含むか)"
grep -alE "FT_[A-Z][A-Za-z_0-9]{3,}" *_PE.bin | while read -r f; do
  n=$(grep -aoE 'FT_[A-Z][A-Za-z_0-9]{3,}' "$f" | sort -u | wc -l)
  i=$(objdump -p "$f" | grep -ciE 'DLL Name:.*freetype' || true)
  echo "$f FT_names=$n import_freetype=$i"
done
echo "== freetype DLL 名の文字列 (installer file table と DLL 自身)"
grep -al "freetype.dll\|freetype_x64.dll" *_PE.bin || true
echo "== FL 本体 (block00031) の FT_ 名 / GetProcAddress 数"
echo "FT_names=$(grep -aoE 'FT_[A-Z][A-Za-z_0-9]{3,}' block00031_PE.bin | sort -u | wc -l) GPA=$(objdump -p block00031_PE.bin | grep -c GetProcAddress || true)"
