#!/usr/bin/env bash
# KH-17 (#780): Ladder Filter (ksla) の process 閉包を flelift の x64c で測る。
#   usage: KH_CORE=<HeartCore.core_64 のパス> OUT=<出力先 (repo 外・work/ 配下)> bash scripts/ladder_x64c_closure.sh
#   手順: (1) rtti_walk.py で vtable を出す (2) LadderDsp の vtable のうち SnapinDsp<LadderDspModel> と異なる slot を roots にする
#         (process = slot 14 は this->slot20 / this->slot15 / slot7 / slot0 を間接 call する。間接 call は x64c が辿らないので根に入れる)
#         (3) x64c で閉包を lift し unsup を数える (4) ネガコン: roots を process (slot 14) 1 本だけにした閉包を測る。
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
python3 - "$OUT/rtti_vtables.json" "$OUT/entries.json" "$OUT/entries_proc_only.json" <<'EOF'
import json, sys
vt = json.load(open(sys.argv[1]))
own = vt['.?AVLadderDsp@ladder@@'][0]['slots']
base = vt['.?AV?$SnapinDsp@VLadderDspModel@ladder@@@@'][0]['slots']
proc = int(own[14], 16)
roots = sorted({int(s, 16) for i, s in enumerate(own) if (i >= len(base) or base[i] != s) and int(s, 16) != int(base[1], 16)})
json.dump({'roots': roots, 'calltgt': []}, open(sys.argv[2], 'w'))
json.dump({'roots': [proc], 'calltgt': []}, open(sys.argv[3], 'w'))
print('own slots', len(own), 'base slots', len(base), 'process', hex(proc), 'roots', len(roots), ' '.join(hex(r) for r in roots))
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
python3 "$FLE/x64c.py" --pe "$CORE" --entries "$OUT/entries.json" --out "$OUT/lift" --closure 1000 \
  --img "$IMG" --shift 0 --img-size 0x625c000 --impbase 0x1D80000 | tail -c 300
summ "$OUT/lift" "closure (roots = LadderDsp 独自 slot)"
python3 "$FLE/x64c.py" --pe "$CORE" --entries "$OUT/entries_proc_only.json" --out "$OUT/lift_proc_only" --closure 1000 \
  --img "$IMG" --shift 0 --img-size 0x625c000 --impbase 0x1D80000 | tail -c 300
summ "$OUT/lift_proc_only" "negctl (roots = process slot 14 のみ)"
