#!/usr/bin/env bash
# KH-82 (#3995): Phase Plant (phaseplant) の vtable 各 slot を root にした x64c 閉包と unsup を測る。
#   usage: KH_CORE=<HeartCore.core_64 のパス> OUT=<出力先 (repo 外)> bash scripts/phaseplant_x64c_closure.sh
#   (1) rtti_walk.py で vtable を出す (2) PhasePlantDsp の vtable slot を 1 本ずつ root にして x64c で閉包を lift
#   (3) 全 slot を root にした閉包 (all) も測る。PhasePlantDsp は 12 slot (0..11) しか持たず
#   slot 14 が無いため、process slot の候補を全部測る。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
KH="$(cd -- "$HERE/.." && pwd)"
ROOT="$(cd -- "$KH/../../.." && pwd)"
FLE="$ROOT/tools/flelift"
CORE="${KH_CORE:?HeartCore.core_64 のパスを KH_CORE で指定}"
OUT="${OUT:?出力先を OUT で指定 (repo 外)}"
IMG=0x180000000
mkdir -p "$OUT"
python3 "$HERE/rtti_walk.py" "$CORE" "$OUT/rtti_vtables.json" > "$OUT/rtti_walk.log"
python3 - "$OUT/rtti_vtables.json" "$OUT" <<'EOF'
import json, os, sys
vt = json.load(open(sys.argv[1]))
out = sys.argv[2]
own = vt['.?AVPhasePlantDsp@phaseplant@@'][0]['slots']
print('PhasePlantDsp slots', len(own))
for i, s in enumerate(own):
    print('slot', i, s)
roots = [int(s, 16) for s in own]
os.makedirs(f'{out}/all', exist_ok=True)
json.dump({'roots': sorted(roots), 'calltgt': []}, open(f'{out}/all/entries.json', 'w'))
for i, s in enumerate(own):
    d = f'{out}/slot{i}'
    os.makedirs(d, exist_ok=True)
    json.dump({'roots': [int(s, 16)], 'calltgt': []}, open(f'{d}/entries.json', 'w'))
EOF
summ() {
  python3 - "$1/lift_meta.json" "$2" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
print('%s: functions=%d insns=%d unsup_kinds=%d unsup_sites=%d %s imports_used=%d unlifted_callees=%d traps=%d' % (
    sys.argv[2], len(m['functions']), m['ninsn'], len(m['unsup']), len(m['unsup_sites']), json.dumps(m['unsup'], sort_keys=True),
    len(m['imports_used']), len(m['unlifted_callees']), len(m['traps'])))
EOF
}
for d in "$OUT"/slot* "$OUT/all"; do
  name=$(basename "$d")
  python3 "$FLE/x64c.py" --pe "$CORE" --entries "$d/entries.json" --out "$d/lift" --closure 1000 \
    --img "$IMG" --shift 0 --img-size 0x625c000 --impbase 0x1D80000 | tail -c 300
  summ "$d/lift" "$name"
done
