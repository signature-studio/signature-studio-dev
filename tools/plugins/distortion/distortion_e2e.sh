#!/usr/bin/env bash
# PLG-F6 (#203) distortion + multi-fx の「lift 準備度」実測を 1 コマンドで再現する。 不合格・測定不成立は非 0 で終わる。
#   bash tools/plugins/distortion/distortion_e2e.sh [--skip-lift]
#   bash tools/plugins/distortion/distortion_e2e.sh --judge-only <status.csv> [<audit.csv>]   (判定だけを実行: ネガティブコントロール用)
# 手順: 前提 inventory → 殻の閉包 (plugin_closure) → batch_lift (RetDec+pass 鎖 → emcc -c) → judge.py (殻)
#       → unimpl_names.py → closure_facts.py → matrix_check.py → ids_crosscheck.py → engine / 別 DLL の lift → judge.py --engines
# 出力: work/distortion/{status.csv,facts.json,engines.csv} (work/ は gitignore)
# 判定: judge.py の exit が非 0、または matrix_check / ids_crosscheck が非 0 なら本スクリプトは非 0 で終わり、最終行の OK は出ない。
#       --skip-lift は work/batch/status.csv (環境変数 BATCH_STATUS で差替可) の既存の行 (block ごとの最後) を使う開発用。 lift をやり直さないので検証としては使わない。
# 前提素材: fl-win64 / toolchain-retdec / toolchain-emsdk  ([WIN64] [RETDEC] [EMSDK]; docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
read -ra SHELLS < <(python3 distortion/targets.py shells)
read -ra ENGINES < <(python3 distortion/targets.py engines)
SHELLS_CSV="$(IFS=,; echo "${SHELLS[*]}")"
ENGINES_CSV="$(IFS=,; echo "${ENGINES[*]}")"
ALLOW=(--allow-unimpl 19024=1)   # targets.ALLOW_UNIMPL と同じ (Love Philter の rep_stosb_memset 1 件)
OUT=work/distortion
BATCH_STATUS="${BATCH_STATUS:-work/batch/status.csv}"   # --skip-lift が読む lift 結果 (NC で差し替える)

judge_shells() {   # $1 = status.csv, $2 = 欠落監査 csv。 非 0 ならここで set -e により終了する
  python3 distortion/judge.py "$1" --blocks "$SHELLS_CSV" --audit "$2" "${ALLOW[@]}"
}

if [ "${1:-}" = "--judge-only" ]; then
  judge_shells "${2:?status.csv}" "${3:-$OUT/shell_audit.csv}"
  echo "[distortion_e2e] OK (judge-only)"
  exit 0
fi

mkdir -p "$OUT"
bash distortion/inventory.sh

python3 lift/plugin_closure.py "${SHELLS[@]}" > /dev/null
if [ "${1:-}" != "--skip-lift" ]; then
  # 前回までの行を判定に混ぜない: 今回追記された行だけを status.csv にする
  mkdir -p work/batch
  [ -f work/batch/status.csv ] || echo "block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds" > work/batch/status.csv
  n0=$(wc -l < work/batch/status.csv)
  bash lift/batch_lift.sh "${SHELLS[@]}"
  { head -n 1 work/batch/status.csv; tail -n +$((n0 + 1)) work/batch/status.csv; } > "$OUT/status.csv"
else
  echo "[distortion_e2e] WARNING: --skip-lift: 既存の $BATCH_STATUS を使う (lift は再実行しない)" >&2
  python3 - "$SHELLS_CSV" "$BATCH_STATUS" > "$OUT/status.csv" <<'PY'
import csv, sys
want = sys.argv[1].split(',')
rows = list(csv.reader(open(sys.argv[2])))
last = {r[0]: r for r in rows[1:] if r[0] in want}
w = csv.writer(sys.stdout, lineterminator='\n')
w.writerow(rows[0])
w.writerows(last[b] for b in want if b in last)
PY
fi
# 閉包 range と final.ll の突合 (全 range の開始 VA に define があるか)
echo "block,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > "$OUT/shell_audit.csv"
for b in "${SHELLS[@]}"; do
  echo "$b,$(python3 distortion/engine_defs.py --ranges "work/closure/block$(printf %05d "$b").ranges.txt" --ll "work/batch/$b/p.final.ll")" >> "$OUT/shell_audit.csv"
done
judge_shells "$OUT/status.csv" "$OUT/shell_audit.csv"
python3 distortion/unimpl_names.py work/batch --blocks "$SHELLS_CSV" --allow 19024=__asm_rep_stosb_memset

python3 distortion/closure_facts.py > "$OUT/facts.stdout.json" 2> "$OUT/facts.err"
python3 distortion/matrix_check.py
python3 distortion/ids_crosscheck.py

if [ "${1:-}" != "--skip-lift" ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,f80_funcs_pre,emcc_c_rc_pre_f80,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > "$OUT/engines.csv"
  for eb in "${ENGINES[@]}"; do bash distortion/engine_lift.sh "$eb" 1800 | tail -n 1 >> "$OUT/engines.csv"; done
  cat "$OUT/engines.csv" "$OUT"/engine*/first_errors.txt
  python3 distortion/judge.py "$OUT/engines.csv" --engines --blocks "$ENGINES_CSV"
fi
# C++ DLL の DSP 閉包 (CreatePlugInstance → vptr → vtable → 直接呼出)。 閉包の全 range が engine の final.ll に define を持つことも確認する
echo "block,seed_vtables,vtables_in_closure,closure_funcs,closure_bytes,pdata_funcs,indirect_call_sites,iat_call_sites,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > "$OUT/closure_cpp.csv"
for eb in "${ENGINES[@]}"; do
  python3 distortion/closure_cpp.py "$eb" --ranges "$OUT/closure_cpp_$eb.txt" --json "$OUT/closure_cpp_$eb.json" > /dev/null
  python3 - "$OUT/closure_cpp_$eb.json" "$eb" "$(python3 distortion/engine_defs.py --ranges "$OUT/closure_cpp_$eb.txt" --ll "$OUT/engine$eb/e.final.ll")" >> "$OUT/closure_cpp.csv" <<'PY'
import json, sys
j = json.load(open(sys.argv[1]))
print(','.join(str(x) for x in [sys.argv[2], len(j['seed_vtables']), j['vtables_in_closure'], j['closure_funcs'], j['closure_bytes'], j['pdata_funcs'],
                                  j['indirect_call_sites'], j['iat_call_sites'], sys.argv[3]]))
PY
done
cat "$OUT/closure_cpp.csv"
python3 distortion/judge.py "$OUT/closure_cpp.csv" --closure-cpp --blocks "$ENGINES_CSV"
echo "[distortion_e2e] OK: $OUT/{status.csv,facts.json,engines.csv}"
