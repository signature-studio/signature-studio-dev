#!/usr/bin/env bash
# PLG-F7 (#204) pitch-time 8 本の「lift 前提」実測 + 判定を 1 コマンドで再現する。
#   bash tools/plugins/pitch_time/pitch_time_e2e.sh [--skip-lift | --judge-only]
# 手順: inventory (work/ 無ければ生成) → 殻 7 本の閉包 → batch_lift → judge.py (gate) → closure_facts → matrix_check → ids_crosscheck
#       → C++ module 2 本 (Pitcher / Scratcher engine) の全 .pdata lift → judge.py --engines (gate)。 Newtone engine は §4 の通り未完のため gate に含めない
# 終了コード: 全ての gate が合格のときだけ 0。 どれか 1 つでも不合格なら非 0 で、最終行は [pitch_time_e2e] FAIL (OK 行は出ない)。
#   --skip-lift  : 既存の work/ の結果で判定と突合のみ (lift と C++ module の再測定は省く)。 status は $STATUS_CSV (既定 work/batch/status.csv) の最後の行
#   --judge-only : 殻の judge.py と C++ module の judge.py --engines だけ実行して終わる (最終行は [pitch_time_e2e] JUDGE-ONLY PASS)。
#                  入力は $STATUS_CSV / $CPP_CSV (既定 work/batch/status.csv / work/pitch_time/cpp.csv)。 判定の配線のネガコン用
# 出力: work/pitch_time/{status7.csv,facts.json,cpp.csv} (work/ は gitignore)
# 前提素材: fl-win64 / toolchain-retdec ([RETDEC]) / toolchain-emsdk ([EMSDK])  (docs/REFERENCES.md, docs/WORKFLOW.md §11)
set -euo pipefail
trap 'rc=$?; [ "$rc" = 0 ] || echo "[pitch_time_e2e] FAIL (exit $rc, line $LINENO)" >&2' EXIT
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
MODE=""
for a in "$@"; do
  case "$a" in --skip-lift|--judge-only) MODE="$a";; *) echo "usage: $0 [--skip-lift|--judge-only]" >&2; exit 2;; esac
done
# Fruity Scratcher / Fruity Vocoder / Gross Beat / Newtime / Newtone / Pitch Shifter / Vocodex (Delphi 殻)
SHELLS=(19071 19087 19098 19166 19217 19221 19270)
CPP=(19222 19072)   # Pitcher 本体 / Scratcher engine (Newtone engine 19216 は REPORT §4: RetDec が 1 chunk で終わらず未完)
mkdir -p work/pitch_time work/batch
CLOSURE_DIR="${CLOSURE_DIR:-work/closure}"; LL_DIR="${LL_DIR:-work/batch}"   # judge の欠落監査の入力 (batch_lift.sh / plugin_closure.py の出力先)
if [ -n "$MODE" ]; then
  STATUS_CSV="${STATUS_CSV:-work/batch/status.csv}"; CPP_CSV="${CPP_CSV:-work/pitch_time/cpp.csv}"
else
  STATUS_CSV=work/batch/status.csv; CPP_CSV=work/pitch_time/cpp.csv
fi

if [ "$MODE" != --judge-only ]; then
  if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
    python3 inventory/win_scan.py
    python3 pitch_time/mk_blockmap.py
    python3 inventory/win_funcs.py
    python3 inventory/win_unique.py > /dev/null
    python3 inventory/win_abi.py > /dev/null
  fi
  [ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null
  python3 lift/plugin_closure.py "${SHELLS[@]}"
fi

SINCE=1
if [ -z "$MODE" ]; then
  [ -f work/batch/status.csv ] && SINCE=$(wc -l < work/batch/status.csv) || SINCE=1   # 今回追記された行だけを判定する (前回の合格行で今回の失敗を隠さない)
  bash lift/batch_lift.sh "${SHELLS[@]}"
fi
OUTCSV=work/pitch_time/status7.csv
[ "$MODE" = --judge-only ] && OUTCSV=work/pitch_time/status7.judge_only.csv   # 合成 CSV の試験で本物の status7.csv を上書きしない
python3 pitch_time/judge.py "$STATUS_CSV" "${SHELLS[@]}" --closure-dir "$CLOSURE_DIR" --ll-dir "$LL_DIR" --since-line "$SINCE" --out "$OUTCSV"
if [ "$MODE" = --judge-only ]; then
  python3 pitch_time/judge.py --engines "$CPP_CSV" pitch_time/expected_cpp.csv "${CPP[@]}"
  echo "[pitch_time_e2e] JUDGE-ONLY PASS"; exit 0
fi

python3 pitch_time/closure_facts.py > work/pitch_time/facts.stdout.json 2> work/pitch_time/facts.err
python3 pitch_time/matrix_check.py
python3 pitch_time/ids_crosscheck.py

# C++ module (MSVC): 全 .pdata 関数を lift → emcc -c。 測定値を expected_cpp.csv と突合する (drift を gate にする)
if [ -z "$MODE" ]; then
  echo "block,pdata_funcs,chunks,lift_rc_max,defines,f80_funcs,unimpl_helpers,emcc_c_fail_chunks,fixcmp_patched,emcc_c_fail_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside" > work/pitch_time/cpp.csv
  for b in "${CPP[@]}"; do bash pitch_time/cpp_lift.sh "$b" 900 | tail -n 1 >> work/pitch_time/cpp.csv; done
  cat work/pitch_time/cpp.csv work/pitch_time/cpp*/c*/first_errors.txt
fi
python3 pitch_time/judge.py --engines "$CPP_CSV" pitch_time/expected_cpp.csv "${CPP[@]}"
echo "[pitch_time_e2e] OK: 殻 ${#SHELLS[@]}/${#SHELLS[@]} 合格 + matrix_check + ids_crosscheck + C++ module ${#CPP[@]} 本が expected_cpp.csv と一致 (work/pitch_time/)"
