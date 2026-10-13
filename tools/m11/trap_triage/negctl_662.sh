#!/usr/bin/env bash
# #662: unit 56 の 8c7710 転記 (m11_ov.c) と、その先の 8c5eb0 の欠陥 (件数 0 のループ先頭ガード脱落) の実測 + ネガコン.
#   base  = 検証起点 8d883c3 の m11_ov.c (8c7710 無し)
#   cur   = 現在の m11_ov.c (8c7710 転記)              期待: base と unit 差 0 (回帰無し), unit 56 は trap
#   guard = cur + IR 実験 (8c5eb0 の件数 <= 0 で本体を飛ばす) 期待: base と unit 差は 56 のみ (trap→ok)
#   ng    = cur + 偽ガード (icmp eq 123456789 = 常に不成立) 期待: cur と unit 差 0 (ネガコン: 効果はガードの条件由来)
# 前提: work/ に work-m11 (boot_final.ll, boot_final3.ll, obj/ 等) があり m11_build.sh が通ること。PE は FL_WIN64_DIR (build の qstore 用)。
# 終了時に m11_ov.c と work/boot_final3.ll を元に戻す。判定が 1 つでも外れたら exit 1。
# survey は各構成の前に units_<name>.json を消し, 非 0 終了または JSON 無しなら exit 1 (前回の値で PASS しない)。
# IR 状態 (#680): qstore (#516) は boot_final.ll を書き換え, post で boot_final3.ll が再生成される。artifact の boot_final3.ll は qstore 前の IR なので,
#   4 構成の入力は「前段 build を通した boot_final3.ll」(orig) に揃える。qstore は capstone/pefile が要るため, 無ければ FAIL。
set -u
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$HERE"
OUT=work/v662
mkdir -p "$OUT"
python3 -c 'import capstone, pefile' 2>/dev/null || { echo "FAIL: capstone/pefile 無し (qstore が skip され IR 状態が変わる)"; exit 1; }
source "$HERE/../shared/env.sh"
PE_CHK="${PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
[ -f "$PE_CHK" ] || { echo "FAIL: PE 無し ($PE_CHK) (qstore が skip され IR 状態が変わる。FL_WIN64_DIR を fl-win64 の展開先にする)"; exit 1; }
if [ ! -f "$OUT/boot_final3.orig.ll" ]; then
  rm -f work/boot_final3.ll
  bash m11_build.sh > "$OUT/build_prep.log" 2>&1 || { echo "FAIL: 前段 build ($OUT/build_prep.log)"; exit 1; }
  cp work/boot_final3.ll "$OUT/boot_final3.orig.ll" || { echo "FAIL: $OUT/boot_final3.orig.ll の保存 (work-m11 を先に展開)"; exit 1; }
fi
cp m11_ov.c "$OUT/ov.cur.c"
git show 8d883c3:tools/m11/m11_ov.c > "$OUT/ov.base.c" || { echo "FAIL: git show 8d883c3"; exit 1; }
restore() { cp "$OUT/ov.cur.c" m11_ov.c; cp "$OUT/boot_final3.orig.ll" work/boot_final3.ll; }
trap restore EXIT
export TMPDIR="${TMPDIR:-$RUNNER_TEMP}"

run_cfg() { # run_cfg <name> <ov.c> <orig|guard|ng>
  local name="$1" ov="$2" mode="$3"
  cp "$ov" m11_ov.c
  cp "$OUT/boot_final3.orig.ll" work/boot_final3.ll
  if [ "$mode" != orig ]; then
    local cond="icmp sle i32 %9, 0"
    [ "$mode" = ng ] && cond="icmp eq i32 %9, 123456789"
    python3 - "$cond" <<'PYEOF' || { echo "FAIL: IR パッチ ($name) の対象行が 1 件でない"; exit 1; }
import sys
p = 'work/boot_final3.ll'
s = open(p).read()
old = '  store i32 0, ptr %stack_var_-44.0.reg2mem\n  store i64 %10, ptr %rbx.0.reg2mem\n  br label %dec_label_pc_8c5f23\n'
assert s.count(old) == 1, s.count(old)
new = ('  store i32 0, ptr %stack_var_-44.0.reg2mem\n  store i64 %10, ptr %rbx.0.reg2mem\n'
       '  %g662 = ' + sys.argv[1] + '\n  br i1 %g662, label %dec_label_pc_8c6066, label %dec_label_pc_8c5f23\n')
open(p, 'w').write(s.replace(old, new, 1))
PYEOF
  fi
  bash m11_build.sh > "$OUT/build_$name.log" 2>&1 || { echo "FAIL: build ($name) rc!=0 ($OUT/build_$name.log)"; exit 1; }
  rm -f "$OUT/units_$name.json"
  M11_SURVEY_UNITS="$OUT/units_$name.json" timeout 300 node m11_survey.mjs > "$OUT/survey_$name.out" 2>&1 \
    || { echo "FAIL: survey ($name) rc!=0 ($OUT/survey_$name.out)"; exit 1; }
  [ -f "$OUT/units_$name.json" ] || { echo "FAIL: survey ($name) が units JSON を出さなかった ($OUT/survey_$name.out)"; exit 1; }
  grep '^M11_SURVEY ' "$OUT/survey_$name.out" | cut -c1-200 | sed "s/^/[$name] /"
}

run_cfg base "$OUT/ov.base.c" orig
run_cfg cur "$OUT/ov.cur.c" orig
run_cfg guard "$OUT/ov.cur.c" guard
run_cfg ng "$OUT/ov.cur.c" ng

python3 - "$OUT" <<'PYEOF'
import json, sys
out = sys.argv[1]
L = {n: json.load(open(f'{out}/units_{n}.json')) for n in ['base', 'cur', 'guard', 'ng']}
diff = lambda a, b: [(i, L[a][i], L[b][i]) for i in range(len(L[a])) if L[a][i] != L[b][i]]
checks = [
    ('G1 cur vs base: 回帰 0 (unit 差 0)', diff('base', 'cur') == []),
    ('G2 cur: unit 56 は trap (8c5eb0 の欠陥が残る)', L['cur'][56] == 'trap'),
    ('G3 guard vs base: 差は unit 56 のみ trap→ok', diff('base', 'guard') == [(56, 'trap', 'ok')]),
    ('G4 ng (ネガコン) vs cur: unit 差 0', diff('cur', 'ng') == []),
    ('G5 ng: unit 56 は trap のまま', L['ng'][56] == 'trap'),
]
bad = 0
for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
    bad += (not ok)
for a, b in [('base', 'cur'), ('base', 'guard'), ('cur', 'ng')]:
    print(f'diff {a}->{b}:', diff(a, b)[:5], 'n=', len(diff(a, b)))
sys.exit(1 if bad else 0)
PYEOF
