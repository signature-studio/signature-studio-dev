#!/usr/bin/env bash
# #1080: function_412770 の null memcpy が unit 895 の Runtime error 210 (halt0) の直接原因か判定する。
#   前提: work/boot_final.ll が m11_gen_ir2.sh で作られ ir_conditions.json = applied であること。
#   HEAD (原 IR) / A (*arg1 を読む = native 機械語どおり) / B (null の代わりに 0 埋め領域) の 3 通りを
#   build して survey し、unit 単位の kind 遷移を出す。終了時に原 IR を復元する。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
M11="$HERE/../"
cd "$M11"
source ../shared/env.sh
OUT="${NEGCTL_OUT:-$M11/work/negctl_1080}"
mkdir -p "$OUT"
cp work/boot_final.ll "$OUT/boot_final.orig.ll"

python3 "$HERE/patch_412770_1080.py" "$OUT/boot_final.orig.ll" "$OUT"

run_variant() {
  local name="$1" ir="$2"
  cp "$ir" work/boot_final.ll
  python3 m11_cond.py --bind work/boot_final.ll >/dev/null
  bash m11_build.sh > "$OUT/build_$name.log" 2>&1
  SV_RAW=1 node trap_triage/survey_units.mjs "$OUT/survey_$name.json" > "$OUT/survey_$name.log" 2>&1
  grep -a SURVEY_UNITS "$OUT/survey_$name.log"
}

run_variant head "$OUT/boot_final.orig.ll"
run_variant A "$OUT/patchA.ll"
run_variant B "$OUT/patchB.ll"

cp "$OUT/boot_final.orig.ll" work/boot_final.ll
python3 m11_cond.py --bind work/boot_final.ll >/dev/null
python3 m11_cond.py --check work/boot_final.ll

python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
def load(p): return {u['unit']: u for u in json.load(open(p))}
base = load(f'{out}/survey_head.json')
for v in ['A', 'B']:
    cur = load(f'{out}/survey_{v}.json')
    tr = [(k, base[k]['kind'], cur[k]['kind']) for k in base if base[k]['kind'] != cur[k]['kind']]
    print(f'{v}: transitions={len(tr)} ' + ' '.join(f'{k}:{a}->{b}' for k, a, b in tr))
    print(f'{v}: unit895 kind={cur[895]["kind"]} top={cur[895]["frames"][0]} err={cur[895].get("err", [""])[0]}')
PY
