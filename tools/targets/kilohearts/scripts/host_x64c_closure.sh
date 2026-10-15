#!/usr/bin/env bash
# KH-6 (#61): ホスト 2 種 (Snap Heap = micropass / Multipass = multipass) の process 閉包を flelift の x64c で測る。
#   usage: KH_CORE=<HeartCore.core_64 のパス> OUT=<出力先 (repo 外・work/ 配下)> bash scripts/host_x64c_closure.sh
#   手順は ladder_x64c_closure.sh と同じ: (1) rtti_walk.py で vtable を出す (2) 各ホストの *Dsp vtable のうち
#   SnapinDsp<*DspModel> と異なる slot (no-op 0x1800128a0 は除く) を roots にする (3) x64c で閉包を lift し unsup を数える
#   (4) ネガコン: roots を process (slot 14) 1 本だけにした閉包を測る。
#   Phase Plant は SnapinDsp 基底を持たず process slot の対応が無いため対象外 (REPORT_APPENDIX_61.md §4)。
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
hosts = {
    'micropass': ('.?AVMicropassDsp@micropass@@', '.?AV?$SnapinDsp@VMicropassDspModel@micropass@@@@'),
    'multipass': ('.?AVMultipassDsp@multipass@@', '.?AV?$SnapinDsp@VMultipassDspModel@multipass@@@@'),
}
for name, (own_k, base_k) in hosts.items():
    own = vt[own_k][0]['slots']
    base = vt[base_k][0]['slots']
    proc = int(own[14], 16)
    noop = int(base[1], 16)
    roots = sorted({int(s, 16) for i, s in enumerate(own) if (i >= len(base) or base[i] != s) and int(s, 16) != noop})
    os.makedirs(f'{out}/{name}', exist_ok=True)
    json.dump({'roots': roots, 'calltgt': []}, open(f'{out}/{name}/entries.json', 'w'))
    json.dump({'roots': [proc], 'calltgt': []}, open(f'{out}/{name}/entries_proc_only.json', 'w'))
    print(name, 'own slots', len(own), 'base slots', len(base), 'process', hex(proc), 'roots', len(roots), ' '.join(hex(r) for r in roots))
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
for name in micropass multipass; do
  python3 "$FLE/x64c.py" --pe "$CORE" --entries "$OUT/$name/entries.json" --out "$OUT/$name/lift" --closure 1000 \
    --img "$IMG" --shift 0 --img-size 0x625c000 --impbase 0x1D80000 | tail -c 300
  summ "$OUT/$name/lift" "$name closure (roots = 独自 slot)"
  python3 "$FLE/x64c.py" --pe "$CORE" --entries "$OUT/$name/entries_proc_only.json" --out "$OUT/$name/lift_proc_only" --closure 1000 \
    --img "$IMG" --shift 0 --img-size 0x625c000 --impbase 0x1D80000 | tail -c 300
  summ "$OUT/$name/lift_proc_only" "$name negctl (roots = process slot 14 のみ)"
done
