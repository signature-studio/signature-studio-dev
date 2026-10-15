#!/usr/bin/env bash
# value_flow_5243_e2e.sh — #5243 (LD-260): site ↔ IR i32 読み出しの対応方式の計測の 1 コマンド再現 (修復は行わない)。
#   1/3 audit (修復前) → 2/3 value_flow_5243.py base (link_d17 と同じ宛先判定) → 3/3 value_flow_5243.py rmw (RMW 形の宛先も使用と数える)
# 素材: work-m11 (tools/m11/work/) と toolchain-emsdk は不要 (emcc は使わない)。
# 使い方: bash tools/m11/ldfix/value_flow_5243_e2e.sh     環境変数: M11_WORK (既定 tools/m11/work) / PY / RUNNER_TEMP
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="${M11_WORK:-$HERE/../work}"
OUT="${RUNNER_TEMP:-/tmp}/value_flow_5243"; mkdir -p "$OUT"
PY="${PY:-python3}"
IR="$W/boot_final3.ll"; IMG="$W/m11_image.bin"; CFG="$W/boot*.drc.config.json"
step() { echo "[value_flow_5243_e2e] $*"; }

step "1/3 audit (修復前)"
"$PY" "$HERE/audit_lsf_ssa.py" "$IR" "$IMG" "$CFG" --json "$OUT/ssa_base.json" | head -1 || exit 1
n=2
for r in base rmw; do
  step "$n/3 value_flow ($r)"
  n=$((n + 1))
  AUDIT_JSON="$OUT/ssa_base.json" "$PY" "$HERE/value_flow_5243.py" "$IR" "$IMG" "$CFG" --use-rule "$r" --json "$OUT/vf_$r.json" | head -1 || exit 1
done
"$PY" - "$OUT" <<'EOF'
import json, sys, collections
O = sys.argv[1]
b = json.load(open(O + '/vf_base.json')); r = json.load(open(O + '/vf_rmw.json'))
key = lambda x: (x['fn'], x['k'], x['blk'], x['ir'])
bs = {key(x) for x in b}; rs = {key(x) for x in r}
print('[value_flow_5243_e2e] base=%d rmw=%d added=%d removed=%d' % (len(bs), len(rs), len(rs - bs), len(bs - rs)))
print('[value_flow_5243_e2e] ir_use(rmw)=%s' % dict(collections.Counter(x['ir_use'] for x in r)))
EOF
