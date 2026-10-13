#!/usr/bin/env bash
# fl-win64 の展開済み PE (extracted/*_PE.bin) から FreeType 呼出元の候補を洗う (#1144)。
# usage: bash oss/freetype/callers_scan.sh <extracted_dir>
#   extracted_dir は `tar --zstd -xf fl-win64.tar.zst --wildcards 'extracted/*_PE.bin'` の展開先 (repo 外の素材・work/ 配下に置く)
# 注意: FT_ 名は ASCII と UTF-16LE の両方で持たれうる (GetProcAddress 用の名前表は UTF-16 の場合がある)。両方走査する。
set -euo pipefail
D="${1:?usage: callers_scan.sh <extracted_dir>}"
cd "$D"
echo "== FT_ 名を文字列で持つ PE (ASCII / UTF-16LE の FT_ 名数 / DLL import に freetype を含むか)"
for f in *_PE.bin; do
  a=$(grep -aoE 'FT_[A-Z][A-Za-z_0-9]{3,}' "$f" | sort -u | wc -l || true)
  u=$(grep -aoP '(?:[\x20-\x7e]\x00){4,}' "$f" | tr -d '\0' | grep -E '^FT_[A-Z][A-Za-z_0-9]{3,}$' | sort -u | wc -l || true)
  if [ "$((a + u))" = 0 ]; then continue; fi
  i=$(objdump -p "$f" | grep -ciE 'DLL Name:.*freetype' || true)
  echo "$f FT_names_ascii=$a FT_names_utf16=$u import_freetype=$i"
done
echo "== freetype DLL 名の文字列 (ASCII / UTF-16LE)"
grep -al "freetype.dll\|freetype_x64.dll" *_PE.bin || true
grep -alP 'f\x00r\x00e\x00e\x00t\x00y\x00p\x00e\x00' *_PE.bin || true
echo "== FL 本体 (block00031) の FT_ 名 / GetProcAddress 数"
ft=$(grep -aoE 'FT_[A-Z][A-Za-z_0-9]{3,}' block00031_PE.bin | sort -u | wc -l || true)
gpa=$(objdump -p block00031_PE.bin | grep -c GetProcAddress || true)
echo "FT_names=$ft GPA=$gpa"
