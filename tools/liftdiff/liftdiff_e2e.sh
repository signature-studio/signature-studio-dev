#!/usr/bin/env bash
# liftdiff 1 コマンド再現:
#   1) native ランナ + target(m11, ott_old) の wasm をビルド
#   2) OTT 旧 RetDec chain の既知欠陥 D1〜D6 を関数単位差分で検出 (tests/check_ott.py)
#   3) M11 boot 状態 (native で unit 0..16 実行) を作り、unit #18 周辺 (455790→44bb70→446400→4133f0 _UStrAsg) の原因を特定 (tests/check_unit18.py)
#   4) M11 closure (7,421 関数) の差分バッチ → 一致/不一致/実行不能 + 類型別集計
# 使い方: bash tools/liftdiff/liftdiff_e2e.sh [--full] [--m11-only]   既定は closure の代表 800 関数、--full は全数
#   --m11-only: OTT 旧 chain ([1/4] の ott_old build と [2/4]) を省略 (素材 work-m6-ott / analysis-ott-binaries が無い環境用)
# 素材 (Actions): oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff [+ OTT 検証には work-m6-ott analysis-ott-binaries]
# python 依存: numpy capstone pefile (PATH 上の python3 に必要)。FL_WIN64_DIR は tools/shared/paths.py 経由で解決
# 前提: tools/m11/work/{boot_final3.ll,boot_final.ll,m11_image.bin} (bash tools/m11/m11_e2e.sh --full で生成), tools/ott/work/ott.ll (bash tools/ott/ott_build.sh)
set -euo pipefail
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
mkdir -p work/m11 work/ott_old work/tmp
SET="sample:800"
M11_ONLY=0
for a in "$@"; do
  case "$a" in
    --full) SET="closure" ;;
    --m11-only) M11_ONLY=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done
python3 -c 'import numpy, capstone, pefile' 2>/dev/null || { echo "missing python deps: numpy capstone pefile" >&2; exit 2; }
need() { [ -e "$1" ] || { echo "missing input: $1 ($2)" >&2; exit 2; }; }
need ../m11/work/boot_final3.ll "oc_artifacts: work-m11"
need ../m11/work/m11_image.bin "oc_artifacts: work-m11"
[ "$M11_ONLY" = 1 ] || need ../ott/work/ott.ll "oc_artifacts: work-m6-ott (or --m11-only)"
echo "== [0/4] LD-288 の入口 xmm0 修正 IR を生成 (targets/m11.json の ir。40c420 の入力を復元)"
python3 tests/ld288_40c420_xmm0.py "$FL_WIN64_DIR/extracted/block00031_PE.bin" ../m11/work/boot_final3.ll work/ld288/boot3_40c420_tr.ll
echo "== [0/4] build (単体テストの p= 実測 (LD-259) が wasm を要るため、テストより先に作る)"
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
python3 liftdiff.py build targets/m11.json >/dev/null
echo "== [0/4] 比較系の単体テスト (LD-11 / #548: cmp_mem byte 単位・wasm timeout の別 outcome。ネガコン込み。失敗で set -e により中断)"
python3 tests/test_compare_ld11.py
python3 tests/test_ld52_machine_sig.py
python3 tests/test_ld200_struct_stub.py
python3 tests/test_ld181_i128_entry.py
python3 tests/test_ld248_i128_xmm_entry.py
python3 tests/test_ld179_tagpoint_tr.py
python3 tests/test_ld203_slot_fill.py
python3 tests/test_ld225_sample_vmo.py
python3 tests/test_ld259_patch_p.py
if [ "$M11_ONLY" = 0 ]; then
python3 liftdiff.py build targets/ott_old.json >/dev/null
echo "== [2/4] OTT 旧 chain: 欠陥 D1〜D6 の検出"
python3 liftdiff.py batch targets/ott_old.json --set closure --shards 4 --nobuild --out work/ott_old/batch.jsonl | tail -22
python3 tests/check_ott.py | tee work/ott_old/check.txt
bash tests/nc_check_ott.sh   # ネガコン: D1/D2/D3/D6 のタグを 1 系統ずつ除くと check_ott.py が exit 1 になること
else
echo "== [2/4] OTT 旧 chain: skipped (--m11-only)"
fi
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
need(rs['outcome'] == 'diff' and rs['native_trace'] > rs['wasm_trace'] and 'callsite_arg_drop' in rs['tags'] and rs['diffs'].get('mem', {}).get('count', 0) > 0, '4123c0: resourcestring 初期化が wasm で脱落 (native entry %s > wasm %s, callsite_arg_drop, mem diff %s)' % (rs['native_trace'], rs['wasm_trace'], rs['diffs'].get('mem', {}).get('count')))
PY
echo "== [3b/4] InitUnits の空振り一致検出 (LD-25 / #977: InitTable 充足の boot 状態で空振りが出ないこと)"
python3 tests/check_initunits.py --json work/m11/initunits.json
echo "== [4/4] M11 closure 差分バッチ ($SET)"
python3 liftdiff.py batch targets/m11.json --set "$SET" --shards 12 --nobuild --state auto --out work/m11/batch_${SET//[:]/_}.jsonl | tail -30
echo "LIFTDIFF_E2E PASS"
