#!/usr/bin/env bash
# MX-6 (#1123) e2e — 1 コマンド再現 (規則 37 / 38)
#   NC (合成バイト列) → RTTI/入口面 → vectorcall 静的検出 (本体 + 線形独立再計算) → .pdata unwind census
# 出力先は repo 外 (MX6_WORK, 既定 $RUNNER_TEMP/massivex-mx6)。PE は MX_PE で指定 (既定 work/extracted)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$HERE/.." && pwd)"     # tools/targets/massivex
DSP="$BASE/dsp"
PE="${MX_PE:-$BASE/work/extracted/VST3/Massive X.vst3}"
[ -f "$PE" ] || { echo "FATAL: PE not found: $PE" >&2; exit 2; }
W="${MX6_WORK:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/massivex-mx6}"
mkdir -p "$W"
L0="$(cut -d' ' -f1-3 /proc/loadavg)"
T0=$(date +%s)

echo "== 1/5 NC: 合成バイト列の正例・負例 (PE 不要)"
python3 "$DSP/scripts/mx6_vectorcall.py" --selftest | sed 's/^/   /'

echo "== 2/5 RTTI + VST3 入口面 (seeds 567 / 1-round closure)"
python3 "$DSP/scripts/mx_rtti.py" "$PE" "$W/rtti_vtables.json" >/dev/null 2>&1
python3 "$DSP/scripts/mx_entry_surface.py" "$PE" "$W/rtti_vtables.json" "$W/surface" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('   seeds=%d one_round=%d pdata=%d' % (d['seeds'], d['one_round_closure'], d['pdata_funcs'] if 'pdata_funcs' in d else 0))"

echo "== 3/5 vectorcall 静的検出 (本体: CFG must-def / 独立再計算: 線形 anyref / 感度: 非 begin 入口)"
python3 "$DSP/scripts/mx6_vectorcall.py" "$PE" "$W/surface_seeds_x64c.json" "$W/surface_one_x64c.json" "$W/vectorcall.json" | sed 's/^/   /'

echo "== 4/5 .pdata unwind census (CHAININFO / EH handler 名)"
python3 "$DSP/scripts/mx6_pdata_eh.py" "$PE" "$W/surface_seeds_x64c.json" "$W/surface_one_x64c.json" "$W/pdata_eh.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('   PE: pdata=%d chained=%d eh=%d unreadable_uinfo=%d' % (d['pe_total']['pdata_entries'], d['pe_total'].get('chained_entries(CHAININFO)',0), d['pe_total'].get('eh_handler_entries',0), d['pe_total'].get('unreadable_unwind_info',0))); print('   seeds: %s' % d['seeds']); print('   one_round: %s' % d['one_round'])"

echo "== 5/5 判定 (期待値: seeds と 1-round の pdata 始点で xmm4/5 入口 livein = 0)"
python3 - "$W" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + '/vectorcall.json'))
ok = (d['seeds']['vectorcall_livein45_pdata_begin'] == 0 and d['one_round']['vectorcall_livein45_pdata_begin'] == 0
      and d['seeds']['consistency_livein_subset_of_anyref'] and d['one_round']['consistency_livein_subset_of_anyref'])
print('   %s' % ('PASS (pdata 始点の vectorcall livein 0 / 整合 OK)' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
PY

T1=$(date +%s)
echo "OK  elapsed=$((T1-T0))s  load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
