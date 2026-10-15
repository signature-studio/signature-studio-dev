#!/usr/bin/env bash
# MX-6 (#1123) e2e — 1 コマンド再現 (規則 37 / 38)
#   NC (合成バイト列) → RTTI/入口面 → vectorcall 静的検出 (本体 + 線形独立再計算) → xmm0〜3 判定 (MX-33 #3032)
#   → .pdata unwind census → 判定 → positive control (funclet 数の固定値) → FH4 FuncInfo4 固定部 (U4a・mx6_fh4.py)
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

echo "== 1/7 NC: 合成バイト列の正例・負例 (PE 不要)"
python3 "$DSP/scripts/mx6_vectorcall.py" --selftest | sed 's/^/   /'

echo "== 2/7 RTTI + VST3 入口面 (seeds 567 / 1-round closure)"
python3 "$DSP/scripts/mx_rtti.py" "$PE" "$W/rtti_vtables.json" >/dev/null 2>&1
python3 "$DSP/scripts/mx_entry_surface.py" "$PE" "$W/rtti_vtables.json" "$W/surface" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('   seeds=%d one_round=%d pdata=%d' % (d['seeds'], d['one_round_closure'], d['pdata_funcs'] if 'pdata_funcs' in d else 0))"

echo "== 3/7 vectorcall 静的検出 (本体: CFG must-def / 独立再計算: 線形 anyref / 感度: 非 begin 入口)"
python3 "$DSP/scripts/mx6_vectorcall.py" "$PE" "$W/surface_seeds_x64c.json" "$W/surface_one_x64c.json" "$W/vectorcall.json" | sed 's/^/   /'

echo "== 4/7 受入1 (MX-33 #3032): xmm0〜3 だけの入口 livein 保留 17 件の判定 (NC 9 件・独立再計算・感度)"
python3 "$DSP/scripts/mx33_xmm03.py" "$PE" "$W/vectorcall.json" "$W/xmm03.json" > "$W/xmm03.log"
grep -v '^| ' "$W/xmm03.log" | sed 's/^/   /'

echo "== 5/7 .pdata unwind census (CHAININFO / EH handler 名)"
python3 "$DSP/scripts/mx6_pdata_eh.py" "$PE" "$W/surface_seeds_x64c.json" "$W/surface_one_x64c.json" "$W/pdata_eh.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('   PE: pdata=%d chained=%d eh=%d unreadable_uinfo=%d' % (d['pe_total']['pdata_entries'], d['pe_total'].get('chained_entries(CHAININFO)',0), d['pe_total'].get('eh_handler_entries',0), d['pe_total'].get('unreadable_unwind_info',0))); print('   seeds: %s' % d['seeds']); print('   one_round: %s' % d['one_round']); print('   funclets(FH3): %s' % d['funclets_fh3'])"

echo "== 6/7 判定 (期待値: seeds と 1-round の pdata 始点で xmm4/5 入口 livein = 0 / 受入1 の内訳が 17 件)"
python3 - "$W" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + '/vectorcall.json'))
x = json.load(open(sys.argv[1] + '/xmm03.json'))
ok = (d['seeds']['vectorcall_livein45_pdata_begin'] == 0 and d['one_round']['vectorcall_livein45_pdata_begin'] == 0
      and d['seeds']['consistency_livein_subset_of_anyref'] and d['one_round']['consistency_livein_subset_of_anyref']
      and x['population'] == 17 and sum(x['counts'].values()) == 17 and x['containment_cfg_P_subset_linear_P'])
print('   %s' % ('PASS (pdata 始点の vectorcall livein 0 / 整合 OK / 受入1 の内訳 17 = 件数一致・包含 OK)' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
PY

echo "== 7/7 positive control: funclet 数の固定値 (MX-6 測定値 seeds 533 / pdata 始点 529 が変わらないこと)"
python3 - "$W" <<'PY'
import json, sys
d = json.load(open(sys.argv[1] + '/pdata_eh.json'))['funclets_fh3']['seeds']
ok = d['funclets'] == 533 and d['funclet_is_pdata_begin'] == 529
print('   funclets=%d (期待 533) pdata 始点=%d (期待 529) -> %s' % (
    d['funclets'], d['funclet_is_pdata_begin'], 'PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
PY

echo "== 8/8 FH4 FuncInfo4 固定部 census + NC (U4a・構造は MSVC 公式記事の FuncInfo4 定義に従う)"
python3 "$DSP/scripts/mx6_fh4.py" --selftest "$PE" | sed 's/^/   /'
python3 "$DSP/scripts/mx6_fh4.py" "$PE" "$W/fh4_census.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('   fh4_entries=%d fi_distinct=%d problems=%s' % (d['fh4_entries'], d['fh4_fi_distinct'], d['fixed_part_problems'])); print('   header_bit_sets=%s' % d['header_bit_sets']); print('   pointer_position=%s' % d['pointer_position_census'])"

T1=$(date +%s)
echo "OK  elapsed=$((T1-T0))s  load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
