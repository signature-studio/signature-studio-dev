#!/usr/bin/env bash
# PLG-X (#210) host 統合 / big3p 12 本の「方針判断の根拠」と lift 前提の実測を 1 コマンドで再現する。
#   bash tools/plugins/hostx/hostx_e2e.sh [--skip-lift] [--skip-engines]
# 許可する未実装 helper は rep_stosb_memset のみ (memset へ写像可; plugins/REPORT.md §4.3 / #538)
# 手順: 前提 inventory (work/ 無ければ生成) → static_facts.py (18 モジュールの PE 外形/API/文字列) →
#       Delphi 殻 9 本の閉包 → batch_lift (RetDec+pass 鎖 → emcc -c) → 判定 (judge.py: 合格必須 7 本 / expect_state.py: 既知不合格 2 本の状態固定) →
#       icall_audit.py (間接 call 脱落) → closure_facts.py (host ID / クラス名 / 双子・engine 重なり) → matrix_check.py → ReWired f80 局所検証 → FL Mobile engine の窓 lift (参考)
# exit 0 = 合格必須 7 本が合格し、既知不合格 2 本が期待どおりの状態で、後続も完走
# 出力: work/hostx/{icall_audit.md,static.json,status_must.csv,status_known.csv,facts.json,engines.csv} (work/ は gitignore)
# 前提素材: fl-win64 / toolchain-retdec (/opt/retdec) / toolchain-emsdk (/opt/emsdk)  (docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
MUST=(19091 23676 19220 24155 23918 19244 23674)   # Wrapper(E) Wrapper(G) Patcher(E) Patcher(G) MIDI Out / Razer Chroma / Video Player
KNOWN=(24161 19304)                                # ReWired (f80 + 未実装 helper) / ZGE 殻 (T3; 1 MB 固有部)
ALL=("${MUST[@]}" "${KNOWN[@]}")
SKIP_LIFT=0; SKIP_ENG=0
for a in "$@"; do case "$a" in --skip-lift) SKIP_LIFT=1;; --skip-engines) SKIP_ENG=1;; esac; done
mkdir -p work/hostx

if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
  python3 inventory/win_scan.py
  python3 hostx/mk_blockmap.py
  python3 inventory/win_funcs.py
  python3 inventory/win_unique.py > /dev/null
  python3 inventory/win_abi.py > /dev/null
fi

python3 hostx/static_facts.py > work/hostx/static.md
python3 lift/plugin_closure.py "${ALL[@]}" > /dev/null
if [ "$SKIP_LIFT" = 0 ]; then
  bash lift/batch_lift.sh "${ALL[@]}"
fi

rc=0; python3 hostx/judge.py work/batch/status.csv "${MUST[@]}" --allow-unimpl rep_stosb_memset -o work/hostx/status_must.csv || rc=$?
[ "$rc" = 0 ] || { echo "[hostx_e2e] FAIL: 合格必須 7 本の判定が不合格 (judge.py rc=$rc)" >&2; exit "$rc"; }
python3 hostx/expect_state.py work/batch/status.csv "${KNOWN[@]}" -o work/hostx/status_known.csv

# 間接 call 監査 (icall §4 D1): 合格 7 本 + ReWired の閉包について、機械語の非 IAT 間接 call 数 vs lift 後 IR の間接 call 数 (judge は emcc -c 通過しか見ない)
python3 hostx/icall_audit.py "${MUST[@]}" 24161 | tee work/hostx/icall_audit.md
python3 hostx/xcheck_icall.py "${MUST[@]}" 24161 | tee work/hostx/icall_xcheck.txt

python3 hostx/closure_facts.py > work/hostx/facts.stdout.json 2> work/hostx/facts.err
python3 hostx/matrix_check.py

# ReWired の f80 2 関数: p0c の f80→f64 lowering を当てて emcc -c が通るか (局所検証)
bash hostx/rewired_f80.sh | tee work/hostx/rewired_f80.txt

# FL Studio Mobile 系 engine (C++ 6〜9 MB): 窓 lift の到達性だけ (全関数ではない)
if [ "$SKIP_LIFT" = 0 ] && [ "$SKIP_ENG" = 0 ]; then
  echo "block,window,start_index,funcs,bytes,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,lift_s,first_error" > work/hostx/engines.csv
  for eb in 18976 22444; do bash hostx/engine_sample.sh "$eb" 300 900 >> work/hostx/engines.csv; done
  cat work/hostx/engines.csv
fi
echo "[hostx_e2e] OK: work/hostx/{static.json,status_must.csv,status_known.csv,facts.json}"
