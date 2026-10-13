#!/usr/bin/env bash
# #595 再現 + ネガコン: m11_ov.c の function_413060 の `u64 old = Q(dest);` だけを D4 の欠陥形 `u64 old = (u64)(uintptr_t)dest;` (RetDec の deref 脱落) に戻した構成を
#   work/obj/ov.o に差し替えて ON (M11_OV_CLASSCREATE=1) で build → survey_units.mjs し, 現行 ON (転記どおり) と unit 単位で比べる.
#   usage: negctl_595.sh [on d4 ...]   (省略時は両方)   結果: work/negctl_595/<名>.{json,out,err} + 1 行サマリ + 遷移
#   期待 (REPORT_595 §2.2): on = ok 817 / miss 47 (ok 退行 415 のみ) / d4 = ok 816 / miss 48 (unit 15 だけ ok→miss, icall 0x1407000 miss 2)
#   終了時に work/obj/ov.o を現行 m11_ov.c から既定 (M11_OV_CLASSCREATE=0) で再生成する.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
HANG_S="${HANG_S:-120}"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=1 -I."
OUT=work/negctl_595; mkdir -p "$OUT"
gen() { # gen <構成> → work/ov_ablate.c
  case "$1" in
    on) cp m11_ov.c work/ov_ablate.c ;;
    d4) sed '/^unsigned long long function_413060(/,/^}/ s/u64 old = Q(dest);/u64 old = (u64)(uintptr_t)dest;/' m11_ov.c > work/ov_ablate.c ;;
    *) echo "unknown config $1" >&2; return 1 ;;
  esac
  [ "$(diff m11_ov.c work/ov_ablate.c | grep -c '^>')" = "$([ "$1" = on ] && echo 0 || echo 1)" ] || { echo "$1: 置換行数が想定と違う" >&2; return 1; }
}
M11_OV_CLASSCREATE=1 bash m11_build.sh > /dev/null 2>&1 || { echo "ON の初回 build に失敗" >&2; exit 1; }
CFGS=("$@"); [ ${#CFGS[@]} = 0 ] && CFGS=(on d4)
for c in "${CFGS[@]}"; do
  gen "$c" || continue
  emcc -c work/ov_ablate.c -o work/obj/ov.o $CF || { echo "$c: ov compile FAIL"; continue; }
  touch work/obj/ov.o
  M11_OV_CLASSCREATE=1 bash m11_build.sh > "$OUT/$c.build.log" 2>&1 || { echo "$c: link FAIL"; tail -3 "$OUT/$c.build.log"; continue; }
  s=$(date +%s.%N)
  timeout "$HANG_S" node trap_triage/survey_units.mjs "$OUT/$c.json" > "$OUT/$c.out" 2> "$OUT/$c.err"; rc=$?
  e=$(date +%s.%N)
  if [ $rc = 124 ]; then r="HANG (timeout ${HANG_S}s)"; else r=$(grep -a SURVEY_UNITS "$OUT/$c.out" | head -1); fi
  printf '%-3s rc=%-3s %.1fs  %s\n' "$c" "$rc" "$(echo "$e - $s" | bc)" "$r"
done
if [ -f "$OUT/on.json" ] && [ -f "$OUT/d4.json" ]; then
  echo "--- on -> d4 (survey_diff.py)"
  python3 trap_triage/survey_diff.py "$OUT/on.json" "$OUT/d4.json" | grep -a -E "ok +-> +miss|^ok 退行|kind 以外"
  echo "--- icall target 0x1407000 (unit 単位)"
  for c in on d4; do echo -n "$c: "; python3 trap_triage/icall_hits.py "$OUT/$c.json" --units | grep -a "0x1407000" || echo "(0x1407000 の hit なし)"; done
fi
rm -f work/ov_ablate.c; touch m11_ov.c; bash m11_build.sh > /dev/null 2>&1; echo "ov.o を現行 m11_ov.c から既定 (M11_OV_CLASSCREATE=0) で再生成した"
