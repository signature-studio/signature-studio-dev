#!/usr/bin/env bash
# H10 (#218) 1 コマンド検証: Fruity Wrapper の wrapper-chunk reader 解析の主張を機械検査する.
#   ① PE バイト検査 (capstone; fw_a=block19091, fw_b=block23676, FLEngine=block00031)  ② evidence 文面検査  ③ ネガティブコントロール 10 本
#   ④ typecheck  ⑤ reader 模型 test (生成 DB の .fst 5 件 + 実機 OTT.fst)
# 前提: fl-win64 素材 ($FL_WIN64_DIR/extracted/block19091_PE.bin, block23676_PE.bin)。Ghidra は不要 (evidence は commit 済み)。
# Ghidra で evidence を再生成: bash analysis/reproduce.sh
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck disable=SC1091
source ../../shared/env.sh
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
mkdir -p work
X="$FL_WIN64_DIR/extracted"
[ -f work/fw_a.dll ] || cp "$X/block19091_PE.bin" work/fw_a.dll
[ -f work/fw_b.dll ] || cp "$X/block23676_PE.bin" work/fw_b.dll
if [ ! -x work/venv/bin/python ]; then
  uv venv -q work/venv
  uv pip install -q --python work/venv/bin/python capstone pefile
fi
PY=work/venv/bin/python
t0=$(date +%s.%N); la0=$(cut -d' ' -f1-3 /proc/loadavg)
fail=0
step() { echo; echo "== $*"; }

step "PE bytes (capstone): fw_a + fw_b"
$PY analysis/h10_check.py work/fw_a.dll work/fw_b.dll --json work/h10_check.json | grep -E "^FAIL|SUMMARY" || true
$PY analysis/h10_check.py work/fw_a.dll work/fw_b.dll >/dev/null || { echo "FAIL: h10_check"; fail=1; }

step "FLEngine PE bytes (capstone): event 212 flags 0x10 / 0x80"
$PY analysis/fle_check.py "$X/block00031_PE.bin" | grep -E "^FAIL|SUMMARY" || true
$PY analysis/fle_check.py "$X/block00031_PE.bin" >/dev/null || { echo "FAIL: fle_check"; fail=1; }

step "evidence text (Ghidra decompile)"
python3 analysis/evidence_check.py evidence | grep -E "^FAIL|SUMMARY" || true
python3 analysis/evidence_check.py evidence >/dev/null || { echo "FAIL: evidence_check"; fail=1; }

step "negative controls (each must be DETECTED = the checker FAILs on the broken expectation)"
for b in rec57size ver ctor6 rec51; do
  if $PY analysis/h10_check.py work/fw_a.dll --break "$b" >/dev/null; then echo "detected  h10_check --break $b"; else echo "NOT DETECTED h10_check --break $b"; fail=1; fi
done
for b in flag80 caller type31; do
  if $PY analysis/fle_check.py "$X/block00031_PE.bin" --break "$b" >/dev/null; then echo "detected  fle_check --break $b"; else echo "NOT DETECTED fle_check --break $b"; fail=1; fi
done
for b in d4use callers ext; do
  if python3 analysis/evidence_check.py evidence --break "$b" >/dev/null; then echo "detected  evidence_check --break $b"; else echo "NOT DETECTED evidence_check --break $b"; fail=1; fi
done

step "typecheck"
../../../node_modules/.bin/tsc -p tsconfig.json && echo ok || { echo "FAIL: typecheck"; fail=1; }

step "reader model tests (node:test)"
node --test test/*.test.ts 2>&1 | grep -E "^# (tests|pass|fail|skipped)|^not ok" || true
node --test test/*.test.ts >/dev/null 2>&1 || { echo "FAIL: tests"; fail=1; }

t1=$(date +%s.%N)
echo; echo "elapsed $(echo "$t1 - $t0" | bc) s | load average start [$la0] end [$(cut -d' ' -f1-3 /proc/loadavg)] | exit $fail"
exit $fail
