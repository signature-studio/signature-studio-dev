#!/usr/bin/env bash
# #667 の閉包 (closure_unreached.py の total3 = total2 + 根 (RVA32 表・命令内即値) の BFS 閉包) の ranges を lift → emcc -c し、status 行を出す。 lea_lift.sh と同じ列・同じ手順 (入出力 dir だけ違う)。
#   bash tools/plugins/sampler/unr_lift.sh <block> [<block> ...]
# 出力: work/sampler/unrlift/<block>/ と work/sampler/unrlift/status_run.csv (この run の行だけ。 実行の最初に作り直す)
# RetDec は lift_from_ll.sh で .ll 出力後に止める (C バックエンドは使わない。 REPORT §5)。 後段の pass 鎖は lift_ranges.sh と同一。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
D=work/sampler/unrlift; mkdir -p "$D"
CSV="$D/status_run.csv"
echo "block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds,unimpl_names,f80_raw,emcc_c_rc_raw,lowered" > "$CSV"
for b in "$@"; do
  PE="$FL_WIN64_DIR/extracted/block$(printf %05d "$b")_PE.bin"
  OUT="$D/$b"; rm -rf "$OUT"; mkdir -p "$OUT"
  R="work/sampler/unr/block$(printf %05d "$b").ranges.txt"
  NAME="$(python3 -c "
import json
M=json.load(open('PLUGIN_MATRIX.json'))['plugins']
print(next((p['name'] for p in M for m in p['win']['modules'] if m['block']==$b), '?'))")"
  CF="$(python3 -c "
import json
j=json.load(open('work/sampler/unr.json'))
v=next(x for x in j.values() if x.get('block')==$b)
print(v['total3']['funcs'], v['total3']['bytes'])")"
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
  # lea 先に x87 を含む関数が入る block (Granulizer / Slicer / Slicer 2) は、p0c/f80_lower.py (x86_fp80→f64, #197) を明示の段として通し、
  # judge に渡す f80_funcs / emcc_c_rc は lowering 後の値、raw (lowering 前) は f80_raw / emcc_c_rc_raw に残す。 f80→f64 は bit-exact を保証しない (通過 ≠ 正しさ)
  F80R=$F80; ERCR=$erc; LOW=0
  if [ "$F80" -gt 0 ] 2>/dev/null; then
    LOW=1
    python3 p0c/f80_lower.py "$OUT/p.final.ll" "$OUT/p.lower.ll" --report "$OUT/lower.json" > "$OUT/lower.log" 2>&1 || true
    if [ -f "$OUT/p.lower.ll" ]; then F80=$(grep -c 'x86_fp80' "$OUT/p.lower.ll" || true); else F80=-1; fi
    erc=-1
    if [ -f "$OUT/p.lower.ll" ]; then
      ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$OUT/tmp" emcc -c "$OUT/p.lower.ll" -o "$OUT/p.lower.o" -w -O0 -msimd128 > "$OUT/emcc_lower.log" 2>&1 ); erc=$?
    fi
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
  echo "$b,$NAME,${CF%% *},${CF##* },$rc,$DEF,${UNI:--1},$F80,$erc,$((t1-t0)),$NAMES,$F80R,$ERCR,$LOW" >> "$CSV"
  echo "[lea_lift] $b $NAME rc=$rc defines=$DEF f80=$F80 unimpl=${UNI:--1} emcc_c=$erc f80_raw=$F80R emcc_c_raw=$ERCR lowered=$LOW ${t0:+$((t1-t0))s}"
done
