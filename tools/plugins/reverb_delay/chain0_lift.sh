#!/usr/bin/env bash
# 従来鎖 (PLUG_ICALL=0) で閉包を直接 lift する (測定のみ・gate 外)。 既定鎖は lift/batch_lift.sh (PLUG_ICALL=1) で別に測る。
#   bash tools/plugins/reverb_delay/chain0_lift.sh <block> ...
# 出力: work/reverb_delay/chain0/<block>/p.* と work/reverb_delay/chain0/status.csv (batch_lift.sh と同じ 12 列。 icall 列は 0)
# 前提: reverb_delay_e2e.sh の prep / plugin_closure.py 実行済み (work/closure/block<NNNNN>.ranges.txt)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
export PATH=/opt/emsdk/node/24.19.0_64bit/bin:$PATH
cd "$HERE/.."
O=work/reverb_delay/chain0
mkdir -p "$O"
echo "block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds,icall,dispatch_calls" > "$O/status.csv"
for b in "$@"; do
  PE="$FL_WIN64_DIR/extracted/block$(printf %05d "$b")_PE.bin"
  OUT="$O/$b"; mkdir -p "$OUT"
  NAME="$(python3 -c "
import json
M=json.load(open('PLUGIN_MATRIX.json'))['plugins']
print(next((p['name'] for p in M for m in p['win']['modules'] if m['block']==$b), '?'))")"
  t0=$(date +%s)
  PLUG_ICALL=0 bash lift/lift_ranges.sh "$PE" "work/closure/block$(printf %05d "$b").ranges.txt" "$OUT" p 2400 > "$OUT/lift.log" 2>&1
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
  ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$OUT/p.final.ll" -o "$OUT/p.o" -w -O0 -msimd128 > "$OUT/emcc.log" 2>&1 ); erc=$?
  DSP=$(grep -c 'call void @__icall_dispatch(' "$OUT/p.final.ll" 2>/dev/null || true)
  echo "$b,$NAME,${CF%% *},${CF##* },$rc,$DEF,${UNI:--1},$F80,$erc,$((t1-t0)),0,${DSP:-0}" >> "$O/status.csv"
  echo "[chain0] $b $NAME rc=$rc defines=$DEF f80=$F80 emcc_c=$erc icall=0 dispatch=${DSP:-0} sec=$((t1-t0))"
done
exit 0
