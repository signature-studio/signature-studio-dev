#!/usr/bin/env bash
# ReWired (block 24161) の f80 (x87) 混入 IR に p0c/f80_lower.py (f80→f64 lowering, --no-rint) を当てて `emcc -c` が通るかを見る局所検証。
# 前提: batch_lift.sh 24161 実行済み (work/batch/24161/p.final.ll)。 到達性のみ (lowering 後の数値の正しさは見ていない)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
IN=work/batch/24161/p.final.ll; OUT=work/hostx/rewired_f80; rm -rf "$OUT"; mkdir -p "$OUT/tmp"
[ -f "$IN" ] || { echo "rewired_f80: $IN が無い (batch_lift.sh 24161 を先に)" >&2; exit 1; }
f80_before=$(python3 - "$IN" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
fs = [f for f in re.split(r'\n(?=define )', s) if f.startswith('define') and 'x86_fp80' in f]
print(len(fs), ' '.join(re.search(r'@([\w.$]+)', f).group(1) for f in fs))
PY
)
python3 p0c/f80_lower.py "$IN" "$OUT/lowered.ll" --no-rint --report "$OUT/report.json" > "$OUT/lower.log" 2>&1; lrc=$?
f80_after=$(grep -c 'x86_fp80' "$OUT/lowered.ll" 2>/dev/null || true); f80_after=${f80_after:--1}
emcc_c() { ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$1" -o "$OUT/x.o" -w -O0 -msimd128 > "$2" 2>&1 ); echo $?; }
e0=$(emcc_c "$IN" "$OUT/emcc_before.log")
e1=-1; [ -f "$OUT/lowered.ll" ] && e1=$(emcc_c "$OUT/lowered.ll" "$OUT/emcc_after.log")
unimpl=$(grep -o 'unimplemented [0-9]*' work/batch/24161/p.simd.log 2>/dev/null | head -1)
echo "rewired_f80: f80 関数(before)=[$f80_before]  lower rc=$lrc  x86_fp80 行(after)=$f80_after  emcc -c: before rc=$e0 / after rc=$e1  simd.log: ${unimpl:-なし}"
grep -m2 'error' "$OUT/emcc_before.log" | cut -c1-200 | sed 's/^/  before: /'
[ "$e1" != 0 ] && grep -m2 'error' "$OUT/emcc_after.log" 2>/dev/null | cut -c1-200 | sed 's/^/  after: /'
exit 0
