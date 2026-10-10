#!/usr/bin/env bash
# roundtrip.sh PE FUNCS LABEL [OUTDIR] — 任意 PE の関数集合に対して
#   (1) 元 PE を RetDec decode → audit (before)   (2) icall_rewrite → RetDec → ir_icall_restore → audit (after)
# を実行し、JSON/表を OUTDIR に出す。FUNCS = "0xA-0xB,..." または VA 1 行 1 個。大きい集合は ranges を 4 chunk に分割して RetDec (arg 長制限対策)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
PE="$1"; F="$2"; LABEL="$3"; OUT="${4:-$HERE/work/rt_$3}"
CH="${CHUNKS:-1}"
mkdir -p "$OUT/tmp"
export TMPDIR="$OUT/tmp"
retdec_chunks() {  # $1 pe $2 ranges-csv $3 prefix
  python3 - "$2" "$3" "$CH" <<'PY'
import sys
r = open(sys.argv[1]).read().strip().split(',')
n = int(sys.argv[3])
for i in range(n):
    open('%s.ranges.%d' % (sys.argv[2], i), 'w').write(','.join(r[i::n]))
PY
  for i in $(seq 0 $((CH-1))); do
    /opt/retdec/bin/retdec-decompiler "$1" -o "$3.$i.drc.c" --select-ranges "$(cat "$3.ranges.$i")" --select-decode-only --timeout 3000 > "$3.$i.log" 2>&1 &
  done
  wait
}
# before: 元 PE を F の範囲で decode
python3 - "$PE" "$F" "$OUT" "$HERE" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[4])
import audit_icall as A
pe, f, out = sys.argv[1:4]
img = A.Image(pe)
toks = [t for t in open(f).read().replace(',', '\n').split() if t]
rng = {}
vas = []
for t in toks:
    if '-' in t:
        lo, hi = t.split('-'); rng[int(lo, 16)] = int(hi, 16); vas.append(int(lo, 16))
    else:
        vas.append(int(t, 16))
img.set_extra_starts(vas)
o = []
for v in sorted(set(vas)):
    r = (v, rng[v]) if v in rng else img.func_range(v)
    if r: o.append('0x%x-0x%x' % r)
open(out + '/before.ranges', 'w').write(','.join(o))
open(out + '/F.ranges', 'w').write(','.join(o))
PY
retdec_chunks "$PE" "$OUT/before.ranges" "$OUT/before"
IRS=""; for i in $(seq 0 $((CH-1))); do IRS="$IRS --ir $OUT/before.$i.drc.ll"; done
python3 "$HERE/audit_icall.py" --pe "$PE" --funcs "$OUT/F.ranges" $IRS --label "$LABEL-before" --json "$OUT/audit_before.json" | tee "$OUT/audit_before.txt" | tail -3
# after
python3 "$HERE/icall_rewrite.py" --pe "$PE" --funcs "$OUT/F.ranges" --out "$OUT/rw.dll" --map "$OUT/map.json" | tee "$OUT/rewrite.txt"
python3 - "$OUT" <<'PY'
import json, sys
o = sys.argv[1]
m = json.load(open(o + '/map.json'))
open(o + '/after.ranges', 'w').write(open(o + '/map.json.ranges').read() + ',0x%x-0x%x,0x%x-0x%x' % (m['stub'], m['stub'] + 78, m['comis_stub'], m['comis_stub'] + 29))
PY
retdec_chunks "$OUT/rw.dll" "$OUT/after.ranges" "$OUT/after"
IRS=""
for i in $(seq 0 $((CH-1))); do
  python3 "$HERE/ir_icall_restore.py" --ir "$OUT/after.$i.drc.ll" --map "$OUT/map.json" --out "$OUT/after.$i.restored.ll" --report "$OUT/restore.$i.json" >/dev/null
  IRS="$IRS --ir $OUT/after.$i.restored.ll"
done
python3 "$HERE/audit_icall.py" --pe "$PE" --funcs "$OUT/F.ranges" $IRS --label "$LABEL-after" --json "$OUT/audit_after.json" --sites "$OUT/sites_after.json" | tee "$OUT/audit_after.txt" | tail -3
