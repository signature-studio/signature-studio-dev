#!/usr/bin/env bash
# PLG-F5 (#202) modulation 8 本の「lift 前提」実測を 1 コマンドで再現する。
#   bash tools/plugins/modulation/modulation_e2e.sh [--skip-lift | --judge-only]
# 手順: 前提 inventory (work/ 無ければ生成) → 8 閉包 → batch_lift (RetDec+pass 鎖 → emcc -c) → judge.py (gate)
#       → closure_facts.py → matrix_check.py → ids_crosscheck.py → engine 4 本 (参考・判定外)
# exit 0 は「殻 8 本の judge / matrix_check / ids_crosscheck が全て合格し、engine 4 本の測定行が揃った」ことだけを意味する。
#   engine の `emcc -c` 結果は判定に含めない (最終行に件数を出す)。 どれかが不合格なら非 0 で終わり、最終の OK 行は出ない。
#   --skip-lift  : lift を再実行せず、既存の work/batch/status.csv の最終行で判定する (closure_facts 以降は実行する)
#   --judge-only : --skip-lift の判定だけ実行して終了 (STATUS_CSV=<path> で入力を差し替え可。 ネガティブコントロール用)
# 出力: work/modulation/{status8.csv,facts.json,engines.csv} (work/ は gitignore)
# 前提素材: fl-win64 / toolchain-retdec (/opt/retdec) / toolchain-emsdk (/opt/emsdk)  (docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
MODE="${1:-}"
case "$MODE" in ""|--skip-lift|--judge-only) ;; *) echo "usage: $0 [--skip-lift|--judge-only]" >&2; exit 2;; esac
# Frequency Shifter / Fruity Chorus / Fruity Flanger / Fruity Flangus / Fruity Phaser / Hyper Chorus / Vintage Chorus / Vintage Phaser
BLOCKS=(18978 18989 19007 19009 19066 19144 19265 19267)
BLOCKS_CSV="$(IFS=,; echo "${BLOCKS[*]}")"
ENGINES=(18977 19143 19266 19268)   # 上の殻と同順: Frequency Shifter / Hyper Chorus / Vintage Chorus / Vintage Phaser
STATUS="${STATUS_CSV:-work/batch/status.csv}"
S8=work/modulation/status8.csv; [ "$MODE" = "--judge-only" ] && S8=work/modulation/status8.judge.csv
mkdir -p work/modulation

if [ "$MODE" != "--judge-only" ]; then
  if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
    python3 inventory/win_scan.py
    python3 modulation/mk_blockmap.py
    python3 inventory/win_funcs.py
    python3 inventory/win_unique.py > /dev/null
    python3 inventory/win_abi.py > /dev/null
  fi
  [ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null
  python3 lift/plugin_closure.py "${BLOCKS[@]}"
fi

if [ -z "$MODE" ]; then
  # 前回の出力が残っていると RetDec 失敗が見えなくなる (lift_ranges.sh は drc.ll の存在だけを見る) ので block ごとに消す
  for b in "${BLOCKS[@]}"; do rm -rf "work/batch/$b"; done
  n0=1; [ -f work/batch/status.csv ] && n0=$(wc -l < work/batch/status.csv)
  bash lift/batch_lift.sh "${BLOCKS[@]}"
  # この実行で追記された行だけを判定対象にする (stale な行で合格させない)
  { head -n 1 work/batch/status.csv; tail -n +$((n0 + 1)) work/batch/status.csv; } > "$S8"
else
  echo "[modulation_e2e] $MODE: lift は再実行せず $STATUS の block ごとの最終行で判定する"
  cp "$STATUS" "$S8"
fi

python3 modulation/judge.py "$S8" --blocks "$BLOCKS_CSV" --batch-dir work/batch \
  || { echo "[modulation_e2e] FAIL: judge (殻 8 本のうち不合格あり)" >&2; exit 1; }
if [ "$MODE" = "--judge-only" ]; then echo "[modulation_e2e] judge-only: PASS"; exit 0; fi

python3 modulation/closure_facts.py > work/modulation/facts.stdout.json 2> work/modulation/facts.err
python3 modulation/matrix_check.py || { echo "[modulation_e2e] FAIL: matrix_check" >&2; exit 1; }
python3 modulation/ids_crosscheck.py || { echo "[modulation_e2e] FAIL: ids_crosscheck" >&2; exit 1; }

# C++ engine 4 本 (判定には含めない: 到達性の実測のみ。 ただし測定行が揃わなければ FAIL)
if [ "$MODE" != "--skip-lift" ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > work/modulation/engines.csv
  for eb in "${ENGINES[@]}"; do bash modulation/engine_lift.sh "$eb" 1500 | tail -n 1 >> work/modulation/engines.csv; done
  cat work/modulation/engines.csv work/modulation/engine*/first_errors.txt
fi
awk -F, -v n="${#ENGINES[@]}" 'NR > 1 { rows++; if (NF != 15) bad++ } END { exit !(rows == n && !bad) }' work/modulation/engines.csv \
  || { echo "[modulation_e2e] FAIL: engines.csv の測定行が ${#ENGINES[@]} 本分揃っていない" >&2; exit 1; }
ENG_OK=$(awk -F, 'NR > 1 && $7 == 0 { n++ } END { print n + 0 }' work/modulation/engines.csv)
echo "[modulation_e2e] shells: judge/matrix_check/ids_crosscheck 合格 (8/8 本)。 engines(参考・判定外): emcc -c rc=0 は $ENG_OK/${#ENGINES[@]} 本"
echo "[modulation_e2e] OK: work/modulation/{status8.csv,facts.json,engines.csv} elapsed=${SECONDS}s loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
