#!/usr/bin/env bash
# PLG-G1 (#206) synth-simple + drum-synth 14 本 (13 本が Delphi 殻 12 block + MiniSynth 単体 C++ DLL) の「lift 前提」実測を 1 コマンドで再現する。
#   bash tools/plugins/g1/g1_e2e.sh [--skip-lift] [--skip-engines] [--judge-only]
# 手順: 前提 inventory (work/ 無ければ生成) → 12 閉包 → batch_lift (RetDec+pass 鎖 → emcc -c) → [gate 1: judge.py] → [gate 1b: define_audit.py]
#       → closure_facts.py → [gate 2: matrix_check.py] → [gate 3: ids_crosscheck.py] → [gate 4: icall_check.py] → C++ DLL 7 本の lift (参考; 形式のみ検査)
# どの gate も不合格なら非 0 で終了し、最終行の `[g1_e2e] OK` は出さない (set -e)。
# 出力: work/g1/{status12.csv,define_table.md,facts.json,cpp_facts.json,icall/,engines.csv} (work/ は gitignore)
# 鎖: 本測定は PLUG_ICALL=0 (間接 call 復元前の従来鎖) に固定する。 main の batch_lift.sh は既定 PLUG_ICALL=1 (#539) だが、既定鎖の測定は REPORT §6.1 (別 run)。
#     PLUG_ICALL=1 の status.csv (icall 列 = 1) は judge.py が不合格にする
# 環境変数: G1_STATUS_CSV = judge に渡す status.csv を差し替える (ネガティブコントロール用; 既定 work/batch/status.csv)
# 前提素材: fl-win64 / toolchain-retdec (/opt/retdec) / toolchain-emsdk (/opt/emsdk)  (docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
SKIP_LIFT=0; SKIP_ENG=0; JUDGE_ONLY=0
for a in "$@"; do
  case "$a" in
    --skip-lift) SKIP_LIFT=1 ;;
    --skip-engines) SKIP_ENG=1 ;;
    --judge-only) JUDGE_ONLY=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done
read -r -a BLOCKS <<< "$(python3 g1/common.py shells)"
read -r -a CPP <<< "$(python3 g1/common.py engines)"
mkdir -p work/g1
export PLUG_ICALL=0

bash g1/prep.sh
python3 lift/plugin_closure.py "${BLOCKS[@]}" > /dev/null
if [ "$SKIP_LIFT" = 0 ]; then
  rm -f work/batch/status.csv
  bash lift/batch_lift.sh "${BLOCKS[@]}"
fi

echo "== gate 1: judge (lift_rc / emcc -c / f80 / 未実装 helper / define 数)"
python3 g1/judge.py "${G1_STATUS_CSV:-work/batch/status.csv}" "${BLOCKS[@]}" --out work/g1/status12.csv
if [ "$JUDGE_ONLY" = 1 ]; then echo "[g1_e2e] judge-only: gate 1 のみ通過 (他の gate は未実行)"; exit 0; fi
echo "== gate 1b: 閉包の関数 1 つずつに define があるか (名前での検査)"
python3 g1/define_audit.py "${BLOCKS[@]}" | tee work/g1/define_table.md

python3 g1/closure_facts.py > work/g1/facts.stdout.json 2> work/g1/facts.err
echo "== gate 2: PLUGIN_MATRIX.json の lift 欄との突合"
python3 g1/matrix_check.py
echo "== gate 3: Dispatcher ID の別算法検算"
python3 g1/ids_crosscheck.py
echo "== gate 4: 間接 call の静的 site (audit_icall) と独立 sweep の一致 + IR の間接 call 数 (測定)"
python3 g1/icall_check.py "${BLOCKS[@]}" | tee work/g1/icall_table.md

# C++ DLL (engine 6 本 + MiniSynth 単体): 到達性の実測のみ。 emcc -c rc は合否に使わない (行の存在 / 数値形式は engine_check.py が検査する)
if [ "$SKIP_ENG" = 0 ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > work/g1/engines.csv
  for eb in "${CPP[@]}"; do bash g1/engine_lift.sh "$eb" 1500 | tail -n 1 >> work/g1/engines.csv; done
  python3 g1/engine_check.py work/g1/engines.csv "${CPP[@]}"
  cat work/g1/engines.csv
fi
echo "== 未解決の観測 (gate ではない。 件数のみ; 起票先は REPORT §10)"
python3 g1/findings.py
echo "[g1_e2e] OK: gate 1 / 1b / 2 / 3 / 4 と C++ DLL の形式検査が合格 (出力 work/g1/)"
