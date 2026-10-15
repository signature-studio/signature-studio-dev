#!/usr/bin/env bash
# MX-3 e2e — 1 コマンド再現 (規則 37 / 38)
#   RTTI/vtable 抽出 → 入口面特定 → x64c probe (未対応命令センサス) → 独立再計算
# 出力: dsp/work/{rtti_vtables.json, surface*.json, x64c_seeds.log, recount.json}
# 基準 dir = tools/targets/massivex/ (work/ はここ)。dsp/ から起動しても動く。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$HERE/.." && pwd)"     # tools/targets/massivex
cd "$BASE"
source "$HERE/../../../shared/env.sh"
DSP="$BASE/dsp"
W="$DSP/work"
PE="${MX_PE:-$BASE/work/extracted/VST3/Massive X.vst3}"
[ -f "$PE" ] || { echo "FATAL: PE not found: $PE (cwd=$(pwd))" >&2; exit 2; }
X64C="${MX_X64C:-$REPO_ROOT/tools/flelift/x64c.py}"
[ -f "$X64C" ] || { echo "FATAL: x64c not found: $X64C" >&2; exit 2; }
mkdir -p "$W"
L0="$(cut -d' ' -f1-3 /proc/loadavg)"

T0=$(date +%s)
echo "== 1/5 RTTI + vtable 抽出"
python3 "$DSP/scripts/mx_rtti.py" "$PE" "$W/rtti_vtables.json" 2>&1 | sed 's/^/   /'

echo "== 2/5 VST3 入口面 (exports + MassiveX*/Steinberg::Vst vtable slot)"
python3 "$DSP/scripts/mx_entry_surface.py" "$PE" "$W/rtti_vtables.json" "$W/surface" | sed 's/^/   /'

echo "== 3/5 x64c probe (未対応命令センサス, tools/flelift/x64c.py を読取実行)"
python3 - "$W" <<'PY'
import json, sys
W = sys.argv[1]
d = json.load(open(W + '/surface_seeds_x64c.json'))
json.dump({'roots': [int(x, 16) for x in d['roots']], 'calltgt': []},
          open(W + '/e_seeds.json', 'w'))
print("   entries: %d roots" % len(d['roots']))
PY
mkdir -p "$W/lift_seeds" "$W/logs"
python3 "$X64C" --pe "$PE" --entries "$W/e_seeds.json" --out "$W/lift_seeds" \
  --img 0x180000000 --shift 0 --img-size 0x6616000 --closure 0 \
  > "$W/logs/x64c_seeds.log" 2>&1 || { echo "   [FAIL] x64c が異常終了"; exit 1; }
head -c 160 "$W/logs/x64c_seeds.log"; echo
python3 - "$W" <<'PY'
import json, collections, sys
W = sys.argv[1]
m = json.load(open(W + '/lift_seeds/lift_meta.json'))
u = m['unsup']
g = collections.Counter()
for k, v in u.items():
    mn = k.split(':', 1)[0]    # key = mnemonic:mnemonic (x64c.py の key = mnemonic + ':' + 理由)
    if mn.startswith(('aes', 'vaes', 'sha256')) or mn in ('pclmulqdq', 'pshufb', 'palignr'):
        grp = 'AES/SHA-NI'
    elif mn.startswith('v'):
        grp = 'AVX(VEX/EVEX)'
    elif mn[0] == 'f':
        grp = 'x87'
    else:
        grp = 'other'
    g[grp] += v
print("   insns=%d  unsup_sites=%d  unsup_kinds=%d  (%.2f%% of insns)"
      % (m['ninsn'], sum(u.values()), len(u), 100.0 * sum(u.values()) / m['ninsn']))
for k, v in g.most_common():
    print("   group %-14s %d sites" % (k, v))
PY

echo "== 4/5 独立再計算 (線形 E8/E9 バイトスキャン・別アルゴリズム)"
python3 "$DSP/scripts/mx_recount.py" "$PE" "$W/rtti_vtables.json" "$W/recount.json" | sed 's/^/   /'

echo "== 5/5 .pdata chained 分割 + leaf 近似の定量化 (MX-5 受入 2・3)"
python3 "$DSP/scripts/mx_pdata_quant.py" "$PE" "$W/pdata_quant.json" | sed 's/^/   /'

T1=$(date +%s)
echo "OK  elapsed=$((T1-T0))s  load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
