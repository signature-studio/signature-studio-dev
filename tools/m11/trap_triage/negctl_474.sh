#!/usr/bin/env bash
# #474 再現 + ネガコン: m11_ov.c の転記を 1 つずつ外した構成を work/obj/ov.o に差し替えて link → survey_units.mjs.
#   usage: negctl_474.sh [構成名 ...]   (省略時は全構成)  各構成の結果を work/negctl_474/<名>.json + 1 行サマリで出す
#   構成: full(現行) head(転記なし=BASE_REF の m11_ov.c) no5c0270 noinitinst no410320 no409470 chk(full + 5c00e0 循環検査) chkneg(no5c0270 + 循環検査)
#   ハング判定は timeout (HANG_S 秒, 既定 30). 終了時に work/obj/ov.o を現行 m11_ov.c から再生成する.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
HANG_S="${HANG_S:-30}"; BASE_REF="${BASE_REF:-93a11c8}"   # head 構成 = #444 HEAD (93a11c8) の m11_ov.c
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
OUT=work/negctl_474; mkdir -p "$OUT"
[ -f work/obj/boot.o ] || bash m11_build.sh > /dev/null
rename_def() { sed -E "s/^(unsigned long long|u64) $1\(/static __attribute__((unused)) u64 abl_$1(/" ; }
gen() { # gen <構成> → work/ov_ablate.c
  case "$1" in
    full|chk) cp m11_ov.c work/ov_ablate.c ;;
    head) git show "$BASE_REF:tools/m11/m11_ov.c" > work/ov_ablate.c ;;
    no5c0270|chkneg) rename_def function_5c0270 < m11_ov.c > work/ov_ablate.c ;;
    no410320) rename_def function_410320 < m11_ov.c > work/ov_ablate.c ;;
    no409470) sed -E 's/^unsigned long long function_409470\(/static __attribute__((unused)) unsigned long long abl_409470(/' m11_ov.c > work/ov_ablate.c ;;
    noinitinst) { echo 'unsigned long long function_40fb40(unsigned long long, unsigned long long);'; rename_def function_40fb40 < m11_ov.c; } > work/ov_ablate.c
      cat >> work/ov_ablate.c <<'XX'
/* ablation: 試作版 (FillChar + vptr のみ; interface vptr / tkMRecord 入れ子処理なし) */
u64 function_40fb40(u64 self, u64 inst) { memset((void*)(uintptr_t)inst, 0, (size_t)(long long)(int)D(self - 0x80)); Q(inst) = self; return inst; }
XX
      ;;
    *) echo "unknown config $1" >&2; return 1 ;;
  esac
}
CFGS=("$@"); [ ${#CFGS[@]} = 0 ] && CFGS=(head full no5c0270 noinitinst no410320 no409470 chk chkneg)
for c in "${CFGS[@]}"; do
  gen "$c" || continue
  rm -f work/obj/chk5c.o
  emcc -c work/ov_ablate.c -o work/obj/ov.o $CF || { echo "$c: ov compile FAIL"; continue; }
  [[ "$c" = chk* ]] && emcc -c trap_triage/chk_5c00e0.c -o work/obj/chk5c.o $CF
  touch work/obj/ov.o
  bash m11_build.sh > work/negctl_build.log 2>&1 || { echo "$c: link FAIL"; tail -3 work/negctl_build.log; continue; }
  s=$(date +%s.%N)
  SV_TRACE_AT=99999 timeout "$HANG_S" node trap_triage/survey_units.mjs "$OUT/$c.json" > "$OUT/$c.out" 2> "$OUT/$c.err"; rc=$?
  e=$(date +%s.%N)
  if [ $rc = 124 ]; then r="HANG (timeout ${HANG_S}s)"; else r=$(grep -a SURVEY_UNITS "$OUT/$c.out" | head -1); fi
  sum=$(awk '/^\[chk5c00e0\] (CYCLE )?call#/ { if ($0 ~ /CYCLE/) c++; else { n++; split($NF, a, "="); m = a[2] } } END { if (n + c > 0) printf "chk5c00e0: calls=%d maxlen=%d CYCLE=%d", n, m, c }' "$OUT/$c.err")
  printf '%-11s rc=%-3s %.1fs  %s  %s\n' "$c" "$rc" "$(echo "$e - $s" | bc)" "$r" "$sum"
done
rm -f work/obj/chk5c.o work/ov_ablate.c; touch m11_ov.c; bash m11_build.sh > /dev/null 2>&1; echo "ov.o を現行 m11_ov.c から再生成した"
