#!/usr/bin/env bash
# PLG-F4 (#201) reverb-delay 9 本の「lift 前提」実測を 1 コマンドで再現する。 判定が不合格なら exit 1。
#   bash tools/plugins/reverb_delay/reverb_delay_e2e.sh [--skip-lift]
# 手順: 前提 inventory (prep.sh) → 9 閉包 → batch_lift (既定鎖 PLUG_ICALL=1 → RetDec+pass 鎖 → emcc -c) → judge.py (gate) → closure_facts.py
#       → matrix_check.py (gate) → ids_crosscheck.py (gate) → 従来鎖 chain0_lift.sh (PLUG_ICALL=0; 測定のみ)
#       → icall 監査 (2 鎖) + icall_summary.py (表) + xcheck_icall.py (gate: 別算法一致) → f2/icall_gate.py (既定鎖; 測定のみ・gate 外)
#       → ipp_use.py (測定) → engine 2 本の lift (従来鎖・測定のみ・判定に含めない)
# 出力: work/reverb_delay/{status9.csv,facts.json,icall/,chain0/,icall_gate.txt,ipp_use.json,engines.csv} (work/ は gitignore)
# PLUG_ICALL: 既定鎖 = 1 (batch_lift.sh の既定と同じ。 ここで明示 export)。 従来鎖は chain0_lift.sh / engine_lift.sh が PLUG_ICALL=0 を明示する。
# 前提素材: fl-win64 / toolchain-retdec (/opt/retdec) / toolchain-emsdk (/opt/emsdk)  (docs/WORKFLOW.md §11)
# gate (judge / matrix_check / ids_crosscheck / xcheck_icall) が 1 つでも非 0 なら set -e で即 exit 1。 最後の OK 行は全 gate 通過後にだけ出る。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
BLOCKS=(18992 18996 18998 18999 19002 19067 19069 19146 19164)   # Convolver Delay Delay2 Delay3 DelayBank Reeverb Reeverb2 LuxeVerb MultibandDelay
O=work/reverb_delay
export PLUG_ICALL=1
mkdir -p $O/icall $O/chain0/icall
bash reverb_delay/prep.sh

python3 lift/plugin_closure.py "${BLOCKS[@]}" > /dev/null
if [ "${1:-}" != "--skip-lift" ]; then
  rm -f work/batch/status.csv          # 追記式なので stale 行を残さない
  PLUG_ICALL=1 bash lift/batch_lift.sh "${BLOCKS[@]}"
  bash reverb_delay/chain0_lift.sh "${BLOCKS[@]}" > $O/chain0.log 2>&1   # 従来鎖 (測定のみ・gate 外)
  tail -n 9 $O/chain0.log
fi

[ -f work/batch/status.csv ] || { echo "[reverb_delay_e2e] FAIL: work/batch/status.csv が無い" >&2; exit 1; }
python3 reverb_delay/judge.py work/batch/status.csv "${BLOCKS[@]}" --closure-dir work/closure
python3 - work/batch/status.csv $O/status9.csv "${BLOCKS[@]}" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
last = {r[0]: r for r in rows[1:] if r[0] in set(sys.argv[3:])}
csv.writer(open(sys.argv[2], 'w')).writerows([rows[0]] + [last[b] for b in sys.argv[3:]])
PY

python3 reverb_delay/closure_facts.py > $O/facts.stdout.json 2> $O/facts.err
python3 reverb_delay/matrix_check.py
python3 reverb_delay/ids_crosscheck.py

echo "== 間接 call 監査 (tools/icall/audit_icall.py; 測定。 2 鎖。 判定は xcheck_icall.py の別算法一致のみ)"
for b in "${BLOCKS[@]}"; do
  PE="$FL_WIN64_DIR/extracted/block$(printf %05d $b)_PE.bin"
  tr ',' '\n' < "work/closure/block$(printf %05d $b).ranges.txt" | cut -d- -f1 | grep . > "$O/icall/$b.funcs"
  python3 ../icall/audit_icall.py --pe "$PE" \
    --ir "work/batch/$b/p.final.ll" --funcs "$O/icall/$b.funcs" --json "$O/icall/$b.icall.json" --sites "$O/icall/$b.sites.json" --label "$b" > /dev/null
  python3 ../icall/audit_icall.py --pe "$PE" \
    --ir "$O/chain0/$b/p.final.ll" --funcs "$O/icall/$b.funcs" --json "$O/chain0/icall/$b.icall.json" --label "$b" > /dev/null || echo "[chain0] $b: 監査失敗 (測定のみ・gate 外)"
done
python3 reverb_delay/icall_summary.py "${BLOCKS[@]}" || echo "[icall_summary] 失敗 (測定のみ・gate 外)"
python3 reverb_delay/xcheck_icall.py "${BLOCKS[@]}"

echo "== 既定鎖の IR 間接 call 回帰ゲート (tools/plugins/f2/icall_gate.py; 測定のみ・gate 外。 rc 1 は F1 の未被覆 site = REPORT §9)"
set +e
python3 f2/icall_gate.py "${BLOCKS[@]}" --json $O/icall_gate.json > $O/icall_gate.txt 2>&1; GATE_RC=$?
set -e
cat $O/icall_gate.txt
echo "icall_gate (既定鎖・測定のみ) rc=$GATE_RC"

echo "== IPP 実使用の静的調査 (ipp_use.py; 測定のみ)"
python3 reverb_delay/ipp_use.py --json $O/ipp_use.json "${BLOCKS[@]}"

# engine 分離型 2 本の C++ engine DLL (判定には含めない: 到達性の実測のみ。 失敗は想定内で exit code に反映しない)
if [ "${1:-}" != "--skip-lift" ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > $O/engines.csv
  for eb in 19000 19165; do bash reverb_delay/engine_lift.sh "$eb" 1500 | tail -n 1 >> $O/engines.csv; done
  echo "== engine (測定のみ・gate 外)"; cat $O/engines.csv $O/engine*/first_errors.txt
fi
echo "[reverb_delay_e2e] OK: 全 gate 通過 (judge / matrix_check / ids_crosscheck / xcheck_icall) → $O/{status9.csv,facts.json,icall/,ipp_use.json}"
