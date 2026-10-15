#!/usr/bin/env bash
# qstore_ab_942.sh — #942: 本番の IR 生成順 (ldfix → fix_ld108 → qstore) で stage4 / survey を A/B する。
#   既存の測定系 (ldfix_e2e.sh・stage4.sh・survey_stage4.mjs) は変更しない (呼ぶだけ)。
#   variant: raw = boot_final3.ll そのまま / qs = qstore のみ / pnq = ldfix → fix_ld108 / prod = pnq → qstore
#   使い方: bash tools/m11/ldfix/qstore_ab_942.sh
#   前提: ldfix_e2e.sh と同じ (tools/m11/work/boot_final3.ll・PE・capstone/pefile・emsdk)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
cd "$REPO"
source "$REPO/tools/shared/env.sh"
PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
RAW=tools/m11/work/boot_final3.ll
W="$HERE/work/qstore_ab"
QS="$HERE/../qstore/m11_qstore.py"
VARS="ab_raw ab_qs ab_pnq ab_prod"

step() { echo "[qstore_ab] $*"; }
fail() { echo "[qstore_ab] FAILED: $*"; exit 1; }

[ -f "$RAW" ] || fail "$RAW 無し (bash tools/m11/m11_e2e.sh を先に)"
[ -f "$PE" ] || fail "PE 無し ($PE)"
python3 -c 'import capstone, pefile' 2>/dev/null || fail "capstone/pefile 無し (ldfix・qstore が必要)"
mkdir -p "$W"

step "1/3 IR 生成 (本番順: ldfix → fix_ld108 → qstore)"
python3 "$QS" "$RAW" "$W/ab_qs.ll" --pe "$PE" --report "$W/qs_report.json" > "$W/qs.log" 2>&1 || fail "qstore (qs)"
python3 "$HERE/ldfix.py" "$RAW" "$W/ldfix.ll" --pe "$PE" --report "$W/ldfix_report.json" > "$W/ldfix.log" 2>&1 || fail "ldfix.py"
python3 "$HERE/fix_ld108.py" "$W/ldfix.ll" "$W/ab_pnq.ll" > "$W/ld108.log" 2>&1 || fail "fix_ld108.py"
python3 "$QS" "$W/ab_pnq.ll" "$W/ab_prod.ll" --pe "$PE" --report "$W/prod_report.json" > "$W/prod.log" 2>&1 || fail "qstore (prod)"
cp "$RAW" "$W/ab_raw.ll"

step "2/3 stage4 + survey (4 variant)"
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
for N in $VARS; do
  bash "$HERE/stage4.sh" "$W/$N.ll" "$N" > "$W/stage4_$N.log" 2>&1
  grep STAGE4_RESULT "$W/stage4_$N.log" | sed "s/^/[qstore_ab] $N /" | cut -c1-260
  (export S4_NAME=$N; export S4_IMAGE=tools/m11/work/m11_image.bin; \
   timeout 900 node "$HERE/survey_stage4.mjs" > "$HERE/work/stage4/$N/e2e_survey.out" 2> "$HERE/work/stage4/$N/e2e_survey.err" || true)
done

step "3/3 集計 (raw を基準)"
python3 - "$HERE/work/stage4" $VARS <<'PYEOF'
import json, re, sys
root, names = sys.argv[1], sys.argv[2:]
def survey(n):
    txt = open(f'{root}/{n}/e2e_survey.out').read()
    m = re.search(r'M11_SURVEY (\{.*\})', txt)
    return json.loads(m.group(1)) if m else None
def units(d):
    return set(d['first_trap_units']) if d else set()
base = survey(names[0])
print('variant  | survey ok | miss | trap | OOB | halt0 | boot_threw | 先頭 trap unit (raw 比)')
for n in names:
    d = survey(n)
    if d is None:
        print(f'{n}: survey 出力無し'); continue
    k = d['trap_kinds']
    oob = k.get('memory access out of bounds', 0)
    halt = k.get('halt0->longjmp (unit が Halt を呼んだ)', 0)
    print(f"{n:8s} | {d['ok']:9d} | {d['miss']:4d} | {d['trap']:4d} | {oob:3d} | {halt:5d} | {d['boot_threw']} | "
          f"消えた {sorted(units(base) - units(d))} 新規 {sorted(units(d) - units(base))}")
PYEOF
echo "[qstore_ab] DONE"
