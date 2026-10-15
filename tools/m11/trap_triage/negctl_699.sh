#!/usr/bin/env bash
# #699: 8c5eb0 の件数 0 ループ先頭ガードの IR 復元 (guard699/m11_guard699.py を m11_build.sh が適用) の実測 + ネガコン.
# 比較元は現在の m11_ov.c (main 取り込み後の版。#700 の 8c7710 転記を含む) の 1 版に固定する。
#   off = 同じ m11_ov.c, guard 無効 (M11_GUARD699=off)                       基準
#   fix = 同じ m11_ov.c, guard 有効 (既定)                                   期待: unit 56 の trap 元が function_8c6530 の OOB から function_8c5eb0 の辺 (returned = function_410360 の戻り値) に変わる (G2)
#   ng  = 同じ m11_ov.c, 偽ガード (icmp eq i32 %9, 123456789 = 常に不成立)   期待: off と unit 差 0 (ネガコン), unit 56 trap
# G2 は #699 の受入条件 2 改訂 (PM 判断, コメント 6147966392) に合わせた。unit 56 が ok になることは条件にしない。
# 旧 G2 (unit 56 trap→ok) は main の変更で別原因の trap が残るため不成立 (旧期待値は REPORT_699 §3-6 に残す)。
# #3077 (89bee32d) で fail-fast 辺は機械語どおり function_410360 の戻り値を返す形になった。よって fix の期待は unreachable ではなく returned。
# 各 survey は rc=0 かつ units JSON 生成を確認してから判定する (前回 JSON の流用で PASS しない)。
# 判定が 1 つでも外れる・build/survey が失敗したら exit 1。終了時に m11_ov.c と work/boot_final.ll を開始時の版へ戻す
# (ng 構成の IR が残ると次の既定 build の前提が変わるため。boot_final.ll は m11_build.sh が pass を in-place 適用する)。
set -u
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$HERE"
OUT=work/v699
mkdir -p "$OUT"
cp m11_ov.c "$OUT/ov.cur.c"
cp work/boot_final.ll "$OUT/boot_final.start.ll" || { echo "FAIL: work/boot_final.ll が無い"; exit 1; }
cp work/ir_conditions.json "$OUT/ir_conditions.start.json" || { echo "FAIL: work/ir_conditions.json が無い"; exit 1; }
restore() { cp "$OUT/ov.cur.c" m11_ov.c; cp "$OUT/boot_final.start.ll" work/boot_final.ll; cp "$OUT/ir_conditions.start.json" work/ir_conditions.json; }
trap restore EXIT
export TMPDIR="${TMPDIR:-${RUNNER_TEMP:-/tmp}}"

run_cfg() { # run_cfg <name> <off|on|ng>
  local name="$1" mode="$2"
  cp "$OUT/ov.cur.c" m11_ov.c
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
  M11_SURVEY_STACK=56 M11_SURVEY_UNITS="$OUT/units_$name.json" timeout 600 node m11_survey.mjs > "$OUT/survey_$name.out" 2> "$OUT/stack56_$name.txt"
  local rc=$?
  if [ $rc != 0 ] || [ ! -s "$OUT/units_$name.json" ]; then
    echo "FAIL: survey ($name) rc=$rc or units JSON 無し ($OUT/survey_$name.out)"; exit 1
  fi
  grep -m1 '\[survey\]\[stack\] unit 56' "$OUT/stack56_$name.txt" | cut -c1-160 | sed "s/^/[$name] /"
  grep '^M11_SURVEY ' "$OUT/survey_$name.out" | cut -c1-200 | sed "s/^/[$name] /"
}

T0=$(date +%s)
run_cfg off off
run_cfg fix on
run_cfg ng ng
echo "[negctl_699] 3 構成の build+survey 所要 $(( $(date +%s) - T0 )) 秒"

python3 - "$OUT" <<'PYEOF'
import json, sys
out = sys.argv[1]
names = ['off', 'fix', 'ng']
L = {n: json.load(open(f'{out}/units_{n}.json')) for n in names}
diff = lambda a, b: [(i, L[a][i], L[b][i]) for i in range(len(L[a])) if L[a][i] != L[b][i]]
cnt = lambda n: {k: L[n].count(k) for k in sorted(set(L[n]))}
for n in names:
    print(f'counts {n}:', cnt(n), 'unit56=', L[n][56])
def t56(n):
    s = open(f'{out}/stack56_{n}.txt', errors='replace').read()
    return 'oob' if 'memory access out of bounds' in s else 'unreachable' if 'unreachable' in s else 'returned' if 'returned' in s else 'other'
checks = [
    ('G1 off: unit 56 は trap (8c5eb0 の欠陥が残る)', L['off'][56] == 'trap'),
    ('G2 (#699 受入 2 改訂, #3077 後の現版): unit 56 の trap 元が off=OOB → fix=returned (8c5eb0 の辺。function_410360 の戻り値)', t56('off') == 'oob' and t56('fix') == 'returned'),
    ('G3 ng (ネガコン) vs off: unit 差 0 かつ unit 56 は trap', diff('off', 'ng') == [] and L['ng'][56] == 'trap'),
]
bad = 0
for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
    bad += (not ok)
for a, b in [('off', 'fix'), ('off', 'ng')]:
    d = diff(a, b)
    print(f'diff {a}->{b}: n={len(d)} {d[:5]}')
sys.exit(1 if bad else 0)
PYEOF
