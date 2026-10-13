#!/usr/bin/env bash
# 推移閉包 (closure_indirect.py の total) の ranges を lift → emcc -c し、status 行を出す。 batch_lift.sh と同じ列 (+ unimpl_names)。
#   bash tools/plugins/sampler/indirect_lift.sh <block> [<block> ...]
# 出力: work/sampler/indirectlift/<block>/ と work/sampler/indirectlift/status_run.csv (この run の行だけ。 実行の最初に作り直す)
# RetDec は lift_from_ll.sh で .ll 出力後に止める (C バックエンドは使わない。 REPORT §5)。 後段の pass 鎖は lift_ranges.sh と同一。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
D=work/sampler/indirectlift; mkdir -p "$D"
CSV="$D/status_run.csv"
echo "block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds,unimpl_names" > "$CSV"
for b in "$@"; do
  PE="$FL_WIN64_DIR/extracted/block$(printf %05d "$b")_PE.bin"
  OUT="$D/$b"; rm -rf "$OUT"; mkdir -p "$OUT"
  R="work/sampler/indirect/block$(printf %05d "$b").ranges.txt"
  NAME="$(python3 -c "
import json
M=json.load(open('PLUGIN_MATRIX.json'))['plugins']
print(next((p['name'] for p in M for m in p['win']['modules'] if m['block']==$b), '?'))")"
  CF="$(python3 -c "
import json
j=json.load(open('work/sampler/indirect.json'))
v=next(x for x in j.values() if x.get('block')==$b)
print(v['total_funcs'], v['total_bytes'])")"
  t0=$(date +%s)
  bash sampler/lift_from_ll.sh "$PE" "$R" "$OUT" p 2400 > "$OUT/lift.log" 2>&1
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
  NAMES=$(python3 - "$OUT/p.simd.log" <<'PY'
import re, sys
n = set()
try:
    for l in open(sys.argv[1]):
        m = re.match(r'\s+unimplemented: \S+ (__asm_\S+?)\(', l)
        if m:
            n.add(re.sub(r'(__\d+)+$', '', m.group(1)[len('__asm_'):]))
except OSError:
    pass
print('|'.join(sorted(n)))
PY
)
  echo "$b,$NAME,${CF%% *},${CF##* },$rc,$DEF,${UNI:--1},$F80,$erc,$((t1-t0)),$NAMES" >> "$CSV"
  echo "[indirect_lift] $b $NAME rc=$rc defines=$DEF f80=$F80 unimpl=${UNI:--1} emcc_c=$erc ${t0:+$((t1-t0))s}"
done
