#!/usr/bin/env bash
# #482 再現 + ネガコン + 計測: m11_ov.c の function_5c03d0 転記を外した/計測を足した構成を work/obj/ov.o に差し替えて link → survey_units.mjs.
#   usage: negctl_482.sh [構成名 ...]   (省略時は全構成)  各構成の結果を work/negctl_482/<名>.{json,out,err} + 1 行サマリで出す
#   構成: full(現行) no5c03d0(転記を外す = IR の weak 版 = #481 HEAD と同じ) probe(full + 5c03d0 の呼出し/通知を stderr に記録)
#         probeoff(no5c03d0 + 5c03d0 の呼出しだけ記録; 通知は脱落のまま)
#   終了時に work/obj/ov.o を現行 m11_ov.c から再生成する.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
HANG_S="${HANG_S:-30}"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
OUT=work/negctl_482; mkdir -p "$OUT"
[ -f work/obj/boot.o ] || bash m11_build.sh > /dev/null
PROBE_OLD='    Q(obj + 0x18) = node;'
gen() { # gen <構成> → work/ov_ablate.c
  case "$1" in
    full) cp m11_ov.c work/ov_ablate.c ;;
    no5c03d0) sed -E 's/^u64 function_5c03d0\(/static __attribute__((unused)) u64 abl_5c03d0(/' m11_ov.c > work/ov_ablate.c ;;
    probe)
      # 通知先を解決できたか (disp_find) まで記録する. 呼出しそのものは full と同じ
      perl -0pe 's/(    Q\(obj \+ 0x18\) = node;\n)    if \(node != old\) m11_icall\(Q\(Q\(obj\) \+ 0x18\), obj, 0, 0, 0, 0, 0, 0, 0\);/$1    { static int n = 0; u64 tg = Q(Q(obj) + 0x18); fprintf(stderr, "[probe5c03d0] call#%d changed=%d obj=%llx old=%llx node=%llx target=%llx resolved=%d\\n", ++n, node != old, obj, old, node, tg, disp_find((u32)(tg + (0x400000ull - M11_LB_BASE))) != 0); }\n    if (node != old) m11_icall(Q(Q(obj) + 0x18), obj, 0, 0, 0, 0, 0, 0, 0);/' m11_ov.c > work/ov_ablate.c ;;
    probeoff)
      perl -0pe 's/(    Q\(obj \+ 0x18\) = node;\n)    if \(node != old\) m11_icall\(Q\(Q\(obj\) \+ 0x18\), obj, 0, 0, 0, 0, 0, 0, 0\);/$1    { static int n = 0; u64 tg = Q(Q(obj) + 0x18); fprintf(stderr, "[probe5c03d0] call#%d changed=%d obj=%llx old=%llx node=%llx target=%llx resolved=%d NOTIFY-SKIPPED\\n", ++n, node != old, obj, old, node, tg, disp_find((u32)(tg + (0x400000ull - M11_LB_BASE))) != 0); }/' m11_ov.c > work/ov_ablate.c ;;
    *) echo "unknown config $1" >&2; return 1 ;;
  esac
  if [ "$1" = probe ] || [ "$1" = probeoff ]; then grep -q probe5c03d0 work/ov_ablate.c || { echo "$1: probe 挿入に失敗" >&2; return 1; }; fi
}
CFGS=("$@"); [ ${#CFGS[@]} = 0 ] && CFGS=(full no5c03d0 probe probeoff)
for c in "${CFGS[@]}"; do
  gen "$c" || continue
  emcc -c work/ov_ablate.c -o work/obj/ov.o $CF || { echo "$c: ov compile FAIL"; continue; }
  touch work/obj/ov.o
  bash m11_build.sh > work/negctl_build.log 2>&1 || { echo "$c: link FAIL"; tail -3 work/negctl_build.log; continue; }
  s=$(date +%s.%N)
  SV_PROG=1 SV_TRACE_AT=99999 timeout "$HANG_S" node trap_triage/survey_units.mjs "$OUT/$c.json" > "$OUT/$c.out" 2> "$OUT/$c.err"; rc=$?
  e=$(date +%s.%N)
  if [ $rc = 124 ]; then r="HANG (timeout ${HANG_S}s)"; else r=$(grep -a SURVEY_UNITS "$OUT/$c.out" | head -1); fi
  pr=$(grep -ac '^\[probe5c03d0\]' "$OUT/$c.err"); ch=$(grep -ac '^\[probe5c03d0\].* changed=1 ' "$OUT/$c.err"); rs=$(grep -ac '^\[probe5c03d0\].* changed=1 .* resolved=1' "$OUT/$c.err")
  printf '%-9s rc=%-3s %.1fs  %s  5c03d0 calls=%s changed=%s resolved=%s\n' "$c" "$rc" "$(echo "$e - $s" | bc)" "$r" "$pr" "$ch" "$rs"
done
rm -f work/ov_ablate.c; touch m11_ov.c; bash m11_build.sh > /dev/null 2>&1; echo "ov.o を現行 m11_ov.c から再生成した"
