#!/usr/bin/env bash
# #699: 8c5eb0 の件数 0 ループ先頭ガードの IR 復元 (guard699/m11_guard699.py を m11_build.sh が適用) の実測 + ネガコン.
#   base = 検証起点 8d883c3 の m11_ov.c (8c7710 無し), guard 無効 (M11_GUARD699=off)
#   cur  = 現在の m11_ov.c (8c7710 転記),                guard 無効 (M11_GUARD699=off)  期待: base と unit 差 0, unit 56 trap
#   fix  = cur + guard 有効 (既定)                                                    期待: base と unit 差は 56 のみ (trap→ok)
#   ng   = cur + 偽ガード (icmp eq 123456789 = 常に不成立) 期待: cur と unit 差 0 (ネガコン), unit 56 trap
# 各 survey は rc=0 かつ units JSON 生成を確認してから判定する (前回 JSON の流用で PASS しない)。
# 判定が 1 つでも外れる・build/survey が失敗したら exit 1。終了時に m11_ov.c を HEAD 版へ戻す。
set -u
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$HERE"
OUT=work/v699
mkdir -p "$OUT"
cp m11_ov.c "$OUT/ov.cur.c"
git show 8d883c3:tools/m11/m11_ov.c > "$OUT/ov.base.c" || { echo "FAIL: git show 8d883c3"; exit 1; }
restore() { cp "$OUT/ov.cur.c" m11_ov.c; }
trap restore EXIT
export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-/tmp}}"

run_cfg() { # run_cfg <name> <ov.c> <off|on|ng>
  local name="$1" ov="$2" mode="$3"
  cp "$ov" m11_ov.c
  local guard=on cond=
  case "$mode" in
    off) guard=off ;;
    ng)  cond='icmp eq i32 %9, 123456789' ;;
  esac
  rm -f "$OUT/units_$name.json"
  if [ -n "$cond" ]; then
    M11_GUARD699=$guard M11_GUARD699_COND="$cond" bash m11_build.sh > "$OUT/build_$name.log" 2>&1 \
      || { echo "FAIL: build ($name) rc!=0 ($OUT/build_$name.log)"; exit 1; }
  else
    M11_GUARD699=$guard bash m11_build.sh > "$OUT/build_$name.log" 2>&1 \
      || { echo "FAIL: build ($name) rc!=0 ($OUT/build_$name.log)"; exit 1; }
  fi
  M11_SURVEY_UNITS="$OUT/units_$name.json" timeout 600 node m11_survey.mjs > "$OUT/survey_$name.out" 2>&1
  local rc=$?
  if [ $rc != 0 ] || [ ! -s "$OUT/units_$name.json" ]; then
    echo "FAIL: survey ($name) rc=$rc or units JSON 無し ($OUT/survey_$name.out)"; exit 1
  fi
  grep '^M11_SURVEY ' "$OUT/survey_$name.out" | cut -c1-200 | sed "s/^/[$name] /"
}

T0=$(date +%s)
run_cfg base "$OUT/ov.base.c" off
run_cfg cur "$OUT/ov.cur.c" off
run_cfg fix "$OUT/ov.cur.c" on
run_cfg ng "$OUT/ov.cur.c" ng
echo "[negctl_699] 4 構成の build+survey 所要 $(( $(date +%s) - T0 )) 秒"

python3 - "$OUT" <<'PYEOF'
import json, sys
out = sys.argv[1]
names = ['base', 'cur', 'fix', 'ng']
L = {n: json.load(open(f'{out}/units_{n}.json')) for n in names}
diff = lambda a, b: [(i, L[a][i], L[b][i]) for i in range(len(L[a])) if L[a][i] != L[b][i]]
cnt = lambda n: {k: L[n].count(k) for k in sorted(set(L[n]))}
for n in names:
    print(f'counts {n}:', cnt(n), 'unit56=', L[n][56])
checks = [
    ('G1 cur vs base: 回帰 0 (8c7710 転記のみで unit 差 0)', diff('base', 'cur') == []),
    ('G2 cur: unit 56 は trap (8c5eb0 の欠陥が残る)', L['cur'][56] == 'trap'),
    ('G3 fix vs base: 差は unit 56 のみ trap→ok', diff('base', 'fix') == [(56, 'trap', 'ok')]),
    ('G4 fix vs cur: 差は unit 56 のみ trap→ok', diff('cur', 'fix') == [(56, 'trap', 'ok')]),
    ('G5 ng (ネガコン) vs cur: unit 差 0 かつ unit 56 は trap', diff('cur', 'ng') == [] and L['ng'][56] == 'trap'),
]
bad = 0
for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
    bad += (not ok)
for a, b in [('base', 'cur'), ('base', 'fix'), ('cur', 'fix'), ('cur', 'ng')]:
    d = diff(a, b)
    print(f'diff {a}->{b}: n={len(d)} {d[:5]}')
sys.exit(1 if bad else 0)
PYEOF
