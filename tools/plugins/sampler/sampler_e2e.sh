#!/usr/bin/env bash
# PLG-G3 (#208) sampler 8 本の「lift 前提」実測を 1 コマンドで再現する。
#   bash tools/plugins/sampler/sampler_e2e.sh [--skip-lift] [--judge-only]
#   --skip-lift: lift 済みの status.csv を再判定 + facts。 --judge-only: 判定 (judge.py) まででやめる (ネガコン用、数秒)
# 手順: 前提 inventory (work/ 無ければ生成) → Delphi 殻 7 閉包 → batch_lift (RetDec+pass 鎖 → emcc -c) → **判定 (judge.py)**
#       → C++ engine / 単体 DLL の lift (engine_lift.sh、バックグラウンド) と closure_facts.py → matrix_check.py → engine 判定
# 判定が不合格なら exit 1 (最終行の OK は全判定を通った時だけ出る)。 対象は targets.py が唯一の定義。
# 環境変数 STATUS_CSV: 判定入力の status.csv (既定 work/batch/status.csv)。 --skip-lift 時は全行 (block ごとに最後の行)、
#   lift 実行時はこの run が追記した行だけを判定に使う (過去 run の合格行で通さない)
# 出力: work/sampler/{status_run.csv,status.csv,facts.json,engines.csv} (work/ は gitignore)
# 前提素材: fl-win64 / toolchain-retdec / toolchain-emsdk  (docs/WORKFLOW.md §11)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
read -r -a BLOCKS <<< "$(python3 sampler/targets.py blocks)"
read -r -a ENGINES <<< "$(python3 sampler/targets.py engines)"
BL="$(IFS=,; echo "${BLOCKS[*]}")"
EL="$(IFS=,; echo "${ENGINES[*]}")"
ALLOW="$(python3 sampler/targets.py allow-unimpl)"
STATUS_CSV="${STATUS_CSV:-work/batch/status.csv}"
SKIP=0; JUDGE_ONLY=0
for a in "$@"; do
  case "$a" in --skip-lift) SKIP=1 ;; --judge-only) JUDGE_ONLY=1; SKIP=1 ;; *) echo "usage: $0 [--skip-lift] [--judge-only]" >&2; exit 2 ;; esac
done
[ "$SKIP" = 0 ] && STATUS_CSV=work/batch/status.csv   # batch_lift.sh の出力先に固定
mkdir -p work/sampler

if [ ! -d work/winfuncs ] || [ ! -f work/win_abi.json ]; then
  python3 inventory/win_scan.py
  python3 sampler/mk_blockmap.py
  python3 inventory/win_funcs.py
  python3 inventory/win_unique.py > /dev/null
  python3 inventory/win_abi.py > /dev/null
fi
[ -f work/kernel_table.json ] || python3 inventory/kernel_table.py > /dev/null

python3 lift/plugin_closure.py "${BLOCKS[@]}" > /dev/null
N0=0
if [ "$SKIP" = 0 ]; then
  [ -f "$STATUS_CSV" ] && N0=$(wc -l < "$STATUS_CSV")
  bash lift/batch_lift.sh "${BLOCKS[@]}"
fi

python3 - "$STATUS_CSV" "$N0" <<'PY'
import csv, re, sys, os
path, n0 = sys.argv[1], int(sys.argv[2])
rows = list(csv.reader(open(path)))
hdr, body = rows[0], rows[1:][max(n0 - 1, 0):]
hdr = hdr + ['unimpl_names']
out = []
for r in body:
    log = os.path.join('work', 'batch', r[0], 'p.simd.log')
    names = []
    if os.path.exists(log):
        for l in open(log):
            m = re.match(r'\s+unimplemented: \S+ (__asm_\S+?)\(', l)
            if m:
                names.append(re.sub(r'(__\d+)+$', '', m.group(1)[len('__asm_'):]))
    out.append(r + ['|'.join(sorted(set(names)))])
csv.writer(open('work/sampler/status_run.csv', 'w')).writerows([hdr] + out)
PY
python3 sampler/judge.py shells work/sampler/status_run.csv --blocks "$BL" --allow-unimpl "$ALLOW" \
  --allow-names "$(python3 -c 'import sys; sys.path.insert(0, "sampler"); import targets; print(",".join(targets.ALLOW_UNIMPL_NAMES))')" \
  --out work/sampler/status.csv
if [ "$JUDGE_ONLY" = 1 ]; then echo "[sampler_e2e] judge-only: shells PASS"; exit 0; fi

if [ "$SKIP" = 0 ]; then
  echo "block,pdata_funcs,lift_rc,defines,f80_funcs,unimpl_helpers,emcc_c_rc,fixcmp_patched,emcc_c_rc_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside,function_defines" > work/sampler/engines.csv
  for eb in "${ENGINES[@]}"; do
    ( bash sampler/engine_lift.sh "$eb" 900 | tail -n 1 > "work/sampler/engine$eb.line" ) &
  done
fi

python3 sampler/closure_facts.py > work/sampler/facts.stdout.json 2> work/sampler/facts.err
python3 sampler/matrix_check.py

if [ "$SKIP" = 0 ]; then
  wait
  for eb in "${ENGINES[@]}"; do cat "work/sampler/engine$eb.line" >> work/sampler/engines.csv; done
  cat work/sampler/engines.csv work/sampler/engine*/first_errors.txt
  python3 sampler/judge.py engines work/sampler/engines.csv --blocks "$EL"
fi
echo "[sampler_e2e] OK: work/sampler/{status.csv,facts.json}"
