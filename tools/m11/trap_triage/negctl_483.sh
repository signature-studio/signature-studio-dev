#!/usr/bin/env bash
# #483 ネガコン + 独立計測: m11_ov.c の転記を 1 つずつ外した構成を work/obj/ov.o に差し替えて link → survey_units.mjs (survey_diff.py で現行 HEAD 版と比較).
#   usage: negctl_483.sh [構成名 ...]   (省略時は全構成)  各構成の結果を work/negctl_483/<名>.json + 1 行サマリで出す
#   構成: head(#481 HEAD = BASE_REF の m11_ov.c) full(現行) no479b40 no8cbce0 no8cc190 no8cbde0 nogetters no478420 no478540 no478c70 nocmpmeth
#         probe_head (#481 HEAD + 8cc190 の観測 [probe] 行: FComparer の中身と重複判定) / raise_head / raise_full (411e80 = RaiseExcept 呼出を数える, 動作は IR と同一; [raise411e80] 行数 = survey 中の raise 回数)
#   終了時に work/obj/ov.o を現行 m11_ov.c から再生成する.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
BASE_REF="${BASE_REF:-dd9ba2c}"   # head 構成 = #481 HEAD (dd9ba2c) の m11_ov.c
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
OUT=work/negctl_483; mkdir -p "$OUT"
[ -f work/obj/boot.o ] || bash m11_build.sh > /dev/null
rename_def() { sed -E "s/^(unsigned long long|u64) $1\(/static __attribute__((unused)) u64 abl_$1(/" ; }
nocase() { sed -E "/^    case 0x$1: return /d"; }
RAISE='u64 function_411e80(u64 obj) { fprintf(stderr, "[raise411e80] obj=%llx\n", obj); return function_411d20(0, obj, 0); }'
gen() { # gen <構成> → work/ov_ablate.c
  case "$1" in
    full) cp m11_ov.c work/ov_ablate.c ;;
    head) git show "$BASE_REF:tools/m11/m11_ov.c" > work/ov_ablate.c ;;
    probe_head) { git show "$BASE_REF:tools/m11/m11_ov.c"; cat trap_triage/probe_8cc190.c; } > work/ov_ablate.c ;;
    raise_head) { git show "$BASE_REF:tools/m11/m11_ov.c"; echo "$RAISE"; } > work/ov_ablate.c ;;
    raise_full) { cat m11_ov.c; echo "$RAISE"; } > work/ov_ablate.c ;;
    no479b40) rename_def function_479b40 < m11_ov.c > work/ov_ablate.c ;;
    no8cbce0) rename_def function_8cbce0 < m11_ov.c > work/ov_ablate.c ;;
    no8cc190) rename_def function_8cc190 < m11_ov.c > work/ov_ablate.c ;;
    no8cbde0) rename_def function_8cbde0 < m11_ov.c > work/ov_ablate.c ;;
    nogetters) nocase 478420 < m11_ov.c | nocase 478540 | nocase 478c70 > work/ov_ablate.c ;;
    no478420) nocase 478420 < m11_ov.c > work/ov_ablate.c ;;
    no478540) nocase 478540 < m11_ov.c > work/ov_ablate.c ;;
    no478c70) nocase 478c70 < m11_ov.c > work/ov_ablate.c ;;
    nocmpmeth) nocase 479b00 < m11_ov.c | nocase 479b10 > work/ov_ablate.c ;;
    *) echo "unknown config $1" >&2; return 1 ;;
  esac
}
CFGS=("$@"); [ ${#CFGS[@]} = 0 ] && CFGS=(head full no479b40 no8cbce0 no8cc190 no8cbde0 nogetters no478420 no478540 no478c70 nocmpmeth raise_head raise_full probe_head)
for c in "${CFGS[@]}"; do
  gen "$c" || continue
  emcc -c work/ov_ablate.c -o work/obj/ov.o $CF || { echo "$c: ov compile FAIL"; continue; }
  touch work/obj/ov.o
  bash m11_build.sh > work/negctl_build.log 2>&1 || { echo "$c: link FAIL"; tail -3 work/negctl_build.log; continue; }
  s=$(date +%s.%N)
  SV_TRACE_AT=99999 timeout 60 node trap_triage/survey_units.mjs "$OUT/$c.json" > "$OUT/$c.out" 2> "$OUT/$c.err"; rc=$?
  e=$(date +%s.%N)
  if [ $rc = 124 ]; then r="HANG (timeout 60s)"; else r=$(grep -a SURVEY_UNITS "$OUT/$c.out" | head -1); fi
  rz=$(grep -ac '^\[raise411e80\]' "$OUT/$c.err")
  [[ "$c" = raise_* ]] && rz=" raise411e80=$rz" || rz=""
  printf '%-10s rc=%-3s %.1fs  %s%s\n' "$c" "$rc" "$(echo "$e - $s" | bc)" "$r" "$rz"
done
rm -f work/ov_ablate.c; touch m11_ov.c; bash m11_build.sh > /dev/null 2>&1; echo "ov.o を現行 m11_ov.c から再生成した"
