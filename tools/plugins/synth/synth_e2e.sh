#!/usr/bin/env bash
# PLG-G2 (#207) synth 14 本の「lift 前提」実測を 1 コマンドで再現する。
#   bash tools/plugins/synth/synth_e2e.sh [--skip-lift]          (--skip-lift: 前回の lift 結果 work/ を再利用)
#   bash tools/plugins/synth/synth_e2e.sh --judge-only <status.csv>   (判定だけを任意の CSV に対して実行; ネガコン用)
# 手順: 前提 inventory (work/ 無ければ生成) → 対象導出 (targets.py) → shell 12 閉包 batch_lift → C++ DLL 9 本 cpp_lift
#       → mk_status.py → closure_facts.py → matrix_check.py / ids_crosscheck.py / judge.py
# 判定: matrix_check・ids_crosscheck・judge のいずれかが非 0 なら **最後に exit 1** (全部の結果を出し切ってから落とす)。
#       "[synth_e2e] OK" は全て 0 のときだけ出す。
# 出力: work/synth/{status.csv,facts.json,...} (work/ は gitignore)
# 前提素材: fl-win64 / toolchain-retdec / toolchain-emsdk  (docs/WORKFLOW.md §11)
# 環境変数: JOBS (cpp_lift の並列数; 既定 1) / HLL_CAP (cpp_lift.sh: RetDec の HLL 生成を待つ秒数; 既定 300) / SYNTH_KNOWN (judge の baseline; 既定 synth/known.json; ネガコン用)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
mkdir -p work/synth
SHELLS=($(python3 synth/targets.py shell))
CPPS=($(python3 synth/targets.py cpp))
ALL=("${SHELLS[@]}" "${CPPS[@]}")

judge() {  # judge <status.csv>
  python3 synth/judge.py "$1" --known "${SYNTH_KNOWN:-synth/known.json}" --want "${ALL[@]}"
}

if [ "${1:-}" = "--judge-only" ]; then
  if judge "$2"; then echo "[synth_e2e] OK (judge only)"; exit 0; fi
  echo "[synth_e2e] FAIL (judge)" >&2; exit 1
fi

python3 synth/targets.py --check
python3 synth/targets.py all | grep '^x86:' | sed 's/^/対象外 (x64 .pdata なし; 外形のみ facts.json に記録): /'

if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
  python3 inventory/win_scan.py
  python3 synth/mk_blockmap.py
  python3 inventory/win_funcs.py
  python3 inventory/win_unique.py > /dev/null
  python3 inventory/win_abi.py > /dev/null
fi
[ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null

python3 lift/plugin_closure.py "${SHELLS[@]}"
if [ "${1:-}" != "--skip-lift" ]; then
  # 今回の block の古い結果行を落としてから lift する (再実行で古い行が判定に混ざらないように)
  python3 - "${SHELLS[@]}" <<'PY'
import csv, os, sys
p = 'work/batch/status.csv'
if os.path.exists(p):
    rows = list(csv.reader(open(p)))
    keep = [rows[0]] + [r for r in rows[1:] if r[0] not in sys.argv[1:]]
    csv.writer(open(p, 'w', newline='')).writerows(keep)
PY
  bash lift/batch_lift.sh "${SHELLS[@]}"
  printf '%s\n' "${CPPS[@]}" | xargs -P "${JOBS:-1}" -I{} bash synth/cpp_lift.sh {} 2400 > work/synth/cpp_lift.stdout
  sort work/synth/cpp_lift.stdout
fi

python3 synth/mk_status.py work/synth/status.csv
grep -H 'unimplemented:' work/batch/*/p.simd.log work/synth/cpp*/e.simd.log 2>/dev/null | sed 's#work/##' | sort > work/synth/unimpl_names.txt || true
python3 synth/closure_facts.py > work/synth/facts.stdout.json 2> work/synth/facts.err

rc=0
python3 synth/matrix_check.py || rc=1
python3 synth/ids_crosscheck.py || rc=1
python3 synth/judge.py work/synth/status.csv --strict --want "${ALL[@]}" > work/synth/judge_strict.txt || true
tail -n 1 work/synth/judge_strict.txt
judge work/synth/status.csv || rc=1
cat work/synth/cpp*/first_errors.txt > /dev/null 2>&1 || true
if [ "$rc" = 0 ]; then echo "[synth_e2e] OK: work/synth/{status.csv,facts.json}"; exit 0; fi
echo "[synth_e2e] FAIL (matrix_check / ids_crosscheck / judge のいずれかが非 0)" >&2
exit 1
