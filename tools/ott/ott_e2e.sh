#!/usr/bin/env bash
# ott_e2e.sh — OTT (Xfer, VST2 win64) DSP: native 実機械語参照 vs 自作 lifter (x64c) wasm の bit-exact 検収 (1 コマンド)
#   bash tools/ott/ott_e2e.sh [--quick]
#   env: OTT_RECOVER=1   native 単歩 coverage を再取得 (約 90 秒, 既定は ref/cov_all.json)
#        OTT_ULP_TOL=k   出力 cell の許容 ulp (既定 0 = bit-exact)
#        OTT_SKIP_INFO=1 INFO 節 (FMA 感度 / 旧 RetDec chain before 値) を省略
# 判定 (exit 0 = PASS): scenario matrix の全 cell が native 機械語出力と |ulp| <= OTT_ULP_TOL (既定 0) かつ最終 state 差 0。
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$OTT"; mkdir -p work
NODE_BIN="$(command -v node || true)"
[ -n "$NODE_BIN" ] || NODE_BIN="$(ls /opt/emsdk/node/*/bin/node 2>/dev/null | head -1)"
[ -n "$NODE_BIN" ] || { echo "[ott_e2e] node 無し" >&2; exit 2; }
export NODE="$NODE_BIN" PATH="$(dirname "$NODE_BIN"):$PATH"
QUICK=""; [ "${1:-}" = "--quick" ] && QUICK="--quick"
python3 -c "import capstone, pefile" 2>/dev/null || { echo "[ott_e2e] python: capstone/pefile が必要 (pip install capstone pefile)" >&2; exit 2; }
DLL=/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
[ -f "$DLL" ] || { echo "[ott_e2e] $DLL 無し" >&2; exit 2; }

echo "[1/6] native 参照ローダ build (PE を 0x180000000 に敷設, 実機械語を MS x64 ABI で直接実行)"
bash native/build.sh 2>&1 | grep -v "warning\|\^\|write(2\|^ *[0-9]* |" || true
echo "[2/6] coverage: native 単歩実行で実行された関数 entry を取得"
if [ "${OTT_RECOVER:-0}" = "1" ]; then python3 diff/cov_nat.py ref/cov_all.json 2>&1 | grep -v "stack\[\|SIGSEGV" | tail -4; fi
python3 lift/mkentries.py ref/cov_all.json work/entries.json
echo "[3/6] lift: 機械語 → C (x64c, capstone) → emcc → wasm"
LIFT_OUT="$OTT/work/lift" bash lift/lift_build.sh 2>&1 | tail -3 | cut -c1-240
python3 - <<'PYEOF'
import json
m = json.load(open('work/lift/lift_meta.json'))
print('      lifted functions %d / instructions %d / overrides %d / 未 lift callee %d (実行されれば fail-fast)' % (len(m['functions']), m['ninsn'], len(m['overrides']), len(m['unlifted_callees'])))
print('      未対応 mnemonic (全て未実行の AVX/FMA 版 CRT 経路など; 実行時は ott_unsup で fail-fast): %d 種 / %d 箇所' % (len(m['unsup']), sum(m['unsup'].values())))
PYEOF
echo "[4/6] scenario matrix: wasm vs native 実機械語 (出力 bit + 最終 heap/obj state)"
RC=0
python3 diff/matrix.py "$OTT/work/lift/ottl.cjs" $QUICK > work/matrix.log 2>&1 || RC=1
grep -E '"name": "(std|std_f248_0)"' work/matrix.log | python3 -c "
import sys, json
for l in sys.stdin:
    r = json.loads(l); c = r['census']
    print('      %-11s ok=%s cells=%d bit-equal=%d max_ulp=%d census: zero %d / normal %d / junkHi %d / junkTiny %d / nan %d / |max| %.4g' % (r['name'], r['ok'], r['cells'], r['bit_equal'], r['max_ulp'], c['zero'], c['normal'], c['junkHi'], c['junkTiny'], c['nan'], r['absmax']))"
grep -E '^\{.*"ok": false' work/matrix.log | head -5 || true
tail -1 work/matrix.log

if [ "${OTT_SKIP_INFO:-0}" != "1" ]; then
  echo "[5/6] INFO: CRT の FMA3 経路 (__use_fma3 相当 flag) vs SSE2 経路の出力差 (native 実機械語, tolerance 設計用)"
  python3 diff/fma_sens.py | tail -1
  echo "[6/6] INFO: 旧 RetDec chain (M6-M10) の census = before 値 (同一 harness: M10 e2e_check)"
  if [ -f ../m6/work/ott_memfix1.ll ]; then
    OTT_OUT=ott bash ott_build.sh >/dev/null 2>&1 && MOD="$OTT/work/ott.cjs" node diff/old_census.mjs | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
for k in ('f248_0', 'f248_1'):
    c = d[k]; print('      RetDec chain [0x248]=%s: zero %d / normal %d / junkHi %d / junkTiny %d / nan %d / |max| %.4g' % (k[-1], c['zero'], c['normal'], c['junkHi'], c['junkTiny'], c['nan'], c['absmax']))" || echo "      (旧 chain build 失敗: スキップ)"
  else echo "      (tools/m6/work の RetDec 産物が無いためスキップ)"; fi
fi
[ "$RC" = "0" ] && echo "[ott_e2e] PASS" || echo "[ott_e2e] FAIL"
exit $RC
