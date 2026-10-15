#!/usr/bin/env bash
# MX-39 (#3776) e2e — MX-6 残件 U4d (funclet の深い closure 到達・E8/E9 候補の由来) の 1 コマンド再現
#   closure (linear・flow 各 1 本, mx_closure.py で fixed point まで) → funclet 到達 (BFS 深さ) と候補の命令境界判定
# 出力先は repo 外 (MX6_WORK, 既定 $RUNNER_TEMP/massivex-mx6)。PE は MX_PE で指定 (既定 work/extracted)。
# 所要 約 8 分 (flow closure が大半)。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$HERE/.." && pwd)"     # tools/targets/massivex
DSP="$BASE/dsp"
PE="${MX_PE:-$BASE/work/extracted/VST3/Massive X.vst3}"
[ -f "$PE" ] || { echo "FATAL: PE not found: $PE" >&2; exit 2; }
W="${MX39_WORK:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/massivex-mx39}"
mkdir -p "$W"
RTTI="${MX6_WORK:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/massivex-mx6}/rtti_vtables.json"
[ -f "$RTTI" ] || { echo "FATAL: RTTI json not found (run mx6_e2e.sh first): $RTTI" >&2; exit 2; }
T0=$(date +%s)

echo "== 1/3 closure linear (mx_closure.py, fixed point)"
python3 "$DSP/scripts/mx_closure.py" "$PE" "$RTTI" "$W/clo" linear any >/dev/null 2>"$W/clo.stderr"
echo "   $(tail -1 "$W/clo.stderr" | cut -c1-120)"
echo "== 2/3 closure flow (mx_closure.py, code/data 区別つき, fixed point)"
python3 "$DSP/scripts/mx_closure.py" "$PE" "$RTTI" "$W/flow" flow any >/dev/null 2>"$W/flow.stderr"
echo "   $(tail -1 "$W/flow.stderr" | cut -c1-120)"
echo "== 3/3 funclet の BFS 深さ・直接辺の元・E8/E9 候補の命令境界"
python3 "$DSP/scripts/mx39_funclet_reach.py" "$PE" "$W/clo_sets.pkl" "$W/flow_sets.pkl" "$W/reach.json" > "$W/reach.stdout"
python3 - "$W/reach.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print('   FH3 funclet universe=%d (FH3 関数 %d, 上限で棄却 %d)' % (d['funclet_universe_fh3_all'], d['fh3_functions_all'], d['fh3_funcinfo_rejected_by_cap']))
print('   round-1 母数 (REPORT の 537) = %d' % d['funclet_one_round_set_linear'])
for m, v in d['modes'].items():
    print('   %-6s 到達 funclet=%d  深さ≤2: %d  深さ≤3: %d  (入口数 round0..3: %s)' % (
        m, len(v['reached_funclets']), sum(1 for x in v['reached_funclets'] if x['depth'] <= 2),
        sum(1 for x in v['reached_funclets'] if x['depth'] <= 3),
        '/'.join(str(v['closure_entries_by_round'][str(k)]) for k in range(4))))
c = d['candidates']
print('   E8/E9 一致 (全 FH3 funclet 対象) %d 件: 命令境界 %d・境界かつ親の closure 非到達 %d' % (
    len(c), sum(1 for r in c if r.get('site_is_insn_boundary_linear')),
    sum(1 for r in c if r.get('site_is_insn_boundary_linear') and r.get('container_depth_flow') is None)))
r1 = [r for r in c if r.get('target_parent_in_round1')]
print('   537 母数への一致 %d 件 (命令境界 %d 件)' % (len(r1), sum(1 for r in r1 if r.get('site_is_insn_boundary_linear'))))
PY

T1=$(date +%s)
echo "OK  elapsed=$((T1-T0))s"
