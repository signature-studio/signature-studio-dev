#!/usr/bin/env bash
# dynamics 7 閉包の推移閉包 (closure_indirect.py の total) を lift → emcc -c し、status 行を出す。 batch_lift.sh と同じ列。
#   bash tools/plugins/dynamics/indirect_lift.sh <block> [<block> ...]
# 出力: work/dynamics/indirectlift/<block>/ と work/dynamics/indirectlift/status_run.csv (この run の行だけ。 実行の最初に作り直す)
# lift は lift_ranges.sh (PLUG_ICALL=1 = batch_lift.sh と同一鎖)。 closure_indirect.py の出力 (work/dynamics/indirect/) を入力にする。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
source "$HERE/env.sh"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
cd "$ROOT"
D=work/dynamics/indirectlift; mkdir -p "$D"
CSV="$D/status_run.csv"
echo "block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds,icall,dispatch_calls" > "$CSV"
export PLUG_ICALL=1
for b in "$@"; do
  PE="$FL_WIN64_DIR/extracted/block$(printf %05d "$b")_PE.bin"
  OUT="$D/$b"; rm -rf "$OUT"; mkdir -p "$OUT"
  R="work/dynamics/indirect/block$(printf %05d "$b").ranges.txt"
  NAME="$(python3 -c "
import json
M=json.load(open('PLUGIN_MATRIX.json'))['plugins']
print(next((p['name'] for p in M for m in p['win']['modules'] if m['block']==$b), '?'))")"
  CF="$(python3 -c "
import json
j=json.load(open('work/dynamics/indirect.json'))
v=next(x for x in j.values() if isinstance(x, dict) and x.get('block')==$b)
print(v['total_funcs'], v['total_bytes'])")"
  t0=$(date +%s)
  bash lift/lift_ranges.sh "$PE" "$R" "$OUT" p 2400 > "$OUT/lift.log" 2>&1
  rc=$?
  t1=$(date +%s)
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
  erc=-1
  if [ -f "$OUT/p.final.ll" ]; then
    ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$OUT/p.final.ll" -o "$OUT/p.o" -w -O0 -msimd128 > "$OUT/emcc.log" 2>&1 ); erc=$?
  fi
  DSP=$(grep -c 'call void @__icall_dispatch(' "$OUT/p.final.ll" 2>/dev/null || true)
  echo "$b,$NAME,${CF%% *},${CF##* },$rc,$DEF,${UNI:--1},$F80,$erc,$((t1-t0)),1,${DSP:-0}" >> "$CSV"
  echo "[dynamics_indirect_lift] $b $NAME rc=$rc defines=$DEF f80=$F80 unimpl=${UNI:--1} emcc_c=$erc $((t1-t0))s"
done
