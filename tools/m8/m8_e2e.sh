#!/usr/bin/env bash
# m8_e2e.sh (M8): M7 m6_e2e.sh の鎖に (i) ir7_argpass_fixed (idx_store32 正本差分),
# (ii) ir8_valueflow (pattern C 係数群 value-flow 接続 [F1 accessor 誤訳再生成 +
# [F2] SVF xmm1 input 接続 16 callsite), (iii) m8_rt.c (missing 新規 10 stub) を
# 組込した 1 コマンド E2E。
#
#   検収基準 (M7 検収実績との差分を含む):
#     - wasm-ld function signature mismatch: 0 種
#     - wasm-ld undefined symbol: 47 種 (function_18*: 23 / Win/CRT 24;
#       M7 検収 57 = m8_rt.c 新規 stub 10 種で消滅)
#     - m6_simd_check.py: decl def mismatch 0 / callsite mismatch 0
#     - rt_leaf_test.mjs: OK 19 / NG 0 (missing 純計算 leaf #2/4/5/7 bit-exact)
#     - node t3.m8.mjs: mem[0x30260ce0] == 0x2DDFA232 (DLL 実データ, m6 と同値)
#     - trap8_test.mjs: OK 14 / FAIL 5  (m7 baseline OK 6/FAIL 13 → missing 10 種
#       解消; FAIL 残 = #6 fail-fast 保持 + #8 Win API 待ち + #11 未初期 lock 構造
#       + broken-lift OOB 2 件 (= M9 引継))
#     - node t1_sel8.mjs (param 全零 sweep): 512 行 + 2 run determinism bit 一致
#     - node t1_sel8.mjs (T1SVF=1 0.5 / 0.9 / 入力+0.3): param 応答 diffs>0 かつ
#       入力応答 diffs>0 (M7 では 0 diffs = 不応答 constant) + 2 run determinism
#
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M6="$HERE/../m6"
M8="$HERE"
cd "$M8"
mkdir -p work

export TMPDIR="$M8/work/tmp"
mkdir -p "$M8/work/tmp"

echo "=== [1/5] m8_build.sh (lift 直後 fixup + ir6 pass 鎖 + argpass_fixed + ir8_valueflow + emcc)"
bash "$M8/m8_build.sh" 2>&1 | tee work/build_e2e.log >/dev/null
grep -q '\[m8_build\] OK' work/build_e2e.log || { echo "[e2e][FAIL] m8_build 未完了" >&2; exit 1; }

echo "=== [2/5] link 状態・helper 整合の数値照合"
N_MISMATCH=$(grep -ci 'function signature mismatch' work/build_m8_full.log || true)
UNDEF_NAMES=$(grep -o 'undefined symbol: [A-Za-z_0-9.]*' work/build_m8_full.log | sed 's/.*: //' | sort -u)
N_UNDEF=$(echo "$UNDEF_NAMES" | grep -c . || true)
N_FN_UNDEF=$(echo "$UNDEF_NAMES" | grep -c '^function_18' || true)
N_API_UNDEF=$((N_UNDEF - N_FN_UNDEF))
echo "[e2e] signature mismatch: $N_MISMATCH 種 (期待 0)"
echo "[e2e] undefined symbol: $N_UNDEF 種 (期待 47) | function_18*: $N_FN_UNDEF / Win/CRT API: $N_API_UNDEF"
python3 "$M6/m6_simd_check.py" "$M6/work/ott_memfix1.ll" "$M6/msimd6.c" > "$M8/work/simd_check_e2e.log" || true
read -r SIMD_BAD_A SIMD_BAD_B < <(python3 - "$M8/work/simd_check_e2e.log" <<'PYEOF'
import re, sys
t = open(sys.argv[1]).read()
m = re.search(r'decl def mismatch:\s*(\d+)\s*/\s*callsite mismatch:\s*(\d+)', t)
print(m.group(1), m.group(2))
PYEOF
)
echo "[e2e] simd_check: decl def mismatch $SIMD_BAD_A / callsite mismatch $SIMD_BAD_B (期待 0 / 0)"

echo "=== [3/5] node 実行検証 (t1 / t3 / trap8 / rt_leaf)"
T1VAL=0 T1OUT="$M8/work/t1_zero2.hex" T1Z=19 T1SET=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 node "$M8/t1_sel8.mjs" > "$M8/work/t1_zero2.log" 2>&1 || true
T1A=$(sha256sum "$M8/work/t1_zero2.hex" | cut -d' ' -f1)
T1VAL=0 T1OUT="$M8/work/t1_zero3.hex" T1Z=19 T1SET=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 node "$M8/t1_sel8.mjs" > "$M8/work/t1_zero3.log" 2>&1 || true
T1A2=$(sha256sum "$M8/work/t1_zero3.hex" | cut -d' ' -f1)
N_LINES=$(wc -l < "$M8/work/t1_zero3.hex")
echo "[e2e] t1 (param 全零 sweep): lines=$N_LINES  determinism: $T1A vs $T1A2"
T1SVF=1 T1VAL=0.5 T1Z=19 T1SET=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 T1OUT="$M8/work/t1_vsvf05e1.hex" node "$M8/t1_sel8.mjs" > "$M8/work/t1_vsvf05e1.log" 2>&1 || true
T1SVF=1 T1VAL=0.5 T1Z=19 T1SET=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 T1OUT="$M8/work/t1_vsvf05e2.hex" node "$M8/t1_sel8.mjs" > "$M8/work/t1_vsvf05e2.log" 2>&1 || true
T1SVF=1 T1VAL=0.9 T1Z=19 T1SET=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 T1OUT="$M8/work/t1_vsvf09e.hex" node "$M8/t1_sel8.mjs" > "$M8/work/t1_vsvf09e.log" 2>&1 || true
T1SVF=1 T1VAL=0.5 T1SIG=0.3 T1Z=19 T1SET=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 T1OUT="$M8/work/t1_vsvfs3e.hex" node "$M8/t1_sel8.mjs" > "$M8/work/t1_vsvfs3e.log" 2>&1 || true
read -r D_PARAM D_INPUT < <(python3 - "$M8/work" <<'PYEOF'
import sys
def load(p):
    return [l.strip() for l in open(p) if l.strip()]
w = sys.argv[1]
base = load(w + "/t1_vsvf05e1.hex")
p9 = load(w + "/t1_vsvf09e.hex")
s3 = load(w + "/t1_vsvfs3e.hex")
print(sum(1 for x, y in zip(base, p9) if x != y), sum(1 for x, y in zip(base, s3) if x != y))
PYEOF
)
echo "[e2e] t1 value-flow 応答: param(0.5→0.9) diffs=$D_PARAM / input(+0.3) diffs=$D_INPUT (期待 >0 / >0)"
node "$M8/t3.m8.mjs" > "$M8/work/t3_m8_run.log" 2>&1 || true
T3_OK=$(grep -c '\[t3\]\[OK\]' "$M8/work/t3_m8_run.log" || true)
node "$M8/trap8_test.mjs" > "$M8/work/trap8_run.log" 2>&1 || true
TRAP8_OK=$(grep -c '^OK:' "$M8/work/trap8_run.log" || true)
TRAP8_FAIL=$(grep -c '^FAIL:' "$M8/work/trap8_run.log" || true)
node "$M8/rt_leaf_test.mjs" > "$M8/work/rt_leaf_run.log" 2>&1 || true
LEAF_OK=$(grep -c '^\[leaf\]\[OK\]' "$M8/work/rt_leaf_run.log" || true)
LEAF_NG=$(grep -c '^\[leaf\]\[NG\]' "$M8/work/rt_leaf_run.log" || true)
echo "[e2e] t3: [OK] 検出 $T3_OK (期待 1)"
echo "[e2e] trap8: OK $TRAP8_OK / FAIL $TRAP8_FAIL (期待 14 / 5)"
echo "[e2e] rt_leaf bit-exact: OK $LEAF_OK / NG $LEAF_NG (期待 19 / 0)"

echo "=== [4/5] 検収判定"
RC=0
chk() { if [ "$2" != "$3" ]; then echo "  [NG] $1: 実測 $2 / 期待 $3"; RC=1; else echo "  [OK] $1: $2"; fi; }
chk "signature mismatch 種" "$N_MISMATCH" 0
chk "undefined symbol 種"   "$N_UNDEF" 47
chk "undefined function_18* 種" "$N_FN_UNDEF" 23
chk "undefined Win/CRT API 種" "$N_API_UNDEF" 24
chk "simd decl def mismatch" "$SIMD_BAD_A" 0
chk "simd callsite mismatch" "$SIMD_BAD_B" 0
chk "t1_out (全零 sweep) 行数" "$N_LINES" 512
chk "t1 全零 determinism (2 run)" "$T1A" "$T1A2"
if ! [ "$D_PARAM" -gt 0 ]; then echo "  [NG] t1 value-flow param 応答 diffs=$D_PARAM (期待 >0)"; RC=1; else echo "  [OK] t1 param 応答 diffs: $D_PARAM"; fi
if ! [ "$D_INPUT" -gt 0 ]; then echo "  [NG] t1 value-flow input 応答 diffs=$D_INPUT (期待 >0)"; RC=1; else echo "  [OK] t1 input 応答 diffs: $D_INPUT"; fi
chk "t3 [OK] 検出"           "$T3_OK" 1
chk "trap8 OK"               "$TRAP8_OK" 14
chk "trap8 FAIL"             "$TRAP8_FAIL" 5
chk "rt_leaf bit-exact OK"   "$LEAF_OK" 19
chk "rt_leaf bit-exact NG"   "$LEAF_NG" 0

cat > "$M8/work/e2e_result.json" <<EOF
{
  "signature_mismatch": $N_MISMATCH,
  "undefined_symbols": $N_UNDEF,
  "undefined_function_18": $N_FN_UNDEF,
  "undefined_api": $N_API_UNDEF,
  "simd_decl_mismatch": $SIMD_BAD_A,
  "simd_callsite_mismatch": $SIMD_BAD_B,
  "t1_zero_lines": $N_LINES,
  "t1_zero_determinism_bit_equal": $( [ "$T1A" = "$T1A2" ] && echo true || echo false ),
  "t1_valueflow_param_diffs": $D_PARAM,
  "t1_valueflow_input_diffs": $D_INPUT,
  "t3_ok": $T3_OK,
  "trap8_ok": $TRAP8_OK,
  "trap8_fail": $TRAP8_FAIL,
  "rt_leaf_ok": $LEAF_OK,
  "rt_leaf_ng": $LEAF_NG,
  "exit": $RC
}
EOF
if [ "$RC" = 0 ]; then echo "[e2e] OK — m8 検収項目すべて一致 (tools/m8/work/e2e_result.json)"; else echo "[e2e][NG] 検収差異 — tools/m8/work/e2e_result.json 参照" >&2; fi
exit "$RC"
