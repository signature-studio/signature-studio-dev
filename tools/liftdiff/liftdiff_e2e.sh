#!/usr/bin/env bash
# liftdiff 1 コマンド再現:
#   1) native ランナ + target(m11, ott_old) の wasm をビルド
#   2) OTT 旧 RetDec chain の既知欠陥 D1〜D6 を関数単位差分で検出 (tests/check_ott.py)
#   3) M11 boot 状態 (native で unit 0..16 実行) を作り、unit #18 周辺 (455790→44bb70→446400→4133f0 _UStrAsg) の原因を特定 (tests/check_unit18.py)
#   4) M11 closure (7,421 関数) の差分バッチ → 一致/不一致/実行不能 + 類型別集計
# 使い方: bash tools/liftdiff/liftdiff_e2e.sh [--full]   既定は closure の代表 800 関数 (約 1 分)、--full は全数 (約 8 分)
# 前提: tools/m11/work/{boot_final3.ll,boot_final.ll,m11_image.bin} (bash tools/m11/m11_e2e.sh --full で生成), tools/ott/work/ott.ll (bash tools/ott/ott_build.sh)
set -euo pipefail
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
mkdir -p work/m11 work/ott_old work/tmp
SET="sample:800"
[ "${1:-}" = "--full" ] && SET="closure"
echo "== [1/4] build"
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
python3 liftdiff.py build targets/m11.json >/dev/null
python3 liftdiff.py build targets/ott_old.json >/dev/null
echo "== [2/4] OTT 旧 chain: 欠陥 D1〜D6 の検出"
python3 liftdiff.py batch targets/ott_old.json --set closure --shards 4 --nobuild --out work/ott_old/batch.jsonl | tail -22
python3 tests/check_ott.py | tee work/ott_old/check.txt
echo "== [3/4] M11 unit #18 の原因特定 (boot 状態 = native unit 0..16)"
python3 liftdiff.py bootstate targets/m11.json --nobuild
python3 tests/check_unit18.py | tee work/m11/unit18.txt | tail -1 | head -c 400; echo
python3 - <<'PY'
import json
d = json.loads([l for l in open('work/m11/unit18.txt') if l.startswith('UNIT18_SUMMARY')][0].split(' ', 1)[1])
def need(c, m):
    print(('PASS ' if c else 'FAIL ') + m)
    if not c:
        raise SystemExit(1)
u = d['UStrAsg(dest->P[refcnt 2], src=0)']
need(u['outcome'] == 'diff' and 'mem' in u['diffs'], '_UStrAsg: 旧値(dest が保持する文字列)の解放が native と異なる (mem diff)')
mv = d['Move(src,dst,8)']
need(mv['outcome'] == 'diff' and 'spill_slot_deref' in mv['tags'], 'Delphi Move(409c80): [rcx] が spill alloca を直接読む (spill_slot_deref)')
rs = d['4123c0(resourcestring init loop)']
need(rs['outcome'] == 'diff' and rs['native_trace'] > 10 and rs['wasm_trace'] <= 6, '4123c0: resourcestring 初期化ループが wasm で脱落 (native entry %s / wasm %s)' % (rs['native_trace'], rs['wasm_trace']))
PY
echo "== [4/4] M11 closure 差分バッチ ($SET)"
python3 liftdiff.py batch targets/m11.json --set "$SET" --shards 12 --nobuild --state auto --out work/m11/batch_${SET//[:]/_}.jsonl | tail -30
echo "LIFTDIFF_E2E PASS"
