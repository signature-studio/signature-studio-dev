#!/usr/bin/env bash
# バッチ lift 駆動: プラグイン (block 番号) ごとに DSP 閉包 → RetDec → pass 鎖 → ステータス CSV。
#   bash tools/plugins/lift/batch_lift.sh <block> [<block> ...]      例: 18983 19078
#   bash tools/plugins/lift/batch_lift.sh --tier T0                  (PLUGIN_MATRIX.json の Tier 全件)
# 出力: work/batch/<block>/ (IR, simd C, report) と work/batch/status.csv
# 注意: ここでは **固有閉包のみ** を lift する (framework frontier は P0 で別途 lift した共有 lib を想定)。
#       ステータス列: block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
cd "$ROOT"
BLOCKS=("$@")
if [ "${1:-}" = "--tier" ]; then
  mapfile -t BLOCKS < <(python3 - "$2" <<'PY'
import json, sys
t = sys.argv[1]
M = json.load(open('PLUGIN_MATRIX.json'))['plugins']
for p in M:
    if p['tier'] == t:
        for m in p['win']['modules']:
            if m['exports_CreatePlugInstance'] and m['lang'].startswith('Delphi'):
                print(m['block']); break
PY
)
fi
mkdir -p work/batch
[ -f work/batch/status.csv ] || echo "block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds" > work/batch/status.csv
python3 lift/plugin_closure.py "${BLOCKS[@]}" > /dev/null
for b in "${BLOCKS[@]}"; do
  PE="/home/ubuntu/work/analysis/win64/extracted/block$(printf %05d "$b")_PE.bin"
  OUT="work/batch/$b"; mkdir -p "$OUT"
  NAME="$(python3 -c "
import json
M=json.load(open('PLUGIN_MATRIX.json'))['plugins']
print(next((p['name'] for p in M for m in p['win']['modules'] if m['block']==$b), '?'))")"
  t0=$(date +%s)
  bash lift/lift_ranges.sh "$PE" "work/closure/block$(printf %05d "$b").ranges.txt" "$OUT" p 2400 > "$OUT/lift.log" 2>&1
  rc=$?
  t1=$(date +%s)
  CF="$(python3 -c "import json;c=json.load(open('work/closure/block$(printf %05d "$b").json'));print(c['unique_funcs'],c['unique_bytes'])")"
  DEF=$(grep -c '^define' "$OUT/p.final.ll" 2>/dev/null || echo 0)
  UNI=$(grep -o 'unimplemented [0-9]*' "$OUT/p.simd.log" 2>/dev/null | awk '{print $2}' | head -1)
  F80=$(python3 - "$OUT/p.final.ll" <<'PY'
import re, sys
try:
    s = open(sys.argv[1]).read()
except Exception:
    print(-1); sys.exit()
print(sum(1 for f in re.split(r'\n(?=define )', s) if f.startswith('define') and 'x86_fp80' in f))
PY
)
  # IR が wasm バックエンドを通るか (compile のみ; link/実行は個別検証)
  ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$OUT/p.final.ll" -o "$OUT/p.o" -w -O0 -msimd128 > "$OUT/emcc.log" 2>&1 ); erc=$?
  echo "$b,$NAME,${CF%% *},${CF##* },$rc,$DEF,${UNI:--1},$F80,$erc,$((t1-t0))" >> work/batch/status.csv
  echo "[batch] $b $NAME rc=$rc defines=$DEF f80=$F80 emcc_c=$erc"
done
