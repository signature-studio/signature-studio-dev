#!/usr/bin/env bash
# #663 検収 + ネガコン: survey_units.mjs の oob frames 修正 (.slice(1,30) → .slice(0,30)) で kind が 1 件も変わらず、oob の frames だけ最上位を含む 1 段増えることを検査する.
#   usage: negctl_663.sh [BASE_COMMIT]   (既定 8d883c3 = 修正前の起点。その時点の survey_units.mjs を work/negctl_663/ に取り出して走らせる)
#   結果: work/negctl_663/{pre,post,mut}.json と survey_diff / frames_check の出力. 期待: (a) post vs pre = PASS (b) pre vs pre = FAIL (c) kind を 1 件書換えた mut = FAIL.
#   いずれか期待と違えば exit 1.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
BASE="${1:-8d883c3}"
OUT=work/negctl_663; mkdir -p "$OUT/trap_triage"
[ -e "$OUT/work" ] || ln -s "$(pwd)/work" "$OUT/work"
git show "$BASE:tools/m11/trap_triage/survey_units.mjs" > "$OUT/trap_triage/survey_units_pre.mjs" || { echo "git show $BASE 失敗" >&2; exit 1; }
t0=$(date +%s.%N)
node "$OUT/trap_triage/survey_units_pre.mjs" "$OUT/pre.json" > "$OUT/pre.out" 2> "$OUT/pre.err" || { echo "pre survey 失敗" >&2; tail -3 "$OUT/pre.err"; exit 1; }
t1=$(date +%s.%N)
node trap_triage/survey_units.mjs "$OUT/post.json" > "$OUT/post.out" 2> "$OUT/post.err" || { echo "post survey 失敗" >&2; tail -3 "$OUT/post.err"; exit 1; }
t2=$(date +%s.%N)
echo "pre  $(grep -a SURVEY_UNITS "$OUT/pre.out")  md5=$(md5sum < "$OUT/pre.json" | cut -c1-12)  wall=$(echo "$t1 - $t0" | bc)s"
echo "post $(grep -a SURVEY_UNITS "$OUT/post.out")  md5=$(md5sum < "$OUT/post.json" | cut -c1-12)  wall=$(echo "$t2 - $t1" | bc)s"
python3 -c '
import json, sys
per = json.load(open(sys.argv[1]))
u = next(r["unit"] for r in per if r["kind"] == "ok")
for r in per:
    if r["unit"] == u: r["kind"] = "oob"; r["msg"] = "mutated"; r.setdefault("frames", [])
json.dump(per, open(sys.argv[2], "w"), indent=1); print("mut: unit %d の kind を ok -> oob に書換え" % u)' "$OUT/post.json" "$OUT/mut.json"
expect() { # expect <want-exit> <label> <cmd...>
  local want="$1" label="$2"; shift 2
  "$@" > "$OUT/$label.check" 2>&1; local got=$?
  if [ "$got" = "$want" ]; then echo "OK   $label exit=$got (期待 $want)"; else echo "NG   $label exit=$got (期待 $want)"; cat "$OUT/$label.check"; fail=1; fi
}
fail=0
expect 0 check_post_vs_pre python3 trap_triage/frames_check.py "$OUT/pre.json" "$OUT/post.json"
expect 1 negctl_pre_vs_pre python3 trap_triage/frames_check.py "$OUT/pre.json" "$OUT/pre.json"
expect 1 negctl_kind_mut python3 trap_triage/frames_check.py "$OUT/pre.json" "$OUT/mut.json"
python3 trap_triage/survey_diff.py "$OUT/pre.json" "$OUT/post.json" > "$OUT/survey_diff.txt" 2>&1
python3 trap_triage/survey_diff.py "$OUT/pre.json" "$OUT/mut.json" > "$OUT/survey_diff_mut.txt" 2>&1
grep -E "ok 退行|kind 以外" "$OUT/survey_diff.txt" | sed 's/^/post: /'
grep -E "ok 退行" "$OUT/survey_diff_mut.txt" | sed 's/^/mut:  /'
[ "$fail" = 0 ] && echo "NEGCTL_663 ALL EXPECTED" || { echo "NEGCTL_663 UNEXPECTED"; exit 1; }
