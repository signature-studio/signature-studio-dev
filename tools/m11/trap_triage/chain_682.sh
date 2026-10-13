#!/usr/bin/env bash
# #682: 現在の work/ の build をそのまま使い, 各 unit の開始前に [[g+8]+8] (TList の FItems 欄) と Count を stderr へ出す.
#   usage: chain_682.sh <tag>   → work/probe682/chain_<tag>.err (`chain <unit> g= T= items= cnt=`), chain_<tag>.out (survey 結果)
#   survey は m11_survey.mjs の複製 (判定ロジックは同一; 生成物は work/probe682/ に置く).
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
tag=$1
mkdir -p work/probe682
sed -e "s|new URL('./', import.meta.url).pathname|'$HERE'|" \
    -e "s|  const va = hex(i);|  const va = hex(i); if (process.env.SV_CHAIN) { const g = mod.HEAPU32[0x11f26a0 >> 2]; const t = g ? mod.HEAPU32[(g + 8) >> 2] : 0; fs.writeSync(2, 'chain ' + i + ' g=' + g.toString(16) + ' T=' + t.toString(16) + ' items=' + (t ? mod.HEAPU32[(t + 8) >> 2] : 0).toString(16) + ' cnt=' + (t ? mod.HEAPU32[(t + 0x10) >> 2] : 0) + '\\\\n'); }|" \
    m11_survey.mjs > work/probe682/chain_$tag.mjs
SV_CHAIN=1 M11_SURVEY_UNITS=work/probe682/units_$tag.json node work/probe682/chain_$tag.mjs > work/probe682/chain_$tag.out 2> work/probe682/chain_$tag.err || { echo "[chain] survey failed (rc=$?)" >&2; exit 1; }
grep -a -o "^M11_SURVEY .\{0,120\}" work/probe682/chain_$tag.out
grep -a -c "^chain " work/probe682/chain_$tag.err | sed 's/^/[chain] lines: /'
