#!/usr/bin/env bash
# crt_e2e.sh — CAB-138 (OTT-T5) 1 コマンド検収。
#   [1] native coverage (CRT 経路, 約 1 分)  — CRT_COV_SKIP=1 で再利用
#   [2] lift → wasm (override 4 件を実機械語 lift に置換 + CRT api-set trampoline)
#   [3] 新 scenario matrix (9 本: float formatter / op34 / op7 / DSP エラー経路) 突合
#   [4] 既存 entry 85 scenario を CRT 版 build で全数再突合 (回帰)
#   [5] 陰性対照: OTT_CRTINIT=0 で旧 fail-fast (native SIGSEGV / wasm ott_unlifted, 同一 garbage VA) を再現
#   [6] 既存 e2e の継続性確認 (ott_e2e.sh = DSP 89 scenario / entry_e2e.sh = 85, 旧 build のまま)
#   出力: tools/ott/work/crtlift/
set -uo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
CRT="$OTT/crtinit"
OUT="$OTT/work/crtlift"
NODE="${NODE:-/opt/emsdk/node/24.19.0_64bit/bin/node}"
mkdir -p "$OUT"
FAIL=0

[ -f "$CRT/scen_crt.json" ] || python3 "$CRT/crt_scen.py" "$OUT/scen_crt.json"

# [1/6] は crt_nat.py が work/crtlift/libottnatcrt.so を必要とする。clean tree では
# まだ存在しないので、先に native 参照ハーネスだけ build する (lift_crt.sh [1/4] と同一)。
# 再実行時は既存 .so をそのまま使う。
[ -f "$OUT/libottnatcrt.so" ] || \
  gcc -O1 -g -fPIC -shared -o "$OUT/libottnatcrt.so" "$CRT/crt_native.c" "$OTT/native/ms_call.S" \
    -I"$OTT/rt" -I"$OTT/native" -I"$OTT/entry"

if [ "${CRT_COV_SKIP:-0}" != "1" ] || [ ! -f "$OUT/cov_crt.json" ]; then
  echo "[1/6] native coverage (CRT 経路 scenario 実行 + 単歩 coverage)"
  python3 -u "$CRT/crt_nat.py" --out "$OUT/nat_probe.json" --scen "$OUT/scen_crt.json" --cov "$OUT/cov_crt.json" 2>&1 | tail -2
else
  echo "[1/6] coverage 再利用 ($OUT/cov_crt.json)"
fi
if [ "${CRT_LIFT_SKIP:-0}" != "1" ] || [ ! -f "$OUT/ottl_crt.cjs" ]; then
  echo "[2/6] lift → wasm (CRT 初期化版)"
  bash "$CRT/lift_crt.sh" "$OUT/cov_crt.json" 2>&1 | grep -E "^\[|functions" | tail -3
else
  echo "[2/6] wasm 再利用 ($OUT/ottl_crt.cjs)"
fi

echo "[3/6] 新 scenario matrix (CRT 経路) — native 実機械語 vs lift wasm"
python3 -u "$CRT/run_matrix.py" "$OUT/ottl_crt.cjs" "$OUT/matrix" --scen "$OUT/scen_crt.json" 2>&1 | tail -2
python3 -u "$OTT/entry/cmp_entries.py" "$OUT/matrix/nat_result.json" "$OUT/matrix/wasm_result.json" \
  --out "$OUT/matrix/summary.json" || FAIL=1

echo "[4/6] 既存 entry 85 scenario を CRT 版 build で再突合 (回帰)"
python3 -u "$CRT/run_matrix.py" "$OUT/ottl_crt.cjs" "$OUT/matrix85" --scen "$OTT/work/entrylift/scen.json" 2>&1 | tail -2
python3 -u "$OTT/entry/cmp_entries.py" "$OUT/matrix85/nat_result.json" "$OUT/matrix85/wasm_result.json" \
  --out "$OUT/matrix85/summary.json" || FAIL=1

echo "[5/6] 陰性対照 (OTT_CRTINIT=0 → 旧 fail-fast の再現)"
NEG_N=0; NEG_W=0
OTT_CRTINIT=0 python3 -u "$CRT/crt_nat.py" --out "$OUT/nat_neg.json" --scen "$OUT/scen_crt.json" --only flt_disp_def > "$OUT/neg_nat.log" 2>&1 || true
grep -q "SIGSEGV" "$OUT/neg_nat.log" && grep -q "rax=0xae64b77e88c8000" "$OUT/neg_nat.log" && NEG_N=1
OTT_CRTINIT=0 MOD="$OUT/ottl_crt.cjs" SCEN="$OUT/scen_crt.json" NAME=flt_disp_def OUT="$OUT/w_neg.json" \
  "$NODE" "$CRT/crt_wasm.mjs" > "$OUT/neg_wasm.log" 2>&1 || true
grep -q "UNLIFTED function 0xae64b77e88c8000" "$OUT/neg_wasm.log" && NEG_W=1
echo "  native SIGSEGV(CFG garbage jump) 再現: $([ $NEG_N = 1 ] && echo OK || echo NG) / wasm ott_unlifted(同一 garbage VA) 再現: $([ $NEG_W = 1 ] && echo OK || echo NG)"
[ $NEG_N = 1 ] && [ $NEG_W = 1 ] || FAIL=1

echo "[6/6] 既存 e2e の継続性確認 (旧 build — 改変は lift/x64c.py の mxcsr のみ)"
bash "$OTT/ott_e2e.sh" 2>&1 | tail -2 || FAIL=1
bash "$OTT/entry/entry_e2e.sh" --quick 2>&1 | tail -2 || FAIL=1

if [ $FAIL = 0 ]; then
  echo "[crt_e2e] PASS"
else
  echo "[crt_e2e] FAIL"
fi
exit $FAIL
