#!/usr/bin/env bash
# #495 再現 + ネガコン: SV_TRACE_AT の有無で survey JSON が変わらないことを, trace 透過化 (M11_TRACE_ISOLATE=1, 現行) と素の fprintf (=0, 修正前相当) で比べる.
#   usage: negctl_495.sh [iso1] [iso0]   (省略時は両方)   結果: work/negctl_495/<variant>_<cfg>.{json,out} + 1 行サマリ (JSON の md5 / 基準との差分 unit)
#   variant: iso1 = 現行 m11_ov.c / iso0 = -DM11_TRACE_ISOLATE=0 (trace が shadow stack を汚す = 修正前と同じ挙動)
#   cfg: none(trace 無し=基準) / t0 / t114 / t134 / t99999 (SV_TRACE_AT=<n>; 99999 は一致する unit が無く trace は入らない) /
#        fillff / fill00 (trace 無し, 各 unit の直前に SP 直下 8 KiB を 0xff / 0x00 で埋める = 残骸への感度) / t0_fill00 (trace 有り + 同じ 0x00 埋め)
#   終了時に work/obj/ov.o,rt.o を現行ソースから再生成する.
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
source /opt/emsdk/emsdk_env.sh > /dev/null 2>&1
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -I."
OUT=work/negctl_495; mkdir -p "$OUT"
[ -f work/obj/boot.o ] || bash m11_build.sh > /dev/null
cmp_py='
import json, sys
def load(p): return {r["unit"]: r for r in json.load(open(p))}
a, b = load(sys.argv[1]), load(sys.argv[2])
def norm(r): return {k: (len(v) if k == "frames" else v) for k, v in r.items()}
d = [u for u in sorted(a) if norm(a[u]) != norm(b[u])]
k = [u for u in sorted(a) if a[u]["kind"] != b[u]["kind"]]
print("差分 unit %d %s / kind 変化 %d %s" % (len(d), d[:6], len(k), [(u, a[u]["kind"], b[u]["kind"]) for u in k][:6]))'
runcfg() { # runcfg <variant> <cfg> <env...>
  local v="$1" c="$2"; shift 2
  local f="$OUT/${v}_$c"
  env "$@" node trap_triage/survey_units.mjs "$f.json" > "$f.out" 2> "$f.err"
  local md; md=$(md5sum < "$f.json" | cut -c1-12)
  printf '%-5s %-10s %s  md5=%s  ' "$v" "$c" "$(grep -a SURVEY_UNITS "$f.out" | head -1)" "$md"
  [ "$c" = none ] && { echo "(基準)"; return; }
  case "$c" in t0_fill00) ref="$OUT/${v}_fill00" ;; *) ref="$OUT/${v}_none" ;; esac
  python3 -c "$cmp_py" "$ref.json" "$f.json" | sed "s/^/vs 基準: /"
}
VARS=("$@"); [ ${#VARS[@]} = 0 ] && VARS=(iso1 iso0)
for v in "${VARS[@]}"; do
  case "$v" in iso1) D=1 ;; iso0) D=0 ;; *) echo "unknown variant $v" >&2; continue ;; esac
  emcc -c m11_ov.c -o work/obj/ov.o $CF -DM11_TRACE_ISOLATE=$D || { echo "$v: ov compile FAIL"; continue; }
  touch work/obj/ov.o
  bash m11_build.sh > work/negctl_build.log 2>&1 || { echo "$v: link FAIL"; tail -3 work/negctl_build.log; continue; }
  runcfg "$v" none NONE=1
  for t in 0 114 134 99999; do runcfg "$v" "t$t" SV_TRACE_AT=$t; done
  runcfg "$v" fillff SV_STK_FILL=ff
  runcfg "$v" fill00 SV_STK_FILL=00
  runcfg "$v" t0_fill00 SV_TRACE_AT=0 SV_STK_FILL=00
  [ "$v" = iso1 ] && echo "iso1: trace が汚した shadow stack の最深距離 (SV_TRACE_PROBE, SV_TRACE_AT=0; M11_TRACE_SPAN=8192): $(SV_TRACE_PROBE=1 SV_TRACE_AT=0 node trap_triage/survey_units.mjs /dev/null 2>/dev/null | grep -a TRACE_MAXDIRTY)"
done
touch m11_ov.c m11_rt.c; bash m11_build.sh > /dev/null 2>&1; echo "ov.o / rt.o を現行ソースから再生成した"
