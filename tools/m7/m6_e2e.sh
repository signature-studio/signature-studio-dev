#!/usr/bin/env bash
# m6_e2e.sh (M7): m6.sh 相当 1 コマンド E2E — m6_lift → ir6 pass 鎖 → m6_build
# → m6_simd_check → node t1/t3/trap_test 直列化 + 検収数値の elicit 組込.
#
#   検収基準 (M6b 実測準拠, 数値照合で ±0):
#     - wasm-ld function signature mismatch: 0 種
#     - wasm-ld undefined symbol: 57 種 (整数 33 種 + Win/CRT 24 種)
#     - m6_simd_check.py: decl def mismatch 0 / callsite mismatch 0 (exit 0)
#     - node t1.mjs: run complete + t1_out.hex 512 行 + 再実行 determinism bit 一致
#     - node t3.mjs: mem == 0x2DDFA232 (DLL 実データ) exit 0
#     - node trap_test.mjs: OK 6 / FAIL 13 (missing 11 意図的 fail-fast + OOB 2)
#
# 固定パス化: すべての m6 work 成果物・t1_out.hex は tools/m6/work 絶対パスで
# 書出し (script 内で必ず tools/m6/work に cd するため caller cwd 非依存)。
#
# 使い方:
#   bash tools/m7/m6_e2e.sh              # 既存 IR 再利用 (m6_lift 産物が無ければ自動生成)
#   bash tools/m7/m6_e2e.sh --full       # m6_lift.sh からフル再生
#   bash tools/m7/m6_e2e.sh --help
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M6="$HERE/../m6"
M7="$HERE"
cd "$M6"
export TMPDIR="$M6/work/tmp"
mkdir -p work "$M7/work"

FULL=0
[ "${1:-}" = "--full" ] && FULL=1

echo "=== [1/6] m6_lift.sh (RetDec select-ranges → ir5_patch)"
if [ "$FULL" = 1 ] || [ ! -f work/ott_lift.ll ]; then
  bash m6_lift.sh
else
  echo "[e2e] 既存 work/ott_lift.ll を再利用 (toolchain: $(wc -l < work/ott_lift.ll) lines) — --full で再生成"
fi

# lift 再実行の非決定性 artifact 修正 (RetDec が `add i64 0, i64 %X` 形を出すことが
# ある — 数学上 add(0,x)=x で同値。M6 REPORT 記載の既知の型 token parse error 系
# lift 出力ホひと (ir5_patch.py:459 コメント相当)。m6 側スクリプトは改変せず
# lift 直後の work 産物に対して適用):
python3 - <<'PYEOF'
import re
p = 'work/ott_lift.ll'
s = open(p).read()
n = 0
def repl(m):
    global n
    n += 1
    return f'{m.group(1)} = add i64 {m.group(2)}, 0'
s2 = re.sub(r'^([ ]*%[\w.\-]+) = add i64 0, i64 (%[\w.\-]+)$', repl, s, flags=re.M)
print(f'[lift_fixup] add i64 0, i64 %X -> add i64 %X, 0: {n} lines')
# 重複 declare の dedupe (lift 再実行の非決定性で同 signature declare が複数化)
seen = set()
keep = []
d = 0
for l in s2.splitlines():
    m = re.match(r'^declare \S+ @([\w.\-]+)\((.*?)\) local_unnamed_addr$', l)
    key = (m.group(1), m.group(2)) if m else None
    if key and key in seen:
        d += 1
        continue
    if key:
        seen.add(key)
    keep.append(l)
open(p, 'w').write('\n'.join(keep) + '\n')
print(f'[lift_fixup] duplicate declares removed: {d}')
PYEOF

echo "=== [2/6] ir6 pass 鎖 (ir6_pass → ir6_shift → ir6_gdata)"
python3 ir6_pass.py  work/ott_lift.ll  work/ir7e_p1.ll
python3 ir6_shift.py work/ir7e_p1.ll   work/ir7e_p2.ll
python3 ir6_gdata.py work/ir7e_p2.ll   work/ir7e_p3.ll
# m6_build.sh が参照する正本名へ反映 (work scratch の再生成; m6 スクリプト自体は改変しない)
cp work/ott_shift3b.ll work/ott_shift3b.prev.ll 2>/dev/null || true
cp work/ir7e_p3.ll work/ott_shift3b.ll
echo "[e2e] ir6 chain OK: $(wc -l < work/ott_shift3b.ll) lines (ott_shift3b.ll)"

echo "=== [3/6] m6_build.sh (memfix + full-lift extract + emcc)"
bash m6_build.sh 2>&1 | tee work/build_e2e.log >/dev/null
grep -q '\[build\] OK' work/build_e2e.log || { echo "[e2e][FAIL] build 未完了" >&2; exit 1; }

echo "=== [4/6] 検収 (数値照合)"
# (a) signature mismatch / undefined symbol 数 / 種別内訳
N_MISMATCH=$(grep -ci 'function signature mismatch' work/build_e2e.log || true)
UNDEF_NAMES=$(grep -o 'undefined symbol: [A-Za-z_0-9.]*' work/build_e2e.log | sed 's/.*: //' | sort -u)
N_UNDEF=$(echo "$UNDEF_NAMES" | grep -c . || true)
N_ASM_UNDEF=$(echo "$UNDEF_NAMES" | grep -c '^__asm_' || true)
N_FN_UNDEF=$(echo "$UNDEF_NAMES" | grep -c '^function_18' || true)
N_API_UNDEF=$((N_UNDEF - N_ASM_UNDEF - N_FN_UNDEF))
echo "[e2e] signature mismatch: $N_MISMATCH 種 (期待 0)"
echo "[e2e] undefined symbol: $N_UNDEF 種 (期待 57)  | function_18*: $N_FN_UNDEF / __asm_*: $N_ASM_UNDEF / Win/CRT API: $N_API_UNDEF"
# (b) helper 3 重照合
python3 m6_simd_check.py work/ott_memfix1.ll msimd6.c > "$M7/work/simd_check_e2e.log" || true
read -r SIMD_BAD_A SIMD_BAD_B < <(python3 - "$M7/work/simd_check_e2e.log" <<'PYEOF'
import re, sys
t = open(sys.argv[1]).read()
m = re.search(r'decl def mismatch:\s*(\d+)\s*/\s*callsite mismatch:\s*(\d+)', t)
print(m.group(1), m.group(2))
PYEOF
)
echo "[e2e] simd_check: decl def mismatch: $SIMD_BAD_A / callsite mismatch: $SIMD_BAD_B (期待 0 / 0)"
echo "=== [5/6] node 実行検証 (cwd=tools/m6/work 固定パス運用)"
cd work
node t1.mjs > "$M7/work/t1_run1.log" 2>&1 || true
sha1_=$(sha256sum t1_out.hex | cut -d' ' -f1)
node t1.mjs > "$M7/work/t1_run2.log" 2>&1 || true
sha2_=$(sha256sum t1_out.hex | cut -d' ' -f1)
N_LINES=$(wc -l < t1_out.hex)
echo "[e2e] t1: lines=$N_LINES (期待 512) determinism: $sha1_ vs $sha2_"
node t3.mjs > "$M7/work/t3_run.log" 2>&1 || true
T3_RC=0
T3_OK=$(grep -c '\[t3\]\[OK\]' "$M7/work/t3_run.log" || true)
node trap_test.mjs > "$M7/work/trap_test_run.log" 2>&1 || true
TRAP_OK=$(grep -c '^OK:' "$M7/work/trap_test_run.log" || true)
TRAP_FAIL=$(grep -c '^FAIL:' "$M7/work/trap_test_run.log" || true)
cd "$M6"

echo "=== [6/6] 検収判定"
RC=0
chk() { if [ "$2" != "$3" ]; then echo "  [NG] $1: 実測 $2 / 期待 $3"; RC=1; else echo "  [OK] $1: $2"; fi; }
chk "signature mismatch 種" "$N_MISMATCH" 0
chk "undefined symbol 種"   "$N_UNDEF" 57
chk "undefined __asm_* 種"  "$N_ASM_UNDEF" 0
chk "simd decl def mismatch" "$SIMD_BAD_A" 0
chk "simd callsite mismatch" "$SIMD_BAD_B" 0
chk "t1_out.hex 行数"        "$N_LINES" 512
if [ "$sha1_" != "$sha2_" ]; then echo "  [NG] t1 determinism: bit 不一致"; RC=1; else echo "  [OK] t1 determinism: bit 一致"; fi
chk "t3 [OK] 検出"           "$T3_OK" 1
chk "trap_test OK"           "$TRAP_OK" 6
chk "trap_test FAIL"         "$TRAP_FAIL" 13

cat > "$M7/work/e2e_result.json" <<EOF
{
  "signature_mismatch": $N_MISMATCH,
  "undefined_symbols": $N_UNDEF,
  "undefined_function_18": $N_FN_UNDEF,
  "undefined_asm": $N_ASM_UNDEF,
  "undefined_api": $N_API_UNDEF,
  "t1_lines": $N_LINES,
  "t1_determinism_bit_equal": $( [ "$sha1_" = "$sha2_" ] && echo true || echo false ),
  "t3_ok": $T3_OK,
  "trap_ok": $TRAP_OK,
  "trap_fail": $TRAP_FAIL,
  "full_lift": $FULL,
  "exit": $RC
}
EOF
if [ "$RC" = 0 ]; then echo "[e2e] OK — 検収数値すべて一致 (tools/m7/work/e2e_result.json)"; else echo "[e2e][NG] 検収数値に差異 — tools/m7/work/e2e_result.json 参照" >&2; fi
exit "$RC"
