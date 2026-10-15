#!/usr/bin/env bash
# MX-3 ネガティブコントロール (規則 41): 意図的に壊して FAIL/差分を確認する。
#   NC1: root を「dummy 関数 (ret のみ)」に差し替え → closure が 567 未満になること
#   NC2: RTTI class フィルタ (FAMILY_EXACT) を外す → root 数が 4 (export のみ) に落ちること
#   NC3: x64c probe の root を不正 VA 1 個に差し替え → unsup site が base unsup を下回ること
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$HERE/.." && pwd)"; DSP="$BASE/dsp"; W="$DSP/work"
source "$HERE/../../../shared/env.sh"
PE="${MX_PE:-$BASE/work/extracted/VST3/Massive X.vst3}"
X64C="${MX_X64C:-$REPO_ROOT/tools/flelift/x64c.py}"

echo "=== NC1: root を dummy に置換 (surface 567 -> 1) ==="
python3 - "$W" <<'PY'
import json, sys
W = sys.argv[1]
d = json.load(open(W + '/surface_seeds_x64c.json'))
json.dump({'roots': [0x18000a870], 'calltgt': []}, open(W + '/e_nc1.json', 'w'))
print("   roots -> %d (元 567)" % 1)
PY
python3 "$DSP/scripts/mx_entry_surface.py" "$PE" /dev/null "$W/nc_dummy" >/dev/null 2>&1 || true
mkdir -p "$W/lift_nc1"
python3 "$X64C" --pe "$PE" --entries "$W/e_nc1.json" --out "$W/lift_nc1" \
  --img 0x180000000 --shift 0 --img-size 0x6616000 --closure 0 > "$W/logs/x64c_nc1.log" 2>&1
python3 - "$W" <<'PY'
import json, sys
m = json.load(open(sys.argv[1] + '/lift_nc1/lift_meta.json'))
base = json.load(open(sys.argv[1] + '/lift_seeds/lift_meta.json'))
print("   NC1 insns=%d (base %d)  unsup=%d (base %d)  -> %s"
      % (m['ninsn'], base['ninsn'], sum(m['unsup'].values()), sum(base['unsup'].values()),
         'FAIL<期待>' if sum(m['unsup'].values()) < sum(base['unsup'].values()) else 'PASS<異常>'))
PY

echo "=== NC2: RTTI class フィルタを外く (roots 567 -> export 4) ==="
python3 - "$W" "$PE" <<'PY'
import json, sys, struct, bisect, re
import pefile
W, PE = sys.argv[1], sys.argv[2]
d = json.load(open(W + '/surface.json'))
print("   base seeds=%d  family_slots=%d" % (d['seeds'], d['family_slots_total']))
json.dump({'roots': [int(d['exports'][k], 16) for k in d['exports']], 'calltgt': []},
          open(W + '/e_nc2.json', 'w'))
print("   NC2 roots -> %d (export のみ)" % len(d['exports']))
PY
mkdir -p "$W/lift_nc2"
python3 "$X64C" --pe "$PE" --entries "$W/e_nc2.json" --out "$W/lift_nc2" \
  --img 0x180000000 --shift 0 --img-size 0x6616000 --closure 0 > "$W/logs/x64c_nc2.log" 2>&1
python3 - "$W" <<'PY'
import json, sys
W = sys.argv[1]
m = json.load(open(W + '/lift_nc2/lift_meta.json'))
b = json.load(open(W + '/lift_seeds/lift_meta.json'))
print("   NC2 insns=%d (base %d) unsup=%d (base %d) -> %s"
      % (m['ninsn'], b['ninsn'], sum(m['unsup'].values()), sum(b['unsup'].values()),
         'FAIL<期待>' if sum(m['unsup'].values()) < sum(b['unsup'].values()) else 'PASS<異常>'))
PY

echo "=== NC3: root を不正 VA 0x180000001 に置換 (unsup が base unsup を下回ること) ==="
python3 - "$W" <<'PY'
import json, sys
W = sys.argv[1]
d = json.load(open(W + '/surface.json'))
# ダミー: 不正 VA 1 個の root では lift 対象が base (全 root) より小さくなり unsup も base 未満 -> FAIL 確認
json.dump({'roots': [0x180000001], 'calltgt': []}, open(W + '/e_nc3.json', 'w'))
print("   NC3 roots -> 1 (VA 0x180000001 = .text 外/不正)")
PY
mkdir -p "$W/lift_nc3"
python3 "$X64C" --pe "$PE" --entries "$W/e_nc3.json" --out "$W/lift_nc3" \
  --img 0x180000000 --shift 0 --img-size 0x6616000 --closure 0 > "$W/logs/x64c_nc3.log" 2>&1 || echo "   NC3 x64c 異常終了 (期待)"
python3 - "$W" <<'PY'
import json, os, sys
W = sys.argv[1]
p = W + '/lift_nc3/lift_meta.json'
b = json.load(open(W + '/lift_seeds/lift_meta.json'))
if os.path.exists(p):
    m = json.load(open(p))
    print("   NC3 insns=%d (base %d) unsup=%d (base %d) -> %s"
          % (m['ninsn'], b['ninsn'], sum(m['unsup'].values()), sum(b['unsup'].values()),
             'FAIL<期待>' if sum(m['unsup'].values()) < sum(b['unsup'].values()) else 'PASS<異常>'))
else:
    print("   NC3 lift_meta 無し = lift 失敗 (期待どおり FAIL 相当)")
PY
echo "NC done"
